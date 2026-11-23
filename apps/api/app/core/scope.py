"""기관 → 반 기간·카드 재배정 → 내 아이. 거부 이력은 404 전에 커밋한다.

반환값은 SQL 행이다. T27의 조회·변경 모듈도 이 범위 함수를 먼저 부른다.
다른 기관 행은 읽지 않고, 그 행을 거부 이력의 FK로도 연결하지 않는다.
"""

import json
from contextlib import nullcontext
from datetime import datetime

from sqlalchemy import text

from app.core.db import transaction
from app.core.errors import ApiError
from app.core.request_id import active_trace_id
from app.core.schedule import KST


def _checked(user, row, allowed, resource, resource_id, *, request_id=None, card_id=None):
    if row is not None and allowed:
        return row
    # 호출 쪽 변경 트랜잭션과 별도로 기록한다. 이어지는 ApiError로 이력이 롤백되지 않는다.
    with transaction() as connection:
        connection.execute(text("""
            INSERT INTO events (org_id, request_id, card_id, actor_type, actor_id, action, detail)
            VALUES (:org, :request_id, :card_id, 'user', :actor, 'permission_denied', CAST(:detail AS jsonb))
        """), {"org": user.org_id, "actor": user.id,
               "request_id": request_id if row is not None else None,
               "card_id": card_id if row is not None else None,
               "detail": json.dumps({"resource": resource, "resource_id": str(resource_id),
                                     "trace_id": active_trace_id.get()})})
    raise ApiError(404, "NOT_FOUND")


def _classroom(connection, user, classroom_id):
    if user.role == "director":
        return True
    if user.role == "teacher":
        return connection.scalar(text("""
            SELECT EXISTS (SELECT 1 FROM classroom_staff
            WHERE org_id=:org AND user_id=:user AND classroom_id=:classroom
              AND (valid_from IS NULL OR valid_from<=:today)
              AND (valid_to IS NULL OR valid_to>=:today))
        """), {"org": user.org_id, "user": user.id, "classroom": classroom_id,
               "today": datetime.now(KST).date()})
    return False


def _guardian(connection, user, child_id):
    return connection.scalar(text("""
        SELECT EXISTS (SELECT 1 FROM child_guardians
        WHERE org_id=:org AND user_id=:user AND child_id=:child)
    """), {"org": user.org_id, "user": user.id, "child": child_id})


def classroom_in_scope(user, classroom_id, *, connection=None):
    with (transaction() if connection is None else nullcontext(connection)) as connection:
        row = connection.execute(text("SELECT * FROM classrooms WHERE id=:id AND org_id=:org"),
                                 {"id": classroom_id, "org": user.org_id}).mappings().one_or_none()
        allowed = row is not None and _classroom(connection, user, classroom_id)
    return _checked(user, row, allowed, "classroom", classroom_id)


def child_in_scope(user, child_id, *, connection=None):
    with (transaction() if connection is None else nullcontext(connection)) as connection:
        row = connection.execute(text("SELECT * FROM children WHERE id=:id AND org_id=:org"),
                                 {"id": child_id, "org": user.org_id}).mappings().one_or_none()
        allowed = row is not None and (
            _guardian(connection, user, child_id) if user.role == "parent"
            else _classroom(connection, user, row["classroom_id"]))
    return _checked(user, row, allowed, "child", child_id)


def request_in_scope(user, request_id, *, connection=None):
    with (transaction() if connection is None else nullcontext(connection)) as connection:
        row = connection.execute(text("SELECT * FROM requests WHERE id=:id AND org_id=:org"),
                                 {"id": request_id, "org": user.org_id}).mappings().one_or_none()
        allowed = False
        if row is not None:
            if user.role == "parent":
                allowed = row["requester_id"] == user.id and (
                    row["child_id"] is None or _guardian(connection, user, row["child_id"]))
            else:
                allowed = _classroom(connection, user, row["classroom_id"])
                if not allowed and user.role == "teacher":
                    allowed = connection.scalar(text("""
                        SELECT EXISTS (SELECT 1 FROM cards
                        WHERE request_id=:id AND org_id=:org AND assignee_id=:user)
                    """), {"id": request_id, "org": user.org_id, "user": user.id})
    return _checked(user, row, allowed, "request", request_id, request_id=request_id)


def card_in_scope(user, card_id, *, decision=None, connection=None):
    if user.role not in ("teacher", "director"):
        raise ApiError(403, "FORBIDDEN_ROLE")
    with (transaction() if connection is None else nullcontext(connection)) as connection:
        row = connection.execute(text("""
            SELECT c.*, r.type AS request_type, coalesce(r.classroom_id, n.classroom_id) AS classroom_id
            FROM cards c LEFT JOIN requests r ON (r.id, r.org_id)=(c.request_id, c.org_id)
            LEFT JOIN daily_note_inputs n ON c.subject_type='daily_note_batch'
              AND (n.id, n.org_id)=(c.subject_id, c.org_id)
            WHERE c.id=:id AND c.org_id=:org
        """), {"id": card_id, "org": user.org_id}).mappings().one_or_none()
        allowed = row is not None and (row["assignee_id"] == user.id
                                       or _classroom(connection, user, row["classroom_id"]))
    row = _checked(user, row, allowed, "card", card_id,
                   request_id=row["request_id"] if row else None, card_id=card_id)
    if decision is not None and (
        (row["kind"] == "director_report" and user.role != "director")
        or (user.role == "director" and row["request_type"] == "complaint"
            and row["kind"] == "reply_draft" and decision in ("approve", "edit_approve", "complete"))
    ):
        raise ApiError(403, "FORBIDDEN_ROLE")
    return row


def note_input_in_scope(user, input_id, *, connection=None):
    if user.role not in ("teacher", "director"):
        raise ApiError(403, "FORBIDDEN_ROLE")
    with (transaction() if connection is None else nullcontext(connection)) as connection:
        row = connection.execute(text("SELECT * FROM daily_note_inputs WHERE id=:id AND org_id=:org"),
                                 {"id": input_id, "org": user.org_id}).mappings().one_or_none()
        allowed = row is not None and _classroom(connection, user, row["classroom_id"])
    return _checked(user, row, allowed, "note_input", input_id)


def note_in_scope(user, note_id, *, connection=None):
    with (transaction() if connection is None else nullcontext(connection)) as connection:
        row = connection.execute(text("""
            SELECT n.*, i.classroom_id FROM daily_notes n
            JOIN daily_note_inputs i ON (i.id, i.org_id, i.note_date)=(n.input_id, n.org_id, n.note_date)
            WHERE n.id=:id AND n.org_id=:org
        """), {"id": note_id, "org": user.org_id}).mappings().one_or_none()
        allowed = False
        if row is not None:
            allowed = (row["status"] == "sent" and _guardian(connection, user, row["child_id"])) \
                if user.role == "parent" else _classroom(connection, user, row["classroom_id"])
    return _checked(user, row, allowed, "note", note_id)
