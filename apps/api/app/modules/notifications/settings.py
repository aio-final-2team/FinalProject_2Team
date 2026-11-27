"""본인 설정만 저장하고 알림 생성 트랜잭션에서도 같은 값을 읽어요."""

from contextlib import nullcontext
from datetime import time

from sqlalchemy import text

from app.core.db import transaction


def get(user_id, *, connection=None):
    with (transaction() if connection is None else nullcontext(connection)) as connection:
        row = connection.execute(text("""
            SELECT to_char(quiet_start,'HH24:MI') AS quiet_start, to_char(quiet_end,'HH24:MI') AS quiet_end
            FROM user_settings WHERE user_id=:id
        """), {"id": user_id}).mappings().one_or_none()
        return dict(row) if row else {"quiet_start": None, "quiet_end": None}


def save(user, body):
    with transaction() as connection:
        if body.quiet_start is None:
            connection.execute(text("DELETE FROM user_settings WHERE user_id=:id AND org_id=:org"),
                               {"id": user.id, "org": user.org_id})
        else:
            connection.execute(text("""
                INSERT INTO user_settings(user_id,org_id,quiet_start,quiet_end) VALUES (:id,:org,:start,:end)
                ON CONFLICT (user_id) DO UPDATE SET quiet_start=EXCLUDED.quiet_start,
                    quiet_end=EXCLUDED.quiet_end,updated_at=clock_timestamp()
            """), {"id": user.id, "org": user.org_id, "start": time.fromisoformat(body.quiet_start),
                   "end": time.fromisoformat(body.quiet_end)})
        return get(user.id, connection=connection)
