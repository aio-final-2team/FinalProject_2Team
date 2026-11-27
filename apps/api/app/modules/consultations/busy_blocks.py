"""일정 등록과 상담 확정은 같은 담임 잠금 안에서 겹침을 확인해요."""

from sqlalchemy import text

from app.core import scope
from app.core.db import transaction
from app.core.errors import ApiError

VIEW = "id,user_id,lower(period) AS start_at,upper(period) AS end_at,kind"


def list_blocks(user, start, end, user_id):
    with transaction() as connection:
        row = connection.execute(text("""
            SELECT id FROM users WHERE id=:id AND org_id=:org AND role IN ('teacher','director')
        """), {"id": user_id, "org": user.org_id}).mappings().one_or_none()
        scope._checked(user, row, user_id == user.id or user.role == "director", "staff", user_id)
        rows = connection.execute(text(f"""
            SELECT {VIEW} FROM staff_busy_blocks WHERE org_id=:org AND user_id=:user
              AND period && tstzrange(:start,:end,'[)') ORDER BY lower(period),id
        """), {"org": user.org_id, "user": user_id, "start": start, "end": end}).mappings()
        return {"items": [dict(row) for row in rows]}


def create(user, body):
    with transaction() as connection:
        connection.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
                           {"key": f"consult:staff:{user.id}"})
        values = {"org": user.org_id, "user": user.id, **body.model_dump()}
        if connection.scalar(text("""
            SELECT EXISTS (SELECT 1 FROM consultation_bookings
            WHERE org_id=:org AND teacher_id=:user AND status='confirmed'
              AND tstzrange(lower(period),coalesce(expected_end_at,upper(period)),'[)')
                  && tstzrange(:start_at,:end_at,'[)'))
        """), values):
            raise ApiError(409, "SLOT_TAKEN")
        return dict(connection.execute(text(f"""
            INSERT INTO staff_busy_blocks(org_id,user_id,period,kind)
            VALUES (:org,:user,tstzrange(:start_at,:end_at,'[)'),:kind) RETURNING {VIEW}
        """), values).mappings().one())


def delete(user, block_id):
    with transaction() as connection:
        row = connection.execute(text("""
            SELECT user_id FROM staff_busy_blocks WHERE id=:id AND org_id=:org FOR UPDATE
        """), {"id": block_id, "org": user.org_id}).mappings().one_or_none()
        scope._checked(user, row, row is not None and row["user_id"] == user.id, "busy_block", block_id)
        connection.execute(text("DELETE FROM staff_busy_blocks WHERE id=:id AND org_id=:org"),
                           {"id": block_id, "org": user.org_id})
