"""3·5번 API: 요청 만들기, 요청 상세(API 설계 문서 3.1·3.2)."""

from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status

from app.api.labels import parent_label
from app.api.schemas.common import errors
from app.api.schemas.requests import (RequestAccepted, RequestAcceptedOut,
                                      RequestCreateIn, RequestDetailOut)
from app.core.auth import CurrentUser, current_user as read_user
# T27에서 걷을 목록: 아래 workflows 역할 별칭을 쓰기·스트림 구현과 함께 바꾼다.
from app.core.workflows import require_workflow_roles as require_roles
from app.core.errors import trace_id_of
from app import backend
from app.backend import store, request_actions
from app.api.schemas.actions import MessageIn, SlotChoicesIn
from app.api.schemas.requests import RequestStatus
from app.api.schemas.views import RequestList, MessageResponse, ChoicesResponse, ConfirmResponse
from app.api.streams import stream
from fastapi import Query
from typing import Literal

router = APIRouter(tags=["학부모 요청"])


def _stream_url(request_id: UUID) -> str:
    return f"/api/v1/requests/{request_id}/stream"


@router.post("/requests", status_code=status.HTTP_202_ACCEPTED, response_model=RequestAcceptedOut,
             responses={200: {"model": RequestAcceptedOut, "description": "같은 client_request_id로 다시 보냄"},
                        **errors(401, 403, 404, 409, 422)},
             summary="요청 만들기, AI 처리 접수 (FR-02, FR-03)")
def create_request(body: RequestCreateIn, request: Request, response: Response,
                   user: CurrentUser = Depends(require_roles("parent"))) -> RequestAcceptedOut:
    req, created = store.create_request(user, trace_id=trace_id_of(request), **body.model_dump())
    if not created:
        response.status_code = status.HTTP_200_OK
    return RequestAcceptedOut(request=RequestAccepted(id=req.id, status="received" if created else req.status,
                                                      stream_url=_stream_url(req.id)))


@router.get("/requests/{request_id}", response_model=RequestDetailOut, responses=errors(401, 404, 422),
            summary="요청 상세·대화·진행 기록 (FR-02, FR-11)")
def get_request(request_id: UUID, user: CurrentUser = Depends(read_user)) -> RequestDetailOut:
    return backend.request_actions.detail(user, request_id)


@router.get("/requests", response_model=RequestList, responses=errors(401, 403, 422))
def list_requests(status: RequestStatus | None = None, page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
                  sort: Literal["-created_at", "created_at", "-updated_at", "updated_at"] = "-created_at",
                  user: CurrentUser = Depends(require_roles("parent"))):
    with store._lock:
        store.expire()
        requests = store.requests_of(user, status)
        requests.sort(key=lambda r: getattr(r, sort.lstrip("-")), reverse=sort.startswith("-"))
        def item(r):
            action = None
            if r.status == "needs_info":
                action = "시간을 골라 주세요" if r.type == "consultation" else "정보를 더 알려 주세요"
            if r.type == "complaint" and r.status == "sent_or_booked" and r.parent_confirmed_at is None:
                action = "답변을 확인해 주세요"
            return {"id": r.id, "type": r.type, "title": r.title, "status": r.status,
                    "status_label": parent_label(r.status, r.type), "updated_at": r.updated_at,
                    "next_action": action, "hold_until": store.hold_until_of(r.id)}
        return {"items": [item(r) for r in requests[(page-1)*size:page*size]], "total": len(requests), "page": page, "size": size}


@router.get("/requests/{request_id}/stream", response_class=Response,
            responses={200: {"content": {"text/event-stream": {"schema": {"type": "string"}}}}, **errors(401, 403, 404, 422)})
def request_stream(request_id: UUID, user: CurrentUser = Depends(require_roles("parent"))):
    return stream(store.request_in_scope(user, request_id))


@router.post("/requests/{request_id}/messages", status_code=201, response_model=MessageResponse, responses=errors(401, 403, 404, 409, 422))
def add_message(request_id: UUID, body: MessageIn, user: CurrentUser = Depends(require_roles("parent"))):
    return request_actions.message(user, request_id, body.body)


@router.post("/requests/{request_id}/slot-choices", response_model=ChoicesResponse, responses=errors(401, 403, 404, 409, 422))
def choose_slots(request_id: UUID, body: SlotChoicesIn, user: CurrentUser = Depends(require_roles("parent"))):
    return request_actions.choices(user, request_id, body)


@router.post("/requests/{request_id}/confirm", response_model=ConfirmResponse, responses=errors(401, 403, 404, 409, 422))
def confirm_request(request_id: UUID, user: CurrentUser = Depends(require_roles("parent"))):
    return request_actions.confirm(user, request_id)
