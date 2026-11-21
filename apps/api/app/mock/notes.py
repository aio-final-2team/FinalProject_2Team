"""반 알림장 초안·확인·일괄 발송."""

from copy import deepcopy
from datetime import datetime
from uuid import uuid4

from app.core.errors import ApiError
from app.core.care import note_content
from app.core.config import settings
from app.core.schedule import KST, due_at
from app.mock import seed, store
from app.mock.records import NoteInput, Note


def input_in_scope(user, input_id):
    entry = store.state().note_inputs.get(input_id)
    if entry is None or entry.org_id != user.org_id:
        store.deny(user)
    store.classroom_in_scope(user, entry.classroom_id)
    return entry


def record(note, action, *, actor_id=None, from_status=None, **detail):
    store.add_event(None, action, org_id=note.org_id, daily_note_id=note.id,
                    actor_type="user" if actor_id else "agent", actor_id=actor_id,
                    from_status=from_status, to_status=note.status, **detail)


def _edited(note):
    return note.content != note.ai_original or any(
        e.daily_note_id == note.id and e.action == "daily_note_edited" for e in store.state().events)


def regenerate(user, input_id, background_tasks=None):
    with store._lock:
        entry = input_in_scope(user, input_id)
        if any(n.input_id == input_id and n.status == "sent" for n in store.state().notes.values()):
            raise ApiError(409, "INVALID_TRANSITION")
        kept_edited = sum(n.input_id == input_id and n.status in ("draft", "needs_check") and _edited(n)
                          for n in store.state().notes.values())
        card = next(c for c in store.state().cards.values() if c.subject_type == "daily_note_batch" and c.subject_id == input_id)
        started_at = datetime.fromisoformat(card.draft["draft_started_at"]) if card.draft.get("draft_started_at") else entry.created_at
        if (entry.draft_status in ("queued", "running") and
                (store.now() - started_at).total_seconds() < settings.daily_note_writer_timeout):
            return {**draft_view(entry), "kept_edited": kept_edited}
        card.draft.update(draft_started_at=store.now().isoformat(), regenerated_by=str(user.id))
        entry.draft_status = "failed" if "[실패]" in entry.activities else "succeeded"
        if entry.draft_status == "succeeded":
            _generate(entry, store.classroom_children(user, entry.classroom_id), regenerated_by=str(user.id))
        return {**draft_view(entry), "kept_edited": kept_edited}


def requests_for_child(child, note_date):
    """입구 함수의 children[].requests: 같은 원·반·아이의 그날 보호자 요청."""
    requests = [req for req in store.state().requests.values()
                if req.org_id == child.org_id and req.classroom_id == child.classroom_id
                and req.child_id == child.id and req.requester_id in child.guardian_ids
                and req.type in ("medication", "pickup", "inquiry")
                and req.created_at.astimezone(KST).date() == note_date]
    return [{"request_id": req.id, "type": req.type, "text": req.body}
            for req in sorted(requests, key=lambda req: (req.created_at, str(req.id)))]


def draft(user, body, background_tasks=None):
    with store._lock:
        children = store.classroom_children(user, body.classroom_id)
        child_ids = {child.id for child in children}
        for memo in body.child_memos:
            if memo.child_id not in child_ids:
                raise ApiError(422, "VALIDATION_FAILED", child_id=memo.child_id)
        existing = next((i for i in store.state().note_inputs.values() if i.classroom_id == body.classroom_id
                         and i.note_date == body.note_date), None)
        if existing:
            return draft_view(existing), False
        failed = "[실패]" in body.activities
        entry = NoteInput(uuid4(), user.org_id, body.classroom_id, body.note_date, body.activities, body.supplies,
                          user.id, "failed" if failed else "succeeded",
                          child_memos=[memo.model_dump() for memo in body.child_memos])
        store.state().note_inputs[entry.id] = entry
        card = store.Card(uuid4(), user.org_id, None, "daily_note", assignee_id=user.id,
                          subject_type="daily_note_batch", subject_id=entry.id, draft={"summary": "반 알림장 확인"},
                          due_at=due_at(store.now(), kind="daily_note"))
        store.state().cards[card.id] = card
        if failed:
            store.add_event(None, "tool_failed", card=card, input_id=entry.id, code="UPSTREAM_UNAVAILABLE",
                            message="모델 응답이 없어 초안을 만들지 못했어요.")
        else:
            _generate(entry, children)
            store.add_event(None, "drafted", card=card)
        return draft_view(entry), True


def _generate(entry, children, *, regenerated_by=None):
    menu = next(d for d in store.state().documents.values() if d.org_id == entry.org_id and d.doc_type == "menu" and d.status == "active")
    meal = next(c.content for c in store.state().chunks.values() if c.document_id == menu.id)
    memos = {memo["child_id"]: memo["memo"] for memo in entry.child_memos}
    for index, child in enumerate(children):
        existing = next((n for n in store.state().notes.values() if n.input_id == entry.id and n.child_id == child.id), None)
        if existing is not None and (existing.status in ("ready", "sent") or _edited(existing)):
            continue
        checks = [{"id": "c1", "item_key": "supplies", "kind": "date_check",
                   "problem": "준비물 날짜를 확인해 주세요", "sentence": entry.supplies}] if index == 0 else []
        content = {"items": [
            {"key": "day", "label": "오늘 하루", "value": entry.activities, "source": {"type": "teacher_input"}},
            {"key": "supplies", "label": "준비물", "value": entry.supplies, "source": {"type": "teacher_input"}},
            {"key": "meal", "label": "식사", "value": meal, "source": {"type": "document", "document_id": menu.id, "document_title": menu.title}}]}
        memo = memos.get(child.id, "")
        if memo.strip():
            content["items"].append({"key": "child", "label": "아이 메모", "value": memo,
                                     "source": {"type": "teacher_input"}})
        for req in requests_for_child(child, entry.note_date):
            key = req["type"]
            # 누락 확인 시연은 이 고정 요청 하나만 빼요. 실제 귀가 요청 전체를 빼지 않아요.
            if req["request_id"] == seed.REQUEST_PICKUP:
                checks.append({"id": f"request-{req['request_id']}", "item_key": key,
                               "kind": "request_missed", "problem": "보호자 요청을 초안에 반영해 주세요",
                               "sentence": None, "request_id": req["request_id"]})
            else:
                content["items"].append({"key": key, "label": "보호자 요청", "value": req["text"],
                                         "source": {"type": "request", "request_id": req["request_id"]}})
        note = Note(uuid4(), entry.org_id, entry.id, child.id, entry.note_date, content,
                    "needs_check" if checks else "draft", checks)
        previous_status = existing.status if existing else None
        if existing is not None:
            checks = [{**c, "id": str(uuid4())} for c in checks]
            existing.content, existing.open_checks, existing.status = content, checks, note.status
            existing.ai_original = deepcopy(content)
            note = existing
        store.state().notes[note.id] = note
        record(note, "daily_note_drafted", from_status=previous_status,
               **({"regenerated_by": regenerated_by} if regenerated_by else {}))


def draft_view(entry):
    ev = next((e for e in store.state().events if e.action == "tool_failed" and e.detail.get("input_id") == entry.id), None)
    return {"input_id": entry.id, "draft_status": entry.draft_status,
            "error": {k: ev.detail[k] for k in ("code", "message")} if ev and entry.draft_status == "failed" else None}


def patch(user, note_id, body):
    with store._lock:
        note = store.state().notes.get(note_id)
        if note is None or note.org_id != user.org_id:
            store.deny(user)
        input_in_scope(user, note.input_id)
        if note.status == "sent":
            raise ApiError(409, "INVALID_TRANSITION")
        if not set(body.resolved_checks).issubset({c["id"] for c in note.open_checks}):
            # 저장된 확인 항목과 대조해야 아는 조건이라 형식 오류(422)가 아니라 서버 검사(409)다(API 설계 4.1)
            raise ApiError(409, "INVALID_TRANSITION", open_checks=note.open_checks)
        remaining = [c for c in note.open_checks if c["id"] not in body.resolved_checks]
        if body.confirm and remaining:
            raise ApiError(409, "INVALID_TRANSITION", open_checks=remaining)
        previous_status = note.status
        previous_content = deepcopy(note.content)
        if body.content is not None:
            for line in body.content.items:
                if line.source.type == "document":
                    from app.mock.documents import in_scope
                    document = in_scope(user, line.source.document_id)
                    if document.visibility not in ("parents", "all"):
                        raise ApiError(422, "VALIDATION_FAILED", field="content.items[].source.document_id")
                if line.source.type == "request":
                    request = store.request_in_scope(user, line.source.request_id)
                    if request.child_id != note.child_id or (
                            line.key in ("medication", "pickup") and request.type != line.key):
                        raise ApiError(422, "VALIDATION_FAILED", field="content.items[].source.request_id")
            note.content = body.content.model_dump(exclude_none=True)
        note.open_checks = remaining
        note.status = "needs_check" if remaining else "draft"
        note.confirmed_at = note.confirmed_by = None
        if body.confirm:
            note.status, note.confirmed_at, note.confirmed_by = "ready", store.now(), user.id
        if note.content != previous_content:
            record(note, "daily_note_edited", actor_id=user.id, from_status=previous_status)
        if previous_status == "ready" and note.status != "ready":
            record(note, "returned", actor_id=user.id, from_status="ready")
        if previous_status == "needs_check" and note.status == "draft":
            record(note, "checked", actor_id=user.id, from_status="needs_check")
        if body.confirm:
            record(note, "daily_note_confirmed", actor_id=user.id, from_status=previous_status)
        return {"note": view(note)}


def view(note):
    result = {k: deepcopy(getattr(note, k)) for k in ("id", "child_id", "note_date", "status", "content", "open_checks", "confirmed_at", "sent_at")}
    result["content"] = note_content(note.content, {str(r.id): r.__dict__ for r in store.state().requests.values()
                                                  if r.org_id == note.org_id and r.child_id == note.child_id})
    return result


def visible(user, note_date, classroom_id=None):
    if user.role == "teacher" and classroom_id is None:
        raise ApiError(422, "VALIDATION_FAILED", fields=[{"field": "classroom_id", "problem": "담임은 반을 골라 주세요"}])
    if classroom_id and user.role != "parent":
        store.classroom_in_scope(user, classroom_id)
    items = [n for n in store.state().notes.values() if n.org_id == user.org_id and n.note_date == note_date]
    if user.role == "parent":
        child_ids = {c.id for c in store.children_of(user.id)}
        items = [n for n in items if n.child_id in child_ids and n.status == "sent"]
    if classroom_id:
        items = [n for n in items if store.state().note_inputs[n.input_id].classroom_id == classroom_id]
    return items


def classroom_children(user, classroom_id):
    with store._lock:
        children = store.classroom_children(user, classroom_id)
        return {"items": [{"id": c.id, "display_name": c.display_name, "classroom_id": c.classroom_id}
                          for c in sorted(children, key=lambda c: c.display_name)]}


def list_notes(user, note_date, classroom_id, page, size, sort):
    with store._lock:
        items = sorted(visible(user, note_date, classroom_id), key=lambda n: n.created_at,
                       reverse=sort.startswith("-"))
        return {"items": [view(n) for n in items[(page-1)*size:page*size]],
                "total": len(items), "page": page, "size": size}


def send(user, body):
    with store._lock:
        store.classroom_in_scope(user, body.classroom_id)
        entry = next((i for i in store.state().note_inputs.values() if i.org_id == user.org_id
                      and i.classroom_id == body.classroom_id and i.note_date == body.note_date), None)
        if entry is not None and entry.draft_status != "succeeded":
            raise ApiError(409, "NOTE_BATCH_BLOCKED", blocked=[])
        selected = [n for n in store.state().notes.values() if n.org_id == user.org_id and n.note_date == body.note_date
                    and store.state().note_inputs[n.input_id].classroom_id == body.classroom_id and n.status != "sent"]
        blocked = [{"note_id": n.id, "child_id": n.child_id, "open_checks": n.open_checks} for n in selected if n.status != "ready"]
        if blocked:
            raise ApiError(409, "NOTE_BATCH_BLOCKED", blocked=blocked)
        for note in selected:
            note.status, note.sent_at = "sent", store.now()
            card = next(c for c in store.state().cards.values() if c.subject_id == note.input_id)
            record(note, "daily_note_sent", actor_id=user.id, from_status="ready")
        if selected:
            from app.mock.cards import touch
            touch(card, "done")
        return {"sent_count": len(selected)}
