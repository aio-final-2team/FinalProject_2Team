"""학부모의 대화·시간 체크·회신 확인."""

from datetime import timedelta

from app.core.errors import ApiError
from app.core.constants import CARE_REQUEST_TYPES
from app.api.labels import parent_label, staff_label
from app.api.schemas.common import Period
from app.api.schemas.requests import (BookingOut, ConsultationOut, MessageOut, RequestDetailOut,
                                      RequestView, SlotOut, TimelineItem)
from app.mock import care, documents, store


def detail(user, request_id):
    with store._lock:
        req = store.request_in_scope(user, request_id)
        label = parent_label if user.role == "parent" else staff_label
        timeline: list[TimelineItem] = []
        for e in store.events_of(req.id):
            if e.to_status is None:
                continue
            text = label(e.to_status, req.type, req.assignee_id)
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
        care_state = care.view(req) if req.type in CARE_REQUEST_TYPES else None
        return RequestDetailOut(
            request=RequestView(id=req.id, type=req.type, title=req.title, status=req.status,
                                status_label=label(req.status, req.type, req.assignee_id),
                                missing_fields=care_state["missing_fields"] if care_state else req.missing_fields,
                                hold_until=store.hold_until_of(req.id), parent_confirmed_at=req.parent_confirmed_at,
                                created_at=req.created_at, updated_at=req.updated_at),
            messages=[MessageOut(id=m.id, sender_type=m.sender_type, sender_role=m.sender_role, body=m.body,
                                 created_at=m.created_at) for m in store.messages_of(req.id)],
            timeline=timeline, consultation=consultation,
            care=care_state,
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
        if req.type in CARE_REQUEST_TYPES:
            store.set_request_status(req, "received", action="returned", actor_type="user", actor_id=user.id,
                                     care_message=True, message_id=msg.id, version=care.view(req)["version"] + 1)
        else:
            store.add_event(req, "created", actor_type="user", actor_id=user.id, message_id=msg.id)
        req.updated_at = store.now()
        if req.type == "complaint" and req.status == "sent_or_booked":
            req.parent_confirmed_at = None
            card = next(c for c in reversed(store.cards_of(req.id)) if c.kind == "reply_draft")
            card.status, card.closed_at = "pending", None
            card.version += 1
            store.set_request_status(req, "awaiting_review", action="returned", card=card, actor_type="user", actor_id=user.id)
        elif req.status == "needs_info" and req.type not in (*CARE_REQUEST_TYPES, "consultation"):
            store._run_mock_ai(req, None)
        return {"message": msg.__dict__ | {"sender_role": msg.sender_role}}


def choices(user, request_id, body):
    with store._lock:
        req = store.request_in_scope(user, request_id)
        if req.type != "consultation" or req.status != "needs_info":
            raise ApiError(409, "INVALID_TRANSITION")
        card = next((c for c in reversed(store.cards_of(req.id)) if c.kind == "consult_slots"
                     and c.status in ("pending", "in_review")), None)
        if card is None:
            raise ApiError(409, "INVALID_TRANSITION")
        round_no = max((s.round for s in store.slots_of_request(req.id) if s.card_id == card.id), default=0)
        slots = [s for s in store.slots_of_request(req.id) if s.card_id == card.id
                 and s.round == round_no and s.status == "proposed"]
        if body.none_fit:
            for slot in slots:
                slot.status = "discarded"
            slots = store._propose_slots(card, card.assignee_id, round_no + 1)
            store.add_event(req, "info_requested", card=card, actor_type="user", actor_id=user.id,
                            preferred_times=body.preferred_times)
        else:
            chosen = [s for s in slots if s.id in body.slot_ids]
            if len(chosen) != len(body.slot_ids):
                store.deny(user)
            for slot in chosen:
                if slot.period["start"] <= store.now():
                    raise ApiError(409, "SLOT_PAST")
                others = [b for b in store.state().bookings.values() if b.status == "confirmed"
                          and b.org_id == req.org_id and b.request_id != req.id]
                others += [s for s in store.state().slots.values() if s.status == "chosen_by_parent"
                           and store.state().cards[s.card_id].request_id != req.id
                           and s.chosen_at > store.now()-timedelta(hours=24)
                           and store.state().cards[s.card_id].org_id == req.org_id]
                if any((other.teacher_id == slot.teacher_id or other.room_id == slot.room_id)
                       and slot.period["start"] < (getattr(other, "expected_end_at", None) or other.period["end"])
                       and other.period["start"] < slot.period["end"] for other in others):
                    raise ApiError(409, "SLOT_TAKEN")
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
                    "status_label": parent_label(r.status, r.type, r.assignee_id), "updated_at": r.updated_at,
                    "next_action": action, "hold_until": store.hold_until_of(r.id)}
        return {"items": [item(r) for r in requests[(page-1)*size:page*size]], "total": len(requests), "page": page, "size": size}


def stream(user, request_id):
    from app.api.streams import stream as response
    with store._lock:
        req = store.request_in_scope(user, request_id)
        return response(req)
