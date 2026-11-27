"""받은함 필터·상세·원장 현황."""

from collections import Counter
from datetime import timedelta

from app.api.labels import note_batch_label, staff_label
from app.mock import cards, documents, notes, store

FILTERS = ("unassigned", "needs_review", "uncertain", "on_hold", "in_progress", "done")


def inbox_filter(card):
    req = store.state().requests.get(card.request_id)
    # 회신 카드는 발송 뒤 done이어도 민원의 확인·처리 완료 차례를 계속 표시한다.
    waiting_completion = req and req.type == "complaint" and req.status == "sent_or_booked" and card.kind == "reply_draft" and card.status != "rejected"
    if (card.status in ("rejected", "done") and not waiting_completion) or (req and req.status in ("completed", "rejected")):
        return "done"
    if card.status == "on_hold" or (req and req.status == "on_hold"):
        return "on_hold"
    if card.assignee_id is None:
        return "unassigned"
    if req and req.status == "escalated" and card.kind == "reply_draft":
        return "in_progress"
    if req and req.risk_level == "uncertain":
        return "uncertain"
    if (req and (req.status in ("awaiting_review", "escalated") or (waiting_completion and req.parent_confirmed_at))) or req is None:
        return "needs_review"
    return "in_progress"


def person(user_id):
    user = store.get_user(user_id)
    return {"id": user.id, "display_name": user.display_name} if user else None


def requester_fields(req):
    child = store.state().children.get(req.child_id) if req else None
    requester = store.get_user(req.requester_id) if req else None
    return {"child_id": req.child_id if req else None,
            "child_name": child.display_name if child else None,
            "requester_name": requester.display_name if requester else None}


def staff_request(req, card_kind=None):
    from app.mock.request_actions import source_note
    return {k: getattr(req, k) for k in ("id", "type", "title", "body", "status", "risk_level", "risk_category",
                                        "parent_confirmed_at", "classroom_id", "created_at", "updated_at")} | {
        **requester_fields(req),
        "source_note": source_note(req),
        "repeat_count": store.repeat_count(req), "missing_fields": req.missing_fields,
        "status_label": staff_label(req.status, req.type, card_kind=card_kind), "hold_until": store.hold_until_of(req.id)}


def item(card):
    req = store.state().requests.get(card.request_id)
    classroom = store.state().classrooms.get(cards.classroom_of(card))
    check = card.check_result
    note_batch = notes.batch_view(card.subject_id, card.org_id) if card.subject_type == "daily_note_batch" else None
    return {"id": card.id, "kind": card.kind, "status": card.status, "version": card.version,
            **requester_fields(req),
            "status_label": staff_label(req.status, req.type, card_kind=card.kind) if req else note_batch_label(card.status, note_batch["draft_status"], card.draft.get("validation_result"))
            if note_batch else "확인 필요" if card.status == "pending" else "완료",
            "note_batch": note_batch,
            "request_id": card.request_id, "request_type": req.type if req else None,
            "title": req.title if req else card.draft.get("summary", ""), "urgency": req.urgency if req else None,
            "risk_level": req.risk_level if req else None,
            "risk_category": req.risk_category if req and req.risk_level == "urgent" else None,
            "is_urgent": bool(req and req.risk_level == "urgent"), "repeat_count": store.repeat_count(req) if req else None,
            "check": {"passed": check["passed"], "issue_count": len(check.get("issues", []))} if check else None,
            "parent_choice_count": sum(s.status == "chosen_by_parent" for s in store.state().slots.values()
                                       if s.card_id == card.id) if card.kind == "consult_slots" else None,
            "classroom": {"id": classroom.id, "name": classroom.name} if classroom else None, "assignee": person(card.assignee_id),
            "due_at": card.due_at, "is_delayed": bool(card.due_at and card.due_at < store.now()), "hold_until": card.hold_until}


def listing(user, filter, request_type, risk_level, kind, assignee, page, size):
    with store._lock:
        store.expire()
        candidates = []
        for card in store.state().cards.values():
            if not cards.visible_to(user, card):
                continue
            row = item(card)
            if ((risk_level and row["risk_level"] != risk_level)
                    or (kind and card.kind != kind) or (assignee and card.assignee_id != user.id)):
                continue
            candidates.append(card)
        type_selected = [c for c in candidates if inbox_filter(c) == filter] if filter else [c for c in candidates if inbox_filter(c) != "done"]
        type_counts = {key: sum(store.state().requests[c.request_id].type == key for c in type_selected if c.request_id)
                       for key in ("complaint", "consultation", "inquiry")}
        type_counts["all"] = len(type_selected)
        if request_type and request_type != "all":
            candidates = [c for c in candidates if c.request_id and store.state().requests[c.request_id].type == request_type]
        counts = Counter(inbox_filter(c) for c in candidates)
        selected = [c for c in candidates if inbox_filter(c) == filter] if filter else [c for c in candidates if inbox_filter(c) != "done"]
        selected.sort(key=lambda c: (not item(c)["is_urgent"], c.due_at is None, c.due_at or store.now(), str(c.id)))
        return {"items": [item(c) for c in selected[(page-1)*size:page*size]], "total": len(selected), "page": page,
                "size": size, "counts": {key: counts[key] for key in FILTERS}, "type_counts": type_counts}


def detail(user, card_id):
    with store._lock:
        card = cards.in_scope(user, card_id)
        req = store.state().requests.get(card.request_id)
        evidence = documents.evidence(card)
        warnings = []
        if any(not e["is_current"] for e in evidence):
            warnings.append("stale_evidence")
        if (not evidence and not card.draft.get("note_evidence")) or card.draft.get("no_evidence"):
            warnings.append("no_evidence")
        if card.draft.get("law_unchecked"):
            warnings.append("law_unchecked")
        if card.check_result is None:
            warnings.append("check_unavailable")
        if card.draft.get("notify_failed"):
            warnings.append("notify_failed")
        instructions = [a for a in store.state().approvals if a.decision == "instruct"
                        and store.state().cards[a.card_id].request_id == card.request_id] if req else []
        instruction = instructions[-1] if instructions and card.kind != "director_report" else None
        rule = store.state().rules.get(card.subject_id) if card.kind == "rule_proposal" else None
        note_batch = notes.batch_view(card.subject_id, card.org_id) if card.subject_type == "daily_note_batch" else None
        return {"card": {k: getattr(card, k) for k in ("id", "kind", "status", "version", "draft", "check_result", "check_attempts")}
                        | {"summary": card.draft.get("summary", ""), "note_batch": note_batch,
                           "status_label": note_batch_label(card.status, note_batch["draft_status"], card.draft.get("validation_result")) if note_batch else None},
                "request": staff_request(req, card.kind) if req else None,
                "evidence": evidence, "warnings": warnings,
                "messages": [{"id": m.id, "sender_type": m.sender_type, "sender_role": m.sender_role,
                              "body": m.body, "created_at": m.created_at}
                             for m in store.messages_of(req.id)] if req else [],
                "parent_choices": [{"slot_id": s.id, "period": s.period, "room": store.state().rooms[s.room_id].name,
                                    "chosen_at": s.chosen_at, "hold_expires_at": s.chosen_at + timedelta(hours=24)}
                                   for s in store.state().slots.values() if s.card_id == card.id and s.status == "chosen_by_parent"],
                "rule": {k: getattr(rule, k) for k in ("id", "reason_code", "rule_text", "status")} if rule else None,
                "director_instruction": {"text": instruction.reason_text, "by": person(instruction.decided_by),
                                         "at": instruction.created_at} if instruction else None,
                "timeline": [e.__dict__ for e in store.state().events if (req and e.request_id == req.id) or e.card_id == card.id]}


def overview(user):
    with store._lock:
        store.expire()
        all_cards = [c for c in store.state().cards.values() if c.org_id == user.org_id]
        waiting = [c for c in all_cards if c.status in ("pending", "in_review", "on_hold")]
        completed = {c.request_id for c in all_cards if c.status == "done" and c.closed_at
                     and c.closed_at >= store.now() - timedelta(days=30) and c.request_id}
        unconfirmed = [store.state().requests[rid] for rid in completed]
        return {"unassigned": sum(inbox_filter(c) == "unassigned" for c in all_cards), "waiting": len(waiting),
                "delayed": sum(bool(c.due_at and c.due_at < store.now()) for c in waiting),
                "done_today": sum(c.status == "done" and c.closed_at is not None and c.closed_at.date() == store.now().date() for c in all_cards),
                "completed_unconfirmed": sum(r.type == "complaint" and r.status == "completed" and r.parent_confirmed_at is None for r in unconfirmed),
                "reassignments": [{"card_id": e.card_id, **e.detail, "at": e.created_at} for e in store.state().events
                                  if e.org_id == user.org_id and e.action == "reassigned"], "eval": []}
