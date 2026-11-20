"""API 22~26·30. 입력 잠금 → 아이별 잠금 순서를 발송·수정이 함께 쓴다."""

import json
from datetime import datetime

from sqlalchemy import text

from app.core import scope
from app.core.db import transaction
from app.core.errors import ApiError
from app.core.schedule import KST, deliver_after, due_at

input_in_scope = scope.note_input_in_scope


def classroom_children(user, classroom_id):
    scope.classroom_in_scope(user, classroom_id)
    with transaction() as connection:
        items = connection.execute(text("""
            SELECT id, display_name, classroom_id FROM children
            WHERE org_id=:org AND classroom_id=:class ORDER BY display_name, id
        """), {"org": user.org_id, "class": classroom_id}).mappings().all()
    return {"items": [dict(row) for row in items]}


def draft_view(entry):
    return {"input_id": entry["id"], "draft_status": entry["draft_status"],
            "error": {"code": "UPSTREAM_UNAVAILABLE", "message": "모델 응답이 없어 초안을 만들지 못했어요."}
            if entry["draft_status"] == "failed" else None}


def draft(user, body, background_tasks):
    children = classroom_children(user, body.classroom_id)["items"]
    child_ids = {child["id"] for child in children}
    for memo in body.child_memos:
        if memo.child_id not in child_ids:
            raise ApiError(422, "VALIDATION_FAILED", child_id=memo.child_id)
    with transaction() as connection:
        values = {"org": user.org_id, "class": body.classroom_id, "date": body.note_date,
                  "activities": body.activities, "supplies": body.supplies, "author": user.id,
                  "memos": json.dumps([m.model_dump(mode="json") for m in body.child_memos])}
        entry = connection.execute(text("""
            INSERT INTO daily_note_inputs (org_id, classroom_id, note_date, activities, supplies, author_id, child_memos)
            VALUES (:org, :class, :date, :activities, :supplies, :author, CAST(:memos AS jsonb))
            ON CONFLICT (classroom_id, note_date) DO NOTHING RETURNING *
        """), values).mappings().one_or_none()
        created = entry is not None
        if created:
            connection.execute(text("""
                INSERT INTO cards (org_id, subject_type, subject_id, kind, status, assignee_id, draft, due_at)
                VALUES (:org, 'daily_note_batch', :input, 'daily_note', 'pending', :author,
                        '{"summary": "반 알림장 확인"}', :due)
            """), {**values, "input": entry["id"], "due": due_at(datetime.now(KST), kind="daily_note")})
        else:
            entry = connection.execute(text("""
                SELECT * FROM daily_note_inputs WHERE org_id=:org AND classroom_id=:class AND note_date=:date
            """), values).mappings().one()
    if created:
        from app.modules.daily_notes.runner import run_daily_note_drafts
        background_tasks.add_task(run_daily_note_drafts, entry["id"])
    return draft_view(entry), created


def view(note):
    return {name: note[name] for name in ("id", "child_id", "note_date", "status", "content",
                                         "open_checks", "confirmed_at", "sent_at")}


def list_notes(user, note_date, classroom_id, page, size, sort):
    if user.role == "teacher" and classroom_id is None:
        raise ApiError(422, "VALIDATION_FAILED", fields=[{"field": "classroom_id", "problem": "담임은 반을 골라 주세요"}])
    if classroom_id is not None and user.role != "parent":
        scope.classroom_in_scope(user, classroom_id)
    conditions = "n.org_id=:org AND n.note_date=:date"
    if classroom_id is not None:
        conditions += " AND i.classroom_id=:class"
    if user.role == "parent":
        conditions += """ AND n.status='sent' AND EXISTS (
            SELECT 1 FROM child_guardians g
            WHERE (g.child_id, g.org_id)=(n.child_id, n.org_id) AND g.user_id=:user)"""
    query = """ FROM daily_notes n JOIN daily_note_inputs i
                ON (i.id, i.org_id, i.note_date)=(n.input_id, n.org_id, n.note_date)
                JOIN children c ON (c.id, c.org_id)=(n.child_id, n.org_id) WHERE """ + conditions
    direction = "DESC" if sort.startswith("-") else "ASC"
    values = {"org": user.org_id, "date": note_date, "class": classroom_id, "user": user.id,
              "limit": size, "offset": (page-1)*size}
    with transaction() as connection:
        total = connection.scalar(text("SELECT count(*)" + query), values)
        items = connection.execute(text("SELECT n.*" + query +
                                   f" ORDER BY n.created_at {direction}, c.created_at {direction},"
                                   f" c.id {direction}, n.id {direction} LIMIT :limit OFFSET :offset"),
                                   values).mappings().all()
    return {"items": [view(row) for row in items], "total": total, "page": page, "size": size}


def _check_sources(user, content, child_id):
    if content is None:
        return
    for line in content.items:
        if line.source.type == "request":
            request = scope.request_in_scope(user, line.source.request_id)
            if request["child_id"] != child_id:
                raise ApiError(422, "VALIDATION_FAILED", field="content.items[].source.request_id")
        if line.source.type == "document":
            with transaction() as connection:
                row = connection.execute(text("""
                    SELECT * FROM documents WHERE id=:id AND org_id=:org
                """), {"id": line.source.document_id, "org": user.org_id}).mappings().one_or_none()
                targets = connection.scalars(text("""
                    SELECT classroom_id FROM document_classrooms WHERE document_id=:id AND org_id=:org
                """), {"id": line.source.document_id, "org": user.org_id}).all()
                allowed = row is not None and (not targets or any(scope._classroom(connection, user, c) for c in targets))
            scope._checked(user, row, allowed, "document", line.source.document_id)
            if row["visibility"] not in ("parents", "all"):
                raise ApiError(422, "VALIDATION_FAILED", field="content.items[].source.document_id")


def patch(user, note_id, body):
    scoped = scope.note_in_scope(user, note_id)
    _check_sources(user, body.content, scoped["child_id"])
    with transaction() as connection:
        connection.execute(text("SELECT id FROM daily_note_inputs WHERE id=:id AND org_id=:org FOR UPDATE"),
                           {"id": scoped["input_id"], "org": user.org_id})
        note = connection.execute(text("SELECT * FROM daily_notes WHERE id=:id AND org_id=:org FOR UPDATE"),
                                  {"id": note_id, "org": user.org_id}).mappings().one()
        if note["status"] == "sent":
            raise ApiError(409, "INVALID_TRANSITION")
        if not set(body.resolved_checks).issubset({c["id"] for c in note["open_checks"]}):
            raise ApiError(409, "INVALID_TRANSITION", open_checks=note["open_checks"])
        remaining = [c for c in note["open_checks"] if c["id"] not in body.resolved_checks]
        if body.confirm and remaining:
            raise ApiError(409, "INVALID_TRANSITION", open_checks=remaining)
        updated = connection.execute(text("""
            UPDATE daily_notes SET content=CAST(:content AS jsonb), open_checks=CAST(:checks AS jsonb),
                status=:status, confirmed_by=:actor, confirmed_at=:at
            WHERE id=:id AND org_id=:org RETURNING *
        """), {"id": note_id, "org": user.org_id, "checks": json.dumps(remaining),
               "content": json.dumps(body.content.model_dump(mode="json", exclude_none=True)
                                     if body.content is not None else note["content"]),
               "status": "ready" if body.confirm else ("needs_check" if remaining else "draft"),
               "actor": user.id if body.confirm else None, "at": datetime.now(KST) if body.confirm else None}).mappings().one()
    return {"note": view(updated)}


def send(user, body):
    scope.classroom_in_scope(user, body.classroom_id)
    with transaction() as connection:
        values = {"org": user.org_id, "class": body.classroom_id, "date": body.note_date}
        entry = connection.execute(text("""
            SELECT * FROM daily_note_inputs WHERE org_id=:org AND classroom_id=:class AND note_date=:date FOR UPDATE
        """), values).mappings().one_or_none()
        if entry is None:
            return {"sent_count": 0}
        if entry["draft_status"] != "succeeded":
            raise ApiError(409, "NOTE_BATCH_BLOCKED", blocked=[])
        values["input"] = entry["id"]
        selected = connection.execute(text("""
            SELECT * FROM daily_notes WHERE org_id=:org AND input_id=:input AND status<>'sent' ORDER BY id FOR UPDATE
        """), values).mappings().all()
        blocked = [{"note_id": n["id"], "child_id": n["child_id"], "open_checks": n["open_checks"]}
                   for n in selected if n["status"] != "ready" or n["open_checks"]]
        if blocked:
            raise ApiError(409, "NOTE_BATCH_BLOCKED", blocked=blocked)
        now = datetime.now(KST)
        for note in selected:
            connection.execute(text("UPDATE daily_notes SET status='sent', sent_at=:now WHERE id=:id AND org_id=:org"),
                               {"id": note["id"], "org": user.org_id, "now": now})
            guardians = connection.execute(text("""
                SELECT u.id, u.role FROM child_guardians g JOIN users u ON (u.id, u.org_id)=(g.user_id, g.org_id)
                WHERE g.child_id=:child AND g.org_id=:org AND u.role='parent' AND u.is_active
            """), {"child": note["child_id"], "org": user.org_id}).mappings()
            for guardian in guardians:
                connection.execute(text("""
                    INSERT INTO notifications (org_id, recipient_id, subject_type, subject_id, kind, title,
                                               dedupe_key, deliver_after)
                    VALUES (:org, :recipient, 'daily_note', :note, 'note_sent', '오늘 알림장', :key, :after)
                    ON CONFLICT (dedupe_key) DO NOTHING
                """), {"org": user.org_id, "recipient": guardian["id"], "note": note["id"],
                       "key": f"daily_note:{note['id']}:{guardian['id']}",
                       "after": deliver_after(now, guardian["role"])})
        if selected:
            connection.execute(text("""
                UPDATE cards SET status='done', version=version+1, updated_at=:now, closed_at=:now
                WHERE org_id=:org AND subject_type='daily_note_batch' AND subject_id=:input AND status<>'done'
            """), {**values, "now": now})
    return {"sent_count": len(selected)}
