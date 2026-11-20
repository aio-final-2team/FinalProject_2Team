"""3·5번 API: 요청 만들기, 요청 상세(API 설계 문서 3.1·3.2)."""

from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status

from app.api.labels import parent_label, staff_label
from app.api.schemas.common import Period, errors
from app.api.schemas.requests import (ConsultationOut, MessageOut, RequestAccepted, RequestAcceptedOut,
                                      RequestCreateIn, RequestDetailOut, RequestView, SlotOut, TimelineItem)
from app.core.auth import CurrentUser, current_user, require_roles
from app.core.errors import trace_id_of
from app.backend import store, request_actions, documents
from app.api.schemas.actions import MessageIn, SlotChoicesIn
from app.api.schemas.requests import RequestStatus, BookingOut
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
def get_request(request_id: UUID, user: CurrentUser = Depends(current_user)) -> RequestDetailOut:
    with store._lock:
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
            booking = store.confirmed_booking_of(req.id)
            consultation = ConsultationOut(slots=[
                SlotOut(id=s.id, period=Period(**s.period), room=store.room_name(s.room_id), status=s.status)
                for s in store.slots_of_request(req.id) if s.status != "discarded"
            ], booking=BookingOut(id=booking.id, room=store.room_name(booking.room_id), period=Period(**booking.period))
                if booking else None)
        return RequestDetailOut(
            request=RequestView(id=req.id, type=req.type, title=req.title, status=req.status,
                                status_label=label(req.status, req.type), missing_fields=req.missing_fields,
                                hold_until=store.hold_until_of(req.id), parent_confirmed_at=req.parent_confirmed_at,
                                created_at=req.created_at, updated_at=req.updated_at),
            messages=[MessageOut(id=m.id, sender_type=m.sender_type, body=m.body, created_at=m.created_at)
                      for m in store.messages_of(req.id)],
            timeline=timeline,
            consultation=consultation,
            rejection=store.rejection_of(req.id) if req.status == "rejected" else None,
            sources=[source for card in store.approved_cards_of(req.id)
                     for source in documents.evidence(card, parent=user.role == "parent")]
                     if req.status in ("sent_or_booked", "completed") else [],
        )


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
