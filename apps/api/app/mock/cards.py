"""교직원 카드 결정. 판 검사부터 이력·알림까지 같은 잠금 안에서 처리한다."""

from uuid import uuid4

from app.core.errors import ApiError
from app.core.constants import REASSIGN_AFTER_INSTRUCTION
from app.core.request_rules import RECLASSIFY_TYPES
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
    return next(iter(store.classroom_ids_of(owner_id)), None)


def visible_to(user, card):
    return card.org_id == user.org_id and (user.role != "teacher" or card.assignee_id == user.id
            or (card.kind != "rule_proposal" and classroom_of(card) in store.classroom_ids_of(user.id)))


def in_scope(user, card_id):
    card = store.state().cards.get(card_id)
    if card is None or not visible_to(user, card):
        store.deny(user, req=store.state().requests.get(card.request_id) if card and card.org_id == user.org_id else None,
                   card=card if card and card.org_id == user.org_id else None)
    store.expire(card.request_id)
    return card


def close_reports(req):
    """DB 백엔드와 같이 요청이 끝날 때(예약 확정·반려) 열린 원장 보고 카드만 닫아요."""
    for report_card in store.cards_of(req.id):
        if report_card.kind == "director_report" and report_card.status not in ("done", "rejected"):
            touch(report_card, "done")


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


def decide(user, card_id, body, background_tasks=None):
    with store._lock:
        card = in_scope(user, card_id)
        if card.kind == "director_report" and user.role != "director":
            raise ApiError(403, "FORBIDDEN_ROLE")
        version(card, body.version)
        req = store.state().requests.get(card.request_id)
        decision = body.decision
        consultation_report = (req and req.type == "consultation" and card.kind == "director_report"
                               and req.status != "escalated")
        # T04 3.2: 민원 회신의 승인·완료는 교사가 한다. 원장은 지시·재배정(API 설계 4.2).
        if (user.role == "director" and req and req.type == "complaint" and card.kind == "reply_draft"
                and decision in ("approve", "edit_approve", "complete")):
            raise ApiError(403, "FORBIDDEN_ROLE")
        valid = req is not None and req.status not in ("completed", "rejected")
        if consultation_report:
            valid = valid and ((decision in ("hold", "acknowledge") and card.status in ("pending", "in_review"))
                               or (decision in ("resume", "acknowledge") and card.status == "on_hold"))
        elif decision == "acknowledge":
            valid = False
        elif decision == "complete":
            valid = (valid and card.kind == "reply_draft" and card.status == "done"
                     and req.type == "complaint" and req.status == "sent_or_booked")
        elif decision == "resume":
            valid = valid and card.status == "on_hold" and req.status == "on_hold"
        else:
            valid = valid and card.status in ("pending", "in_review") and req.status == "awaiting_review"
        if card.kind == "director_report" and not consultation_report and decision not in ("hold", "resume"):
            valid = False
        if decision in ("approve", "edit_approve") and card.kind != "reply_draft":
            valid = False
        # 판단 필요는 재분류로 풀 수 있는 문의·민원만 막아요. 상담은 시간 확정 흐름 그대로예요.
        if (req and req.risk_level == "uncertain" and req.type in RECLASSIFY_TYPES
                and decision not in ("hold", "resume", "escalate")):
            valid = False
        if not valid:
            raise ApiError(409, "INVALID_TRANSITION")
        if decision == "complete" and req.parent_confirmed_at is None and not body.reason_text:
            raise ApiError(409, "REASON_REQUIRED")
        content = body.edited_content if decision == "edit_approve" else card.draft
        if decision == "edit_approve" and card.draft.get("note_evidence"):
            content = {**content, "note_evidence": card.draft["note_evidence"]}
        if decision in ("approve", "edit_approve") and not content.get("text", "").strip():
            raise ApiError(409, "INVALID_TRANSITION")
        record(card, user, decision, body.reason_code, body.reason_text, body.edited_content)
        if decision in ("reject", "dismiss"):
            from app.mock.memories import remember_rejection
            remember_rejection(user, card, decision, body.reason_code, body.reason_text)
        actor = {"card": card, "actor_type": "user", "actor_id": user.id}
        next_card = None
        if consultation_report:
            card.hold_until = body.hold_until if decision == "hold" else None
            touch(card, {"hold": "on_hold", "resume": "pending", "acknowledge": "done"}[decision])
            store.add_event(req, {"hold": "held", "resume": "resumed", "acknowledge": "report_acknowledged"}[decision],
                            reason_text=body.reason_text, **actor)
        elif decision in ("approve", "edit_approve"):
            from app.mock.memories import remember_answer
            remember_answer(user, card, req, content)
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
            store.expire(req.id)
        elif decision == "dismiss":
            for slot in store.slots_of_request(req.id):
                if slot.card_id == card.id and slot.status == "chosen_by_parent":
                    slot.status = "discarded"
            store.set_request_status(req, "rejected", action="dismissed", reason_code=body.reason_code,
                                     reason_text=body.reason_text, **actor)
            touch(card, "rejected")
            close_reports(req)
        elif decision == "escalate":
            next_card = report(req)
            store.set_request_status(req, "escalated", action="escalated", reason="manual", **actor)
            touch(card)
        elif decision == "reject":
            touch(card, "rejected")
            store.set_request_status(req, "assigned", action="rejected", reason_code=body.reason_code,
                                     reason_text=body.reason_text, **actor)
            next_card = store._new_card(req, card.kind, card.assignee_id, dict(card.draft))
            next_card.check_result = card.check_result
            if card.kind == "reply_draft":  # 거절 뒤 재초안은 초안 없는 카드(API 5.7). 담임이 직접 써서 edit_approve
                next_card.draft["text"] = ""
                next_card.check_result = None
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
        if req is None or req.type not in RECLASSIFY_TYPES or req.status not in ("awaiting_review", "escalated"):
            raise ApiError(409, "INVALID_TRANSITION")
        previous = req.risk_level
        req.risk_level, req.risk_category = body.risk_level, body.risk_category if body.risk_level == "urgent" else None
        for related in store.cards_of(req.id):
            related.due_at = due_at(req.created_at, req.type, req.risk_level, related.kind)
        reports = [c for c in store.cards_of(req.id) if c.kind == "director_report"
                   and c.status not in ("done", "rejected")]
        if previous != "urgent" and body.risk_level == "urgent":
            for reply in store.cards_of(req.id):
                if reply.kind == "reply_draft" and reply.status not in ("done", "rejected"):
                    reply.draft["text"] = ""
                    reply.check_result = None
                    if reply.id != card.id:
                        touch(reply)
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
            store.set_request_status(req, "escalated", action="escalated", card=report_card, actor_type="user", actor_id=user.id,
                                     reason="manual")
        from app.mock.card_views import staff_request
        return {"request": staff_request(req)}


def book(user, card_id, body):
    with store._lock:
        card = in_scope(user, card_id)
        if user.role != "teacher" or card.assignee_id != user.id:
            raise ApiError(403, "FORBIDDEN_ROLE")
        version(card, body.version)
        req = store.state().requests.get(card.request_id)
        slot = store.state().slots.get(body.slot_id)
        if slot is None or slot.card_id != card.id:
            store.deny(user)
        if card.kind != "consult_slots" or req.status == "escalated":
            raise ApiError(409, "INVALID_TRANSITION")
        if slot.status != "chosen_by_parent":
            raise ApiError(409, "SLOT_NOT_CHOSEN")
        if req.status != "awaiting_review" or card.status != "pending":
            raise ApiError(409, "INVALID_TRANSITION")
        if slot.period["start"] <= store.now():
            raise ApiError(409, "SLOT_PAST")
        if store.slot_conflicts(req.org_id, slot.teacher_id, slot.room_id, slot.period) or any(
                b.status == "confirmed" and b.request_id == req.id for b in store.state().bookings.values()):
            slot.status = "discarded"
            round_no = max(s.round for s in store.slots_of_request(req.id) if s.card_id == card.id) + 1
            candidates = store._propose_slots(card, card.assignee_id, round_no)
            touch(card)
            store.set_request_status(req, "needs_info", action="slot_conflict_reproposed", card=card,
                                     actor_type="user", actor_id=user.id, slot_id=slot.id,
                                     new_slot_ids=[candidate.id for candidate in candidates])
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
        close_reports(req)
        return {"booking": {"id": booking.id, "room": store.state().rooms[booking.room_id].name,
                            "period": booking.period}, "request": request_state(req)}


def instruct(user, card_id, body):
    with store._lock:
        card = in_scope(user, card_id)
        version(card, body.version)
        req = store.state().requests.get(card.request_id)
        if card.kind != "director_report" or card.status not in ("pending", "in_review") or req.status != "escalated":
            raise ApiError(409, "INVALID_TRANSITION")
        kind = "consult_slots" if req.type == "consultation" else "reply_draft"
        reply = next((c for c in reversed(store.cards_of(req.id)) if c.kind == kind
                      and c.status in ("pending", "in_review", "unassigned")), None)
        if reply is None:
            raise ApiError(409, "INVALID_TRANSITION")
        record(card, user, "instruct", reason_text=body.instruction)
        touch(card, "done")
        store.set_request_status(req, "awaiting_review", action="instructed", card=reply, actor_type="user", actor_id=user.id)
        response = result(card, req)
        if reply.assignee_id is None:
            response.update(next_action="reassign", message=REASSIGN_AFTER_INSTRUCTION)
        return response


def reassign(user, card_id, body):
    with store._lock:
        card = in_scope(user, card_id)
        target = store.get_user(body.assignee_id)
        if target is None or target.org_id != user.org_id or target.role != "teacher" or not target.is_active:
            store.deny(user)
        if card.kind in ("director_report", "rule_proposal") or card.status in ("done", "rejected"):
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
        if req and card.kind == "consult_slots" and store.confirmed_booking_of(req.id) is None:
            slots = [s for s in store.slots_of_request(req.id) if s.card_id == card.id
                     and s.status in ("proposed", "chosen_by_parent")]
            discarded = [s for s in slots if store.slot_conflicts(card.org_id, target.id, s.room_id, s.period)]
            reset = any(s.status == "chosen_by_parent" for s in discarded)
            for slot in slots:
                if slot in discarded:
                    slot.status = "discarded"
                else:
                    slot.teacher_id = target.id
                    if reset:
                        slot.status, slot.chosen_at = "proposed", None
            if discarded or not slots:
                round_no = max((s.round for s in store.slots_of_request(req.id) if s.card_id == card.id), default=0) + 1
                remaining = len(discarded) if slots else 3
                while remaining:
                    candidates = store._propose_slots(card, target.id, round_no, count=min(remaining, 3))
                    if not candidates:
                        break
                    remaining -= len(candidates)
                    round_no += 1
            if reset or not slots:
                store.set_request_status(req, "needs_info", action="info_requested", card=card)
        return {"card": {"assignee": {"id": target.id, "display_name": target.display_name}, "version": card.version}}


def rule_decision(user, rule_id, body):
    with store._lock:
        rule = store.state().rules.get(rule_id)
        if rule is None or rule.org_id != user.org_id or rule.owner_id != user.id:
            store.deny(user)
        if body.decision == "off":
            if rule.status != "active":
                raise ApiError(409, "INVALID_TRANSITION")
            rule.status, rule.decided_at = "off", store.now()
            return {"rule": {"id": rule.id, "status": rule.status}}
        if rule.status != "proposed":
            raise ApiError(409, "INVALID_TRANSITION")
        card = next((c for c in store.state().cards.values() if c.org_id == user.org_id
                     and c.subject_type == "memory_rule" and c.subject_id == rule.id and c.kind == "rule_proposal"), None)
        if card is None or card.status not in ("pending", "in_review"):
            raise ApiError(409, "INVALID_TRANSITION")
        rule.status = "active" if body.decision == "activate" else "declined"
        rule.decided_at = store.now()
        record(card, user, "approve" if body.decision == "activate" else "reject", reason_code=rule.reason_code)
        touch(card, "done")
        store.add_event(None, "approved" if body.decision == "activate" else "rejected", card=card,
                        actor_type="user", actor_id=user.id)
        return {"rule": {"id": rule.id, "status": rule.status}}


def stream(user, card_id):
    from app.api.streams import stream as replay
    card = in_scope(user, card_id)
    return replay(store.get_request(card.request_id), card)
