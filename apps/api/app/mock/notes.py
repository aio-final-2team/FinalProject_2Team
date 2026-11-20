"""반 알림장 초안·확인·일괄 발송."""

from copy import deepcopy
from uuid import uuid4

from app.core.errors import ApiError
from app.core.schedule import due_at
from app.mock import store
from app.mock.records import NoteInput, Note


def input_in_scope(user, input_id):
    entry = store.state().note_inputs.get(input_id)
    if entry is None or entry.org_id != user.org_id:
        store.deny(user)
    store.classroom_in_scope(user, entry.classroom_id)
    return entry


def draft(user, body):
    with store._lock:
        store.classroom_in_scope(user, body.classroom_id)
        existing = next((i for i in store.state().note_inputs.values() if i.classroom_id == body.classroom_id
                         and i.note_date == body.note_date), None)
        if existing:
            return draft_view(existing), False
        failed = "[실패]" in body.activities
        entry = NoteInput(uuid4(), user.org_id, body.classroom_id, body.note_date, body.activities, body.supplies,
                          user.id, "failed" if failed else "succeeded")
        store.state().note_inputs[entry.id] = entry
        card = store.Card(uuid4(), user.org_id, None, "daily_note", assignee_id=user.id,
                          subject_type="daily_note_batch", subject_id=entry.id, draft={"summary": "반 알림장 확인"},
                          due_at=due_at(store.now(), kind="daily_note"))
        store.state().cards[card.id] = card
        if failed:
            store.add_event(None, "tool_failed", card=card, input_id=entry.id, code="UPSTREAM_UNAVAILABLE",
                            message="모델 응답이 없어 초안을 만들지 못했어요.")
        else:
            menu = next(d for d in store.state().documents.values() if d.org_id == user.org_id and d.doc_type == "menu" and d.status == "active")
            meal = next(c.content for c in store.state().chunks.values() if c.document_id == menu.id)
            children = [c for c in store.state().children.values() if c.org_id == user.org_id and c.classroom_id == entry.classroom_id]
            for index, child in enumerate(children):
                checks = [{"id": "c1", "item_key": "supplies", "problem": "준비물 날짜를 확인해 주세요"}] if index == 0 else []
                content = {"items": [
                    {"key": "day", "label": "오늘 하루", "value": entry.activities, "source": {"type": "teacher_input"}},
                    {"key": "supplies", "label": "준비물", "value": entry.supplies, "source": {"type": "teacher_input"}},
                    {"key": "meal", "label": "식사", "value": meal, "source": {"type": "document", "document_id": menu.id, "document_title": menu.title}}]}
                note = Note(uuid4(), user.org_id, entry.id, child.id, entry.note_date, content,
                            "needs_check" if checks else "draft", checks)
                store.state().notes[note.id] = note
            store.add_event(None, "drafted", card=card)
        return draft_view(entry), True


def draft_view(entry):
    ev = next((e for e in store.state().events if e.action == "tool_failed" and e.detail.get("input_id") == entry.id), None)
    return {"input_id": entry.id, "draft_status": entry.draft_status,
            "error": {k: ev.detail[k] for k in ("code", "message")} if ev else None}


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
        if body.content is not None:
            for line in body.content.items:
                if line.source.type == "document":
                    from app.mock.documents import in_scope
                    in_scope(user, line.source.document_id)
                if line.source.type == "request":
                    store.request_in_scope(user, line.source.request_id)
            note.content = body.content.model_dump(exclude_none=True)
        note.open_checks = remaining
        note.status = "needs_check" if remaining else "draft"
        note.confirmed_at = note.confirmed_by = None
        if body.confirm:
            note.status, note.confirmed_at, note.confirmed_by = "ready", store.now(), user.id
        return {"note": view(note)}


def view(note):
    return {k: deepcopy(getattr(note, k)) for k in ("id", "child_id", "note_date", "status", "content", "open_checks", "confirmed_at", "sent_at")}


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


def send(user, body):
    with store._lock:
        store.classroom_in_scope(user, body.classroom_id)
        selected = [n for n in store.state().notes.values() if n.org_id == user.org_id and n.note_date == body.note_date
                    and store.state().note_inputs[n.input_id].classroom_id == body.classroom_id and n.status != "sent"]
        blocked = [{"note_id": n.id, "child_id": n.child_id, "open_checks": n.open_checks} for n in selected if n.status != "ready"]
        if blocked:
            raise ApiError(409, "NOTE_BATCH_BLOCKED", blocked=blocked)
        for note in selected:
            note.status, note.sent_at = "sent", store.now()
            card = next(c for c in store.state().cards.values() if c.subject_id == note.input_id)
            store.add_event(None, "sent", card=card, actor_type="user", actor_id=user.id, note_id=note.id)
        if selected:
            from app.mock.cards import touch
            touch(card, "done")
        return {"sent_count": len(selected)}
