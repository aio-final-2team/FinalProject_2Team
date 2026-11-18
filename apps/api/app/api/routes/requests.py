"""3·5번 API: 요청 만들기, 요청 상세(API 설계 문서 3.1·3.2)."""

from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status

from app.api.labels import parent_label, staff_label
from app.api.schemas.common import Period, errors
from app.api.schemas.requests import (ConsultationOut, MessageOut, RequestAccepted, RequestAcceptedOut,
                                      RequestCreateIn, RequestDetailOut, RequestView, SlotOut, TimelineItem)
from app.core.auth import CurrentUser, current_user, require_roles
from app.core.errors import trace_id_of
from app.mock import store

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
def get_request(request_id: UUID, user: CurrentUser = Depends(current_user)) -> RequestDetailOut:
    req = store.request_in_scope(user, request_id)
    label = parent_label if user.role == "parent" else staff_label
    timeline: list[TimelineItem] = []
    for e in store.events_of(req.id):           # 상태가 바뀐 단계만, 같은 표시 이름이 이어지면 하나로
        if e.to_status is None:
            continue
        text = label(e.to_status, req.type)
        if not timeline or timeline[-1].label != text:
            timeline.append(TimelineItem(label=text, at=e.created_at))
    consultation = None
    if req.type == "consultation":
        rooms = store.state().rooms
        consultation = ConsultationOut(slots=[
            SlotOut(id=s.id, period=Period(start=s.start, end=s.end), room=rooms[s.room_id].name, status=s.status)
            for s in store.slots_of_request(req.id) if s.status != "discarded"
        ])
    return RequestDetailOut(
        request=RequestView(id=req.id, type=req.type, title=req.title, status=req.status,
                            status_label=label(req.status, req.type), missing_fields=req.missing_fields,
                            hold_until=store.hold_until_of(req.id), parent_confirmed_at=req.parent_confirmed_at,
                            created_at=req.created_at, updated_at=req.updated_at),
        messages=[MessageOut(id=m.id, sender_type=m.sender_type, body=m.body, created_at=m.created_at)
                  for m in store.messages_of(req.id)],
        timeline=timeline,
        consultation=consultation,
    )
