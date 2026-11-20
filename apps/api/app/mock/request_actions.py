"""학부모의 대화·시간 체크·회신 확인."""

from app.core.errors import ApiError
from app.mock import store


def message(user, request_id, body):
    with store._lock:
        req = store.request_in_scope(user, request_id)
        if req.status in ("completed", "rejected"):
            raise ApiError(409, "INVALID_TRANSITION")
        msg = store.Message(store.state().next_int(), req.id, "user", user.id, body)
        store.state().messages.append(msg)
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
