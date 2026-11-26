"""기관·반 범위를 확인하고 기록을 저장하며 삭제 표시는 보존해요."""

from sqlalchemy import text

from app.core import scope
from app.core.db import transaction


def list_records(user, classroom_id, note_date):
    with transaction() as connection:
        scope.classroom_in_scope(user, classroom_id, connection=connection)
        return {"items": [dict(row) for row in connection.execute(text("""
            SELECT * FROM daily_records WHERE org_id=:org AND classroom_id=:class AND note_date=:date
              AND deleted_at IS NULL ORDER BY child_id,created_at,id
        """), {"org": user.org_id, "class": classroom_id, "date": note_date}).mappings()]}


def create(user, classroom_id, body):
    with transaction() as connection:
        scope.classroom_in_scope(user, classroom_id, connection=connection)
        child = scope.child_in_scope(user, body.child_id, connection=connection)
        scope._checked(user, child, child["classroom_id"] == classroom_id, "child", body.child_id)
        return dict(connection.execute(text("""
            INSERT INTO daily_records(org_id,classroom_id,child_id,note_date,body,author_id)
            VALUES (:org,:class,:child_id,:note_date,:body,:author) RETURNING *
        """), {**body.model_dump(), "org": user.org_id, "class": classroom_id,
               "author": user.id}).mappings().one())


def delete(user, record_id):
    with transaction() as connection:
        row = connection.execute(text("""
            SELECT * FROM daily_records WHERE id=:id AND org_id=:org AND deleted_at IS NULL FOR UPDATE
        """), {"id": record_id, "org": user.org_id}).mappings().one_or_none()
        scope._checked(user, row, row is not None, "daily_record", record_id)
        if row["author_id"] != user.id:
            scope.classroom_in_scope(user, row["classroom_id"], connection=connection)
        connection.execute(text("UPDATE daily_records SET deleted_at=now() WHERE id=:id AND org_id=:org"),
                           {"id": record_id, "org": user.org_id})


def with_record_memos(connection, entry, memos):
    rows = connection.execute(text("""
        SELECT child_id::text, string_agg(body,E'\n' ORDER BY created_at,id) FROM daily_records
        WHERE org_id=:org AND classroom_id=:class AND note_date=:date AND deleted_at IS NULL
        GROUP BY child_id
    """), {"org": entry["org_id"], "class": entry["classroom_id"], "date": entry["note_date"]})
    return {**dict(rows.all()), **memos}
