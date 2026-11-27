"""받은함은 staff_inbox, 원장 현황은 director_overview에서 읽어요."""

from collections import Counter
from datetime import datetime, timedelta

from sqlalchemy import text

from app.api.labels import note_batch_label, staff_label
from app.core import scope
from app.core.db import transaction
from app.core.schedule import KST
from app.modules.requests.complaints import repeat_count
from app.modules.requests.requests import _expire, _hold_until, source_note
from app.modules.daily_notes.notes import batch_view

FILTERS = ("unassigned", "needs_review", "uncertain", "on_hold", "in_progress", "done")


def requester_fields(connection, req):
    names = connection.execute(text("""
        SELECT c.display_name AS child_name,u.display_name AS requester_name
        FROM users u LEFT JOIN children c ON c.id=:child AND c.org_id=u.org_id
        WHERE u.id=:user AND u.org_id=:org
    """), {"child": req["child_id"], "user": req["requester_id"], "org": req["org_id"]}).mappings().one()
    return {"child_id": req["child_id"], **names}


def staff_request(connection, req, card_kind=None):
    return {
        k: req[k]
        for k in (
            "id",
            "type",
            "title",
            "body",
            "status",
            "risk_level",
            "risk_category",
            "parent_confirmed_at",
            "classroom_id",
            "created_at",
            "updated_at",
            "missing_fields",
        )
    } | {
        **requester_fields(connection, req),
        "repeat_count": repeat_count(connection, req),
        "status_label": staff_label(req["status"], req["type"], card_kind=card_kind),
        "hold_until": _hold_until(connection, req),
        "source_note": source_note(connection, req),
    }


def _visible(connection, user):
    # 반 없는 개인 규칙 카드는 소유자/배정자만, 원장은 같은 기관 전체를 읽어요.
    return [
        dict(row)
        for row in connection.execute(
            text("""
        SELECT c.*,i.inbox_filter,r.classroom_id AS request_classroom,n.classroom_id AS note_classroom,
               r.child_id,ch.display_name AS child_name,u.display_name AS requester_name,
               coalesce(r.classroom_id,n.classroom_id,owner_class.classroom_id) AS display_classroom
        FROM cards c JOIN staff_inbox i ON i.card_id=c.id
        LEFT JOIN requests r ON (r.id,r.org_id)=(c.request_id,c.org_id)
        LEFT JOIN children ch ON (ch.id,ch.org_id)=(r.child_id,r.org_id)
        LEFT JOIN users u ON (u.id,u.org_id)=(r.requester_id,r.org_id)
        LEFT JOIN daily_note_inputs n ON c.subject_type='daily_note_batch' AND (n.id,n.org_id)=(c.subject_id,c.org_id)
        LEFT JOIN memory_rules mr ON c.subject_type='memory_rule' AND (mr.id,mr.org_id)=(c.subject_id,c.org_id)
        LEFT JOIN LATERAL (SELECT s.classroom_id FROM classroom_staff s
            WHERE s.org_id=c.org_id AND s.user_id=coalesce(mr.owner_id,c.assignee_id)
              AND (s.valid_from IS NULL OR s.valid_from<=CURRENT_DATE)
              AND (s.valid_to IS NULL OR s.valid_to>=CURRENT_DATE)
            ORDER BY s.created_at,s.classroom_id LIMIT 1) owner_class ON true
        WHERE c.org_id=:org AND (:director OR c.assignee_id=:user OR EXISTS (
            SELECT 1 FROM classroom_staff s WHERE s.org_id=c.org_id AND s.user_id=:user
              AND s.classroom_id=coalesce(r.classroom_id,n.classroom_id)
              AND (s.valid_from IS NULL OR s.valid_from<=CURRENT_DATE)
              AND (s.valid_to IS NULL OR s.valid_to>=CURRENT_DATE))) ORDER BY c.id
    """),
            {"org": user.org_id, "user": user.id, "director": user.role == "director"},
        ).mappings()
    ]


def _expire_visible(connection, user):
    ids = sorted({row["request_id"] for row in _visible(connection, user) if row["request_id"]})
    for request_id in ids:
        req = dict(connection.execute(text("SELECT * FROM requests WHERE id=:id"), {"id": request_id}).mappings().one())
        _expire(connection, req)


def _item(connection, card):
    req = (
        connection.execute(text("SELECT * FROM requests WHERE id=:id"), {"id": card["request_id"]})
        .mappings()
        .one_or_none()
    )
    classroom = (
        connection.execute(
            text("SELECT id,name FROM classrooms WHERE id=:id AND org_id=:org"),
            {"id": card["display_classroom"], "org": card["org_id"]},
        )
        .mappings()
        .one_or_none()
    )
    person = (
        connection.execute(
            text("SELECT id,display_name FROM users WHERE id=:id AND org_id=:org"),
            {"id": card["assignee_id"], "org": card["org_id"]},
        )
        .mappings()
        .one_or_none()
    )
    check = card["check_result"]
    note_batch = batch_view(connection, card["subject_id"], card["org_id"]) if card["subject_type"] == "daily_note_batch" else None
    return {k: card[k] for k in ("id", "kind", "status", "version", "request_id", "due_at", "hold_until")} | {
        **{k: card[k] for k in ("child_id", "child_name", "requester_name")},
        "status_label": staff_label(req["status"], req["type"], card_kind=card["kind"])
        if req
        else note_batch_label(card["status"], note_batch["draft_status"], card["draft"].get("validation_result"))
        if note_batch
        else "확인 필요"
        if card["status"] == "pending"
        else "완료",
        "request_type": req["type"] if req else None,
        "title": (req["title"] or req["body"].split("\n")[0][:40]) if req else card["draft"].get("summary", ""),
        "urgency": req["urgency"] if req else None,
        "risk_level": req["risk_level"] if req else None,
        "risk_category": req["risk_category"] if req and req["risk_level"] == "urgent" else None,
        "is_urgent": bool(req and req["risk_level"] == "urgent"),
        "repeat_count": repeat_count(connection, req) if req else None,
        "check": {"passed": check["passed"], "issue_count": len(check.get("issues", []))} if check else None,
        "parent_choice_count": connection.scalar(
            text("SELECT count(*) FROM consultation_slots WHERE card_id=:id AND status='chosen_by_parent'"),
            {"id": card["id"]},
        )
        if card["kind"] == "consult_slots"
        else None,
        "classroom": dict(classroom) if classroom else None,
        "assignee": dict(person) if person else None,
        "is_delayed": bool(card["due_at"] and card["due_at"] < datetime.now(KST)),
        "note_batch": note_batch,
    }


def listing(user, filter, request_type, risk_level, kind, assignee, page, size):
    with transaction() as connection:
        _expire_visible(connection, user)
        candidates = [
            (_item(connection, card), card["inbox_filter"])
            for card in _visible(connection, user)
            if (not kind or card["kind"] == kind) and (not assignee or card["assignee_id"] == user.id)
        ]
        candidates = [(row, bucket) for row, bucket in candidates if not risk_level or row["risk_level"] == risk_level]
        type_selected = (
            [(row, bucket) for row, bucket in candidates if bucket == filter]
            if filter
            else [(row, bucket) for row, bucket in candidates if bucket != "done"]
        )
        type_counts = {
            key: sum(row["request_type"] == key for row, _ in type_selected)
            for key in ("complaint", "consultation", "inquiry")
        }
        type_counts["all"] = len(type_selected)
        if request_type and request_type != "all":
            candidates = [(row, bucket) for row, bucket in candidates if row["request_type"] == request_type]
        counts = Counter(bucket for _, bucket in candidates)
        selected = (
            [row for row, bucket in candidates if bucket == filter]
            if filter
            else [row for row, bucket in candidates if bucket != "done"]
        )
        now = datetime.now(KST)
        selected.sort(
            key=lambda row: (not row["is_urgent"], row["due_at"] is None, row["due_at"] or now, str(row["id"]))
        )
        return {
            "items": selected[(page - 1) * size : page * size],
            "total": len(selected),
            "page": page,
            "size": size,
            "counts": {key: counts[key] for key in FILTERS},
            "type_counts": type_counts,
        }


def detail(user, card_id):
    with transaction() as connection:
        card = dict(scope.card_in_scope(user, card_id, connection=connection))
        req = None
        if card["request_id"]:
            req = dict(
                connection.execute(text("SELECT * FROM requests WHERE id=:id"), {"id": card["request_id"]})
                .mappings()
                .one()
            )
            req = _expire(connection, req)
            card = dict(connection.execute(text("SELECT * FROM cards WHERE id=:id"), {"id": card_id}).mappings().one())
        evidence = [
            dict(row)
            for row in connection.execute(
                text("""
            SELECT d.title AS document_title,ch.location,coalesce(d.effective_from,d.created_at::date) AS effective_from,
                   coalesce(e.quote,'') AS quote,(d.status='active'
                     AND (d.effective_to IS NULL OR d.effective_to>=CURRENT_DATE)) AS is_current
            FROM card_evidence e JOIN document_chunks ch ON (ch.id,ch.org_id)=(e.chunk_id,e.org_id)
            JOIN documents d ON (d.id,d.org_id)=(ch.document_id,ch.org_id)
            WHERE e.card_id=:id AND e.org_id=:org ORDER BY e.rank,ch.id
        """),
                {"id": card_id, "org": user.org_id},
            ).mappings()
        ]
        warnings = []
        if any(not e["is_current"] for e in evidence):
            warnings.append("stale_evidence")
        personal = (card["draft"].get("note_evidence") or card["draft"].get("record_evidence")
                    or card["draft"].get("care_evidence"))
        if (not evidence and not personal) or card["draft"].get("no_evidence"):
            warnings.append("no_evidence")
        if card["draft"].get("law_unchecked"):
            warnings.append("law_unchecked")
        if card["check_result"] is None:
            warnings.append("check_unavailable")
        if card["draft"].get("notify_failed"):
            warnings.append("notify_failed")
        instruction = (
            connection.execute(
                text("""
            SELECT a.reason_text AS text,a.created_at AS at,u.id,u.display_name
            FROM approvals a JOIN cards c ON (c.id,c.org_id)=(a.card_id,a.org_id)
            JOIN users u ON (u.id,u.org_id)=(a.decided_by,a.org_id)
            WHERE c.request_id=:request AND c.org_id=:org AND a.decision='instruct' ORDER BY a.id DESC LIMIT 1
        """),
                {"request": card["request_id"], "org": user.org_id},
            )
            .mappings()
            .one_or_none()
            if req and card["kind"] != "director_report"
            else None
        )
        rule = (
            connection.execute(
                text("SELECT id,reason_code,rule_text,status FROM memory_rules WHERE id=:id AND org_id=:org"),
                {"id": card["subject_id"], "org": user.org_id},
            )
            .mappings()
            .one_or_none()
            if card["kind"] == "rule_proposal"
            else None
        )
        choices = (
            connection.execute(
                text("""
            SELECT s.id AS slot_id,lower(s.period) AS start,upper(s.period) AS end,r.name AS room,s.chosen_at
            FROM consultation_slots s JOIN rooms r ON (r.id,r.org_id)=(s.room_id,s.org_id)
            WHERE s.card_id=:id AND s.org_id=:org AND s.status='chosen_by_parent' ORDER BY s.id
        """),
                {"id": card_id, "org": user.org_id},
            )
            .mappings()
            .all()
        )
        timeline = [
            dict(row)
            for row in connection.execute(
                text("""SELECT * FROM events
            WHERE org_id=:org AND (request_id=:request OR card_id=:id) ORDER BY id"""),
                {"org": user.org_id, "request": card["request_id"], "id": card_id},
            ).mappings()
        ]
        note_batch = batch_view(connection, card["subject_id"], card["org_id"]) if card["subject_type"] == "daily_note_batch" else None
        return {
            "card": {k: card[k] for k in ("id", "kind", "status", "version", "draft", "check_result", "check_attempts")}
            | {"summary": card["draft"].get("summary", ""), "note_batch": note_batch,
               "status_label": note_batch_label(card["status"], note_batch["draft_status"], card["draft"].get("validation_result")) if note_batch else None},
            "request": staff_request(connection, req, card["kind"]) if req else None,
            "messages": [dict(row) for row in connection.execute(text("""
                SELECT m.id,m.sender_type,CASE WHEN m.sender_type='user' THEN u.role END AS sender_role,m.body,m.created_at
                FROM request_messages m LEFT JOIN users u ON (u.id,u.org_id)=(m.sender_id,m.org_id)
                WHERE m.request_id=:id AND m.org_id=:org ORDER BY m.id
            """), {"id": card["request_id"], "org": user.org_id}).mappings()] if req else [],
            "evidence": evidence,
            "warnings": warnings,
            "parent_choices": [
                {
                    "slot_id": row["slot_id"],
                    "period": {"start": row["start"], "end": row["end"]},
                    "room": row["room"],
                    "chosen_at": row["chosen_at"],
                    "hold_expires_at": row["chosen_at"] + timedelta(hours=24),
                }
                for row in choices
            ],
            "rule": dict(rule) if rule else None,
            "director_instruction": {
                "text": instruction["text"],
                "by": {"id": instruction["id"], "display_name": instruction["display_name"]},
                "at": instruction["at"],
            }
            if instruction
            else None,
            "timeline": timeline,
        }


def overview(user):
    with transaction() as connection:
        _expire_visible(connection, user)
        row = (
            connection.execute(text("SELECT * FROM director_overview WHERE org_id=:org"), {"org": user.org_id})
            .mappings()
            .one_or_none()
        )
        result = {
            k: int(row[k]) if row else 0
            for k in ("unassigned", "waiting", "delayed", "done_today", "completed_unconfirmed")
        }
        result["reassignments"] = [
            {"card_id": ev["card_id"], **ev["detail"], "at": ev["created_at"]}
            for ev in connection.execute(
                text(
                    "SELECT card_id,detail,created_at FROM events WHERE org_id=:org AND action='reassigned' ORDER BY id"
                ),
                {"org": user.org_id},
            ).mappings()
        ]
        result["eval"] = [
            dict(row)
            for row in connection.execute(
                text("""
            SELECT suite,requested_model,returned_model,passed,total,started_at FROM eval_runs ORDER BY started_at DESC,id DESC LIMIT 20
        """)
            ).mappings()
        ]
        return result
