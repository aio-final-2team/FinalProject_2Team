"""교직원 카드 결정. 판 검사부터 이력·알림까지 같은 잠금 안에서 처리한다."""

from uuid import uuid4

from app.core.errors import ApiError
from app.core.schedule import due_at
from app.mock import store
from app.mock.records import Approval, Booking
from app.mock.request_actions import request_state


def classroom_of(card):
    state = store.state()
    if card.request_id:
        return state.requests[card.request_id].classroom_id
    if card.subject_type == "daily_note_batch":
        return state.note_inputs[card.subject_id].classroom_id
    owner_id = state.rules[card.subject_id].owner_id if card.subject_type == "memory_rule" else card.assignee_id
    return next((assignment.classroom_id for assignment in state.classroom_staff if assignment.user_id == owner_id), None)


def in_scope(user, card_id):
    card = store.state().cards.get(card_id)
    if card is None or card.org_id != user.org_id or (user.role == "teacher"
            and card.assignee_id != user.id and classroom_of(card) not in store.classroom_ids_of(user.id)):
        store.deny(user, req=store.state().requests.get(card.request_id) if card and card.org_id == user.org_id else None,
                   card=card if card and card.org_id == user.org_id else None)
    store.expire(card.request_id)
    return card


def version(card, value, approval=True):
    if approval and any(a.card_id == card.id and a.card_version == value for a in store.state().approvals):
        raise ApiError(409, "ALREADY_DECIDED")
    if value != card.version:
        raise ApiError(409, "CARD_VERSION_CONFLICT", current_version=card.version)


def touch(card, status=None):
    if status:
        card.status = status
    card.version += 1
    card.updated_at = store.now()
    card.closed_at = store.now() if card.status in ("done", "rejected") else None


def record(card, user, decision, reason_code=None, reason_text=None, edited_content=None):
    store.state().approvals.append(Approval(store.state().next_int(), card.id, card.org_id, card.version,
                                           user.id, decision, store.now(), reason_code, reason_text, edited_content))


def result(card, req, next_card=None):
    return {"card": {"id": card.id, "status": card.status, "version": card.version},
            "request": request_state(req) if req else None, "next_card_id": next_card.id if next_card else None}


def decide(user, card_id, body):
    with store._lock:
        card = in_scope(user, card_id)
        if card.kind == "director_report" and user.role != "director":
            raise ApiError(403, "FORBIDDEN_ROLE")
        version(card, body.version)
        req = store.state().requests.get(card.request_id)
        decision = body.decision
        # T04 3.2: 민원 회신의 승인·완료는 교사가 한다. 원장은 지시·재배정(API 설계 4.2).
        if (user.role == "director" and req and req.type == "complaint" and card.kind == "reply_draft"
                and decision in ("approve", "edit_approve", "complete")):
            raise ApiError(403, "FORBIDDEN_ROLE")
        valid = req is not None and req.status not in ("completed", "rejected")
        if decision == "complete":
            valid = (valid and card.kind == "reply_draft" and card.status == "done"
                     and req.type == "complaint" and req.status == "sent_or_booked")
        elif decision == "resume":
            valid = valid and card.status == "on_hold" and req.status == "on_hold"
        else:
            valid = valid and card.status in ("pending", "in_review") and req.status == "awaiting_review"
        if card.kind == "director_report" and decision not in ("hold", "resume"):
            valid = False
        if decision in ("approve", "edit_approve") and card.kind != "reply_draft":
            valid = False
        if req and req.risk_level == "uncertain" and decision not in ("hold", "resume", "escalate"):
            valid = False
        if not valid:
            raise ApiError(409, "INVALID_TRANSITION")
        if decision == "complete" and req.parent_confirmed_at is None and not body.reason_text:
            raise ApiError(409, "REASON_REQUIRED")
        content = body.edited_content if decision == "edit_approve" else card.draft
        if decision in ("approve", "edit_approve") and not content.get("text", "").strip():
            raise ApiError(409, "INVALID_TRANSITION")
        record(card, user, decision, body.reason_code, body.reason_text, body.edited_content)
        actor = {"card": card, "actor_type": "user", "actor_id": user.id}
        next_card = None
        if decision in ("approve", "edit_approve"):
            card.draft = content
            card.status = "approved"
            store.set_request_status(req, "approved", action="approved", **actor)
            store.state().messages.append(store.Message(store.state().next_int(), req.id, "user", user.id, content["text"]))
            store.set_request_status(req, "sent_or_booked", action="sent", **actor)
            touch(card, "done")
        elif decision == "complete":
            store.set_request_status(req, "completed", action="completed", reason_text=body.reason_text, **actor)
            touch(card, "done")
        elif decision == "hold":
            card.hold_until = body.hold_until
            store.set_request_status(req, "on_hold", action="held", reason_text=body.reason_text, **actor)
            touch(card, "on_hold")
        elif decision == "resume":
            card.hold_until = None
            store.set_request_status(req, "awaiting_review", action="resumed", **actor)
            touch(card, "pending")
        elif decision == "dismiss":
            store.set_request_status(req, "rejected", action="dismissed", reason_code=body.reason_code,
                                     reason_text=body.reason_text, **actor)
            touch(card, "rejected")
        elif decision == "escalate":
            next_card = report(req)
            store.set_request_status(req, "escalated", action="escalated", **actor)
            touch(card)
        elif decision == "reject":
            touch(card, "rejected")
            store.set_request_status(req, "assigned", action="rejected", reason_code=body.reason_code,
                                     reason_text=body.reason_text, **actor)
            next_card = store._new_card(req, card.kind, card.assignee_id, dict(card.draft))
            next_card.check_result = card.check_result
            if card.kind == "reply_draft":
                next_card.draft["text"] = "(모의 재초안) 내용을 다시 확인해서 안내드릴게요."
            if card.kind == "consult_slots":
                for slot in store.slots_of_request(req.id):
                    slot.status = "discarded"
                store._propose_slots(next_card, next_card.assignee_id)
                store.set_request_status(req, "needs_info", action="info_requested", card=next_card)
            else:
                from app.mock.documents import attach_evidence
                attach_evidence(next_card)
                store.set_request_status(req, "awaiting_review", action="drafted", card=next_card)
        return result(card, req, next_card)


def report(req):
    existing = next((c for c in store.cards_of(req.id) if c.kind == "director_report"
                     and c.status not in ("done", "rejected")), None)
    return existing or store._new_card(req, "director_report", store.director_of(req.org_id),
                                      {"summary": req.body[:60]})


def reclassify(user, card_id, body):
    with store._lock:
        card = in_scope(user, card_id)
        if card.kind == "director_report" and user.role != "director":
            raise ApiError(403, "FORBIDDEN_ROLE")
        version(card, body.version, approval=False)
        req = store.state().requests.get(card.request_id)
        if req is None or req.type != "complaint" or req.status not in ("awaiting_review", "escalated"):
            raise ApiError(409, "INVALID_TRANSITION")
        previous = req.risk_level
        req.risk_level, req.risk_category = body.risk_level, body.risk_category if body.risk_level == "urgent" else None
        for related in store.cards_of(req.id):
            related.due_at = due_at(req.created_at, req.type, req.risk_level, related.kind)
        reports = [c for c in store.cards_of(req.id) if c.kind == "director_report"
                   and c.status not in ("done", "rejected")]
        closed_target = False
        if user.role == "director" and body.risk_level == "normal":
            for report_card in reports:
                touch(report_card, "done")
                closed_target = closed_target or report_card.id == card.id
                if report_card.id != card.id:
                    store.add_event(req, "risk_reclassified", card=report_card, actor_type="user", actor_id=user.id,
                                    reason=body.reason, previous_risk_level=previous)
            reports = []
        if not closed_target:
            touch(card)
        store.set_request_status(req, "escalated" if reports else "awaiting_review", action="risk_reclassified", card=card,
                                 actor_type="user", actor_id=user.id, reason=body.reason, previous_risk_level=previous)
        if body.risk_level == "urgent":
            report_card = report(req)
            store.set_request_status(req, "escalated", action="escalated", card=report_card, actor_type="user", actor_id=user.id)
        from app.mock.card_views import staff_request
        return {"request": staff_request(req)}


def book(user, card_id, body):
    with store._lock:
        card = in_scope(user, card_id)
        if classroom_of(card) not in store.classroom_ids_of(user.id):
            raise ApiError(403, "FORBIDDEN_ROLE")
        version(card, body.version)
        req = store.state().requests.get(card.request_id)
        slot = store.state().slots.get(body.slot_id)
        if slot is None or slot.card_id != card.id:
            store.deny(user)
        if card.kind != "consult_slots":
            raise ApiError(409, "INVALID_TRANSITION")
        if slot.status != "chosen_by_parent":
            raise ApiError(409, "SLOT_NOT_CHOSEN")
        if req.status != "awaiting_review" or card.status != "pending":
            raise ApiError(409, "INVALID_TRANSITION")
        for booking in store.state().bookings.values():
            overlaps = slot.period["start"] < booking.period["end"] and booking.period["start"] < slot.period["end"]
            if booking.status == "confirmed" and (booking.request_id == req.id or (overlaps
                    and (booking.room_id == slot.room_id or booking.teacher_id == slot.teacher_id))):
                raise ApiError(409, "SLOT_TAKEN")
        record(card, user, "approve")
        booking = Booking(uuid4(), req.org_id, req.id, slot.id, slot.teacher_id, slot.room_id, dict(slot.period), user.id)
        store.state().bookings[booking.id] = booking
        for candidate in store.state().slots.values():
            if candidate.card_id == card.id:
                candidate.status = "confirmed" if candidate.id == slot.id else "discarded"
        store.set_request_status(req, "approved", action="approved", card=card, actor_type="user", actor_id=user.id)
        store.set_request_status(req, "sent_or_booked", action="booked", card=card, actor_type="user", actor_id=user.id)
        touch(card, "done")
        return {"booking": {"id": booking.id, "room": store.state().rooms[booking.room_id].name,
                            "period": booking.period}, "request": request_state(req)}


def instruct(user, card_id, body):
    with store._lock:
        card = in_scope(user, card_id)
        version(card, body.version)
        req = store.state().requests.get(card.request_id)
        if card.kind != "director_report" or card.status not in ("pending", "in_review") or req.status != "escalated":
            raise ApiError(409, "INVALID_TRANSITION")
        record(card, user, "instruct", reason_text=body.instruction)
        touch(card, "done")
        reply = next(c for c in reversed(store.cards_of(req.id)) if c.kind == "reply_draft")
        store.set_request_status(req, "awaiting_review", action="instructed", card=reply, actor_type="user", actor_id=user.id)
        return result(card, req)


def reassign(user, card_id, body):
    with store._lock:
        card = in_scope(user, card_id)
        target = store.get_user(body.assignee_id)
        if target is None or target.org_id != user.org_id or target.role != "teacher" or not target.is_active:
            store.deny(user)
        if card.kind == "director_report" or card.status in ("done", "rejected"):
            raise ApiError(409, "INVALID_TRANSITION")
        previous, card.assignee_id = card.assignee_id, target.id
        req = store.state().requests.get(card.request_id)
        if req:
            req.assignee_id = target.id
        if card.status == "unassigned":
            card.status = "pending"
        touch(card)
        store.add_event(req, "reassigned", card=card, actor_type="user", actor_id=user.id,
                        **{"from": previous, "to": target.id, "reason": body.reason})
        return {"card": {"assignee": {"id": target.id, "display_name": target.display_name}, "version": card.version}}


def rule_decision(user, rule_id, body):
    with store._lock:
        rule = store.state().rules.get(rule_id)
        if rule is None or rule.org_id != user.org_id or rule.owner_id != user.id:
            store.deny(user)
        if rule.status != "proposed":
            raise ApiError(409, "INVALID_TRANSITION")
        rule.status = "active" if body.decision == "activate" else "declined"
        rule.decided_at = store.now()
        card = next(c for c in store.state().cards.values() if c.subject_id == rule.id)
        record(card, user, "approve" if body.decision == "activate" else "reject", reason_code=rule.reason_code)
        touch(card, "done")
        store.add_event(None, "approved" if body.decision == "activate" else "rejected", card=card,
                        actor_type="user", actor_id=user.id)
        return {"rule": {"id": rule.id, "status": rule.status}}


def stream(user, card_id):
    from app.api.streams import stream as replay
    card = in_scope(user, card_id)
    return replay(store.get_request(card.request_id), card)
