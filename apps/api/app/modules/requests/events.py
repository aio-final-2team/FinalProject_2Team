"""요청 상태·이력·알림을 호출 쪽 트랜잭션에서 함께 바꿔요."""

import json

from sqlalchemy import text

from app.core.request_id import active_trace_id
from app.modules.notifications.notifications import notify_event


def record(connection, req, action, *, card=None, actor_type="system", actor_id=None, agent_name=None,
           from_status=None, to_status=None, **detail):
    event = dict(connection.execute(text("""
        INSERT INTO events (org_id,request_id,card_id,actor_type,actor_id,agent_name,action,
                            from_status,to_status,detail)
        VALUES (:org,:request,:card,:actor_type,:actor,:agent,:action,:from_status,:to_status,CAST(:detail AS jsonb))
        RETURNING *
    """), {"org": req["org_id"] if req else card["org_id"], "request": req["id"] if req else None, "card": card["id"] if card else None,
           "actor_type": actor_type, "actor": actor_id, "agent": agent_name, "action": action,
           "from_status": from_status, "to_status": to_status,
           "detail": json.dumps({"trace_id": active_trace_id.get(), **detail})}).mappings().one())
    notify_event(connection, event, req, card)
    return event


def set_status(connection, req, to_status, *, action, **event_kw):
    old = req["status"]
    req.update(connection.execute(text("""
        UPDATE requests SET status=:status,updated_at=clock_timestamp(),
            closed_at=CASE WHEN :status IN ('completed','rejected') THEN clock_timestamp() ELSE closed_at END
        WHERE id=:id AND org_id=:org RETURNING *
    """), {"id": req["id"], "org": req["org_id"], "status": to_status}).mappings().one())
    return record(connection, req, action, from_status=old, to_status=to_status, **event_kw)
