"""학부모의 대화·시간 체크·회신 확인."""

from app.core.errors import ApiError
from app.api.labels import parent_label, staff_label
from app.api.schemas.common import Period
from app.api.schemas.requests import (BookingOut, ConsultationOut, MessageOut, RequestDetailOut,
                                      RequestView, SlotOut, TimelineItem)
from app.mock import documents, store


def detail(user, request_id):
    with store._lock:
        req = store.request_in_scope(user, request_id)
        label = parent_label if user.role == "parent" else staff_label
        timeline: list[TimelineItem] = []
        for e in store.events_of(req.id):
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
            timeline=timeline, consultation=consultation,
            rejection=store.rejection_of(req.id) if req.status == "rejected" else None,
            sources=[source for card in store.approved_cards_of(req.id)
                     for source in documents.evidence(card, parent=user.role == "parent")]
                     if req.status in ("sent_or_booked", "completed") else [],
        )


def message(user, request_id, body, *, background_tasks=None):
    with store._lock:
        req = store.request_in_scope(user, request_id)
        if req.status in ("completed", "rejected"):
            raise ApiError(409, "INVALID_TRANSITION")
        msg = store.Message(store.state().next_int(), req.id, "user", user.id, body)
        store.state().messages.append(msg)
        store.add_event(req, "created", actor_type="user", actor_id=user.id, message_id=msg.id)
        req.updated_at = store.now()
        if req.type == "complaint" and req.status == "sent_or_booked":
            req.parent_confirmed_at = None
            card = next(c for c in reversed(store.cards_of(req.id)) if c.kind == "reply_draft")
            card.status, card.closed_at = "pending", None
            card.version += 1
            store.set_request_status(req, "awaiting_review", action="returned", card=card, actor_type="user", actor_id=user.id)
        elif req.status == "needs_info" and req.type != "consultation":
            store._run_mock_ai(req, None)
        return {"message": msg.__dict__}


def choices(user, request_id, body):
    with store._lock:
        req = store.request_in_scope(user, request_id)
        if req.type != "consultation" or req.status != "needs_info":
            raise ApiError(409, "INVALID_TRANSITION")
        slots = [s for s in store.slots_of_request(req.id) if s.status != "discarded"]
        card = store.state().cards[slots[0].card_id]
        if body.none_fit:
            for slot in slots:
                slot.status = "discarded"
            slots = store._propose_slots(card, card.assignee_id, max(s.round for s in slots) + 1)
            store.add_event(req, "info_requested", card=card, actor_type="user", actor_id=user.id,
                            preferred_times=body.preferred_times)
        else:
            chosen = [s for s in slots if s.id in body.slot_ids]
            if len(chosen) != len(body.slot_ids):
                store.deny(user)
            for slot in chosen:
                slot.status, slot.chosen_at = "chosen_by_parent", store.now()
            slots = chosen
            store.set_request_status(req, "awaiting_review", action="checked", card=card, actor_type="user", actor_id=user.id)
        return {"slots": [{"id": s.id, "status": s.status} for s in slots], "request": request_state(req)}


def confirm(user, request_id):
    with store._lock:
        req = store.request_in_scope(user, request_id)
        if req.type != "complaint" or req.status != "sent_or_booked":
            raise ApiError(409, "INVALID_TRANSITION")
        if req.parent_confirmed_at is None:
            req.parent_confirmed_at = req.updated_at = store.now()
            store.add_event(req, "parent_confirmed", actor_type="user", actor_id=user.id)
        return {"request": request_state(req)}


def request_state(req):
    return {"id": req.id, "status": req.status, "parent_confirmed_at": req.parent_confirmed_at}


def create(user, *, background_tasks=None, **values):
    req, created = store.create_request(user, **values)
    return {"id": req.id, "status": req.status}, created


def listing(user, status, page, size, sort):
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


def stream(user, request_id):
    from app.api.streams import stream as response
    return response(store.request_in_scope(user, request_id))
