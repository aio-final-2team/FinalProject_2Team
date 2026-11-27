"""API 22~26·30. 입력 잠금 → 아이별 잠금 순서를 발송·수정이 함께 쓴다."""

import json
from contextlib import nullcontext
from datetime import datetime
from uuid import uuid4

from sqlalchemy import text

from app.core import scope
from app.core.config import settings
from app.core.db import transaction
from app.core.photos import profile_view
from app.core.errors import ApiError
from app.core.consents import require_complete
from app.core.care import missed_request_check, note_content
from app.core.constants import LATE_NOTE_REQUEST_NOTICE, NOTE_REQUEST_TYPES, notification_title
from app.core.jobs import dispatch
from app.core.schedule import KST, deliver_after, due_at
from app.modules.daily_notes.events import edited_child_ids, record
from app.modules.daily_notes.runner import requeued
from app.modules.notifications.notifications import enqueue

input_in_scope = scope.note_input_in_scope


def reply(user, note_id, body, background_tasks, trace_id):
    from app.modules.requests.requests import create

    note = scope.note_in_scope(user, note_id)
    req, _ = create(user, background_tasks=background_tasks, client_request_id=str(uuid4()),
                    type="inquiry", body=body, child_id=note["child_id"], previous_request_id=None,
                    trace_id=trace_id, source_note_id=note_id)
    return {"request_id": req["id"]}


def supplies_check(user, note_id):
    with transaction() as connection:
        scope.note_in_scope(user, note_id, connection=connection)
        note = connection.execute(text("SELECT * FROM daily_notes WHERE id=:id FOR UPDATE"),
                                  {"id": note_id}).mappings().one()
        if not any(line["key"] == "supplies" and line["value"].strip() for line in note["content"]["items"]):
            raise ApiError(409, "INVALID_TRANSITION")
        at = connection.scalar(text("""
            UPDATE daily_notes SET supplies_checked_at=coalesce(supplies_checked_at,clock_timestamp())
            WHERE id=:id RETURNING supplies_checked_at
        """), {"id": note_id})
        return {"supplies_checked_at": at}


def batch_view(connection, input_id, org_id):
    entry = connection.execute(text("SELECT * FROM daily_note_inputs WHERE id=:id AND org_id=:org"),
                               {"id": input_id, "org": org_id}).mappings().one_or_none()
    if entry is None:
        return None
    children = connection.execute(text("""
        SELECT c.id AS child_id,c.display_name,n.id AS note_id,coalesce(n.status,'missing') AS status
        FROM children c LEFT JOIN daily_notes n
          ON (n.child_id,n.org_id,n.input_id)=(c.id,c.org_id,:id)
        WHERE c.org_id=:org AND c.classroom_id=:class ORDER BY c.display_name,c.id
    """), {"id": input_id, "org": entry["org_id"], "class": entry["classroom_id"]}).mappings()
    return {"input_id": input_id, "draft_status": entry["draft_status"], "children": [dict(c) for c in children]}


def request_received(connection, req, event):
    if req["type"] not in NOTE_REQUEST_TYPES:
        return
    entry = connection.execute(text("""
        SELECT * FROM daily_note_inputs WHERE org_id=:org AND classroom_id=:class AND note_date=:date FOR UPDATE
    """), {"org": req["org_id"], "class": req["classroom_id"],
           "date": req["created_at"].astimezone(KST).date()}).mappings().one_or_none()
    if entry is None:
        return
    note = connection.execute(text("""
        SELECT * FROM daily_notes WHERE input_id=:input AND child_id=:child AND org_id=:org FOR UPDATE
    """), {"input": entry["id"], "child": req["child_id"], "org": req["org_id"]}).mappings().one_or_none()
    if note is None:
        return
    if note["status"] != "sent":
        connection.execute(text("""
            UPDATE daily_notes SET open_checks=open_checks || CAST(:check AS jsonb),
                status='needs_check',confirmed_by=NULL,confirmed_at=NULL WHERE id=:id
        """), {"id": note["id"], "check": json.dumps([missed_request_check(req["type"], req["id"])])})
        if note["status"] == "ready":
            record(connection, {**note, "status": "needs_check"}, "returned", from_status="ready",
                   request_id=str(req["id"]))
    card = connection.execute(text("""
        SELECT * FROM cards WHERE org_id=:org AND subject_type='daily_note_batch' AND subject_id=:id
    """), {"org": req["org_id"], "id": entry["id"]}).mappings().one()
    enqueue(connection, {**event, "card_id": card["id"]}, req, card["assignee_id"], "new_card",
            LATE_NOTE_REQUEST_NOTICE, dedupe_key=f"late_note_request:{req['id']}:{card['id']}", subject_id=note["id"])


def classroom_children(user, classroom_id, *, connection=None):
    with (transaction() if connection is None else nullcontext(connection)) as connection:
        scope.classroom_in_scope(user, classroom_id, connection=connection)
        items = connection.execute(text("""
            SELECT id, display_name, classroom_id, profile_photo_path FROM children
            WHERE org_id=:org AND classroom_id=:class ORDER BY display_name, id
        """), {"org": user.org_id, "class": classroom_id}).mappings().all()
    return {"items": [{"id": row["id"], "display_name": row["display_name"], "classroom_id": row["classroom_id"],
                       "profile_photo": profile_view(row["id"], row["profile_photo_path"])} for row in items]}


def draft_view(entry):
    return {"input_id": entry["id"], "draft_status": entry["draft_status"],
            "error": {"code": "UPSTREAM_UNAVAILABLE", "message": "모델 응답이 없어 초안을 만들지 못했어요."}
            if entry["draft_status"] == "failed" else None}


def draft(user, body, background_tasks):
    with transaction() as connection:
        children = classroom_children(user, body.classroom_id, connection=connection)["items"]
        require_complete(user)
        child_ids = {child["id"] for child in children}
        for memo in body.child_memos:
            if memo.child_id not in child_ids:
                raise ApiError(422, "VALIDATION_FAILED", child_id=memo.child_id)
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
        dispatch("daily_note", entry["id"], background_tasks)
    return draft_view(entry), created


def view(note, *, connection=None, requests=None):
    result = {name: note[name] for name in ("id", "child_id", "note_date", "status", "content",
                                         "open_checks", "confirmed_at", "sent_at", "version", "corrected_at", "supplies_checked_at")}
    if requests is None:
        with (transaction() if connection is None else nullcontext(connection)) as connection:
            requests = {str(r["id"]): r for r in connection.execute(text(
                "SELECT id,type,status,child_id,source_note_id,body,created_at FROM requests WHERE org_id=:org AND child_id=:child"),
                {"org": note["org_id"], "child": note["child_id"]}).mappings()}
    result["content"] = note_content(note["content"], {key: r for key, r in requests.items()
                                                    if r["child_id"] == note["child_id"]})
    result["replies"] = [{"request_id": r["id"], **{k: r[k] for k in ("body", "status", "created_at")}}
                         for r in sorted(requests.values(), key=lambda r: (r["created_at"], r["id"]))
                         if r["source_note_id"] == note["id"] and r["child_id"] == note["child_id"]]
    return result


def regenerate(user, input_id, background_tasks):
    with transaction() as connection:
        input_in_scope(user, input_id, connection=connection)
        require_complete(user)
        values = {"id": input_id, "org": user.org_id}
        entry = connection.execute(text("SELECT * FROM daily_note_inputs WHERE id=:id AND org_id=:org FOR UPDATE"),
                                   values).mappings().one()
        if connection.scalar(text("""
            SELECT EXISTS (SELECT 1 FROM daily_notes WHERE input_id=:id AND org_id=:org AND status='sent')
        """), values):
            raise ApiError(409, "INVALID_TRANSITION")
        kept_edited = len(edited_child_ids(connection, input_id))
        card = connection.execute(text("""
            SELECT draft FROM cards WHERE subject_type='daily_note_batch' AND subject_id=:id AND org_id=:org
        """), values).scalar_one()
        started_at = datetime.fromisoformat(card["draft_started_at"]) if card.get("draft_started_at") else entry["created_at"]
        if (entry["draft_status"] in ("queued", "running") and
                (datetime.now(KST) - started_at).total_seconds() < settings.daily_note_writer_timeout):
            return {**draft_view(entry), "kept_edited": kept_edited}
        entry = connection.execute(text("""
            UPDATE daily_note_inputs SET draft_status='queued' WHERE id=:id AND org_id=:org RETURNING *
        """), values).mappings().one()
        requeued(connection, input_id, "user", user.id)
        connection.execute(text("""
            UPDATE cards SET draft=draft || CAST(:detail AS jsonb)
            WHERE subject_type='daily_note_batch' AND subject_id=:id AND org_id=:org
        """), {**values, "detail": json.dumps({"draft_started_at": datetime.now(KST).isoformat(),
                                               "regenerated_by": str(user.id)})})
    dispatch("daily_note", input_id, background_tasks)
    return {**draft_view(entry), "kept_edited": kept_edited}


def list_notes(user, note_date, classroom_id, page, size, sort):
    if user.role == "teacher" and classroom_id is None:
        raise ApiError(422, "VALIDATION_FAILED", fields=[{"field": "classroom_id", "problem": "담임은 반을 골라 주세요"}])
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
        if classroom_id is not None and user.role != "parent":
            scope.classroom_in_scope(user, classroom_id, connection=connection)
        total = connection.scalar(text("SELECT count(*)" + query), values)
        pending = None if user.role == "parent" else pending_medications(connection, user.org_id, note_date, classroom_id)
        if values["offset"] >= total:
            return {"items": [], "total": total, "page": page, "size": size, "pending_medication_count": pending}
        items = connection.execute(text("SELECT n.*" + query +
                                   f" ORDER BY n.created_at {direction}, c.created_at {direction},"
                                   f" c.id {direction}, n.id {direction} LIMIT :limit OFFSET :offset"),
                                   values).mappings().all()
        request_ids = list({str(line.get("source", {}).get("request_id")) for row in items
                            for line in row["content"]["items"] if line.get("source", {}).get("request_id")})
        requests = {str(r["id"]): r for r in connection.execute(text("""
            SELECT id,type,status,child_id,source_note_id,body,created_at FROM requests
            WHERE org_id=:org AND (id=ANY(CAST(:ids AS uuid[])) OR source_note_id=ANY(CAST(:notes AS uuid[])))
        """), {"org": user.org_id, "ids": request_ids, "notes": [str(n["id"]) for n in items]}).mappings()}
        return {"items": [{**view(row, requests=requests), "input_id": row["input_id"]} for row in items],
                "total": total, "page": page, "size": size, "pending_medication_count": pending}


def pending_medications(connection, org_id, note_date, classroom_id):
    """그날 들어온 투약 요청 중 아직 완료하지 않은 수. 알림장 발송은 막지 않고 화면 안내에만 써요."""
    start = datetime.combine(note_date, datetime.min.time(), KST)
    return connection.scalar(text("""
        SELECT count(*) FROM requests r
        WHERE r.org_id=:org AND r.type='medication' AND r.status IN ('received','assigned')
          AND (CAST(:class AS uuid) IS NULL OR r.classroom_id=CAST(:class AS uuid))
          AND r.created_at>=:start AND r.created_at<:start + interval '1 day'
          AND EXISTS (SELECT 1 FROM child_guardians g
                      WHERE (g.child_id,g.org_id,g.user_id)=(r.child_id,r.org_id,r.requester_id))
    """), {"org": org_id, "class": classroom_id, "start": start})


def _check_sources(user, content, child_id, connection):
    if content is None:
        return
    for line in content.items:
        if line.source.type == "request":
            request = scope.request_in_scope(user, line.source.request_id, connection=connection)
            if request["child_id"] != child_id or (
                    line.key in ("medication", "pickup") and request["type"] != line.key):
                raise ApiError(422, "VALIDATION_FAILED", field="content.items[].source.request_id")
        if line.source.type == "document":
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
    with transaction() as connection:
        scoped = scope.note_in_scope(user, note_id, connection=connection)
        _check_sources(user, body.content, scoped["child_id"], connection)
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
        if updated["content"] != note["content"]:
            record(connection, updated, "daily_note_edited", actor_id=user.id, from_status=note["status"])
        if note["status"] == "ready" and updated["status"] != "ready":
            record(connection, updated, "returned", actor_id=user.id, from_status="ready")
        if note["status"] == "needs_check" and updated["status"] == "draft":
            record(connection, updated, "checked", actor_id=user.id, from_status="needs_check")
        if body.confirm:
            record(connection, updated, "daily_note_confirmed", actor_id=user.id, from_status=note["status"])
        return {"note": view(updated, connection=connection)}


def _notify_guardians(connection, note, kind, dedupe_prefix, now):
    guardians = connection.execute(text("""
        SELECT u.id, u.role FROM child_guardians g JOIN users u ON (u.id, u.org_id)=(g.user_id, g.org_id)
        WHERE g.child_id=:child AND g.org_id=:org AND u.role='parent' AND u.is_active
    """), {"child": note["child_id"], "org": note["org_id"]}).mappings()
    for guardian in guardians:
        connection.execute(text("""
            INSERT INTO notifications (org_id, recipient_id, subject_type, subject_id, kind, title,
                                       dedupe_key, deliver_after)
            VALUES (:org, :recipient, 'daily_note', :note, :kind, :title, :key, :after)
            ON CONFLICT (dedupe_key) DO NOTHING
        """), {"org": note["org_id"], "recipient": guardian["id"], "note": note["id"],
               "kind": kind, "title": notification_title(kind), "key": f"{dedupe_prefix}:{guardian['id']}",
               "after": deliver_after(now, guardian["role"], user_id=guardian["id"])})


def correct(user, note_id, body):
    with transaction() as connection:
        scoped = scope.note_in_scope(user, note_id, connection=connection)
        connection.execute(text("SELECT id FROM daily_note_inputs WHERE id=:id AND org_id=:org FOR UPDATE"),
                           {"id": scoped["input_id"], "org": user.org_id})
        note = connection.execute(text("SELECT * FROM daily_notes WHERE id=:id AND org_id=:org FOR UPDATE"),
                                  {"id": note_id, "org": user.org_id}).mappings().one()
        if note["status"] != "sent":
            raise ApiError(409, "INVALID_TRANSITION")
        if note["version"] != body.version:
            raise ApiError(409, "CARD_VERSION_CONFLICT", current_version=note["version"])
        _check_sources(user, body.content, note["child_id"], connection)
        now = datetime.now(KST)
        updated = connection.execute(text("""
            UPDATE daily_notes SET content=CAST(:content AS jsonb), corrected_at=:now, version=version+1
            WHERE id=:id AND org_id=:org RETURNING *
        """), {"id": note_id, "org": user.org_id, "now": now,
               "content": json.dumps(body.content.model_dump(mode="json", exclude_none=True))}).mappings().one()
        record(connection, updated, "daily_note_corrected", actor_id=user.id, from_status="sent",
               reason_text=body.reason_text, version=updated["version"])
        _notify_guardians(connection, updated, "note_corrected",
                          f"daily_note_corrected:{note_id}:{updated['version']}", now)
        return {"note": view(updated, connection=connection)}


def send(user, body):
    with transaction() as connection:
        scope.classroom_in_scope(user, body.classroom_id, connection=connection)
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
        blocked.extend({"note_id": None, "child_id": c["child_id"], "status": "missing", "open_checks": []}
                       for c in batch_view(connection, entry["id"], user.org_id)["children"] if c["status"] == "missing")
        if blocked:
            raise ApiError(409, "NOTE_BATCH_BLOCKED", blocked=blocked)
        now = datetime.now(KST)
        for note in selected:
            connection.execute(text("UPDATE daily_notes SET status='sent', sent_at=:now WHERE id=:id AND org_id=:org"),
                               {"id": note["id"], "org": user.org_id, "now": now})
            record(connection, {**note, "status": "sent"}, "daily_note_sent", actor_id=user.id, from_status="ready")
            _notify_guardians(connection, note, "note_sent", f"daily_note:{note['id']}", now)
        if not any(c["status"] != "sent" for c in batch_view(connection, entry["id"], user.org_id)["children"]):
            connection.execute(text("""
                UPDATE cards SET status='done', version=version+1, updated_at=:now, closed_at=:now
                WHERE org_id=:org AND subject_type='daily_note_batch' AND subject_id=:input AND status<>'done'
            """), {**values, "now": now})
    return {"sent_count": len(selected)}
