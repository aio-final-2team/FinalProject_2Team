"""알림장 상태 변경과 같은 트랜잭션에서 아이별 이력을 남긴다."""

import json

from sqlalchemy import text

from app.core.request_id import active_trace_id


def edited_child_ids(connection, input_id):
    return set(connection.scalars(text("""
        SELECT n.child_id::text FROM daily_notes n
        WHERE n.input_id=:input AND n.status IN ('draft','needs_check')
          AND (n.content<>n.ai_original OR EXISTS (
              SELECT 1 FROM events e WHERE e.daily_note_id=n.id AND e.action='daily_note_edited'))
    """), {"input": input_id}))


def record(connection, note, action, *, actor_id=None, from_status=None, **detail):
    connection.execute(text("""
        INSERT INTO events (org_id, daily_note_id, actor_type, actor_id, action, from_status, to_status, detail)
        VALUES (:org, :note, :actor_type, :actor, :action, :from_status, :to_status, CAST(:detail AS jsonb))
    """), {"org": note["org_id"], "note": note["id"], "action": action,
           "actor_type": "user" if actor_id else "agent", "actor": actor_id,
           "from_status": from_status, "to_status": note["status"],
           "detail": json.dumps({"trace_id": active_trace_id.get(), **detail})})
