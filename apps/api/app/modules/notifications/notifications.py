"""요청 이력과 같은 트랜잭션에서 앱 안 알림을 저장해요. 발송은 워커에서 해요."""

from sqlalchemy import text

from app.api.labels import parent_label
from app.core.constants import NOTIFICATION_TITLES as TITLES
from app.core.schedule import deliver_after



def enqueue(connection, event, req, recipient_id, kind, body=None):
    recipient = connection.execute(text("SELECT role FROM users WHERE id=:id AND org_id=:org"),
                                   {"id": recipient_id, "org": req["org_id"]}).mappings().one_or_none()
    if recipient is None:
        return
    connection.execute(text("""
        INSERT INTO notifications (org_id,recipient_id,request_id,card_id,kind,title,body,dedupe_key,deliver_after)
        VALUES (:org,:recipient,:request,:card,:kind,:title,:body,:key,:deliver)
        ON CONFLICT (dedupe_key) DO NOTHING
    """), {"org": req["org_id"], "recipient": recipient_id, "request": req["id"], "card": event["card_id"],
           "kind": kind, "title": TITLES[kind], "body": body, "key": f"event:{event['id']}:{recipient_id}",
           "deliver": deliver_after(event["created_at"], recipient["role"], req["risk_level"], req["risk_category"])})


def notify_event(connection, event, req, card):
    if req is None:
        return
    to, action = event["to_status"], event["action"]
    parent_kinds = {"needs_info": "needs_info", "on_hold": "on_hold", "sent_or_booked": "sent_or_booked",
                    "rejected": "rejected"}
    if to == "completed" and req["type"] == "complaint":
        enqueue(connection, event, req, req["requester_id"], "completed")
    elif to in parent_kinds:
        body = parent_label(to, req["type"])
        if to == "on_hold":
            body += f" · 예정일 {card['hold_until']}"
        if action == "dismissed":
            body = event["detail"].get("reason_text") or event["detail"].get("reason_code")
        enqueue(connection, event, req, req["requester_id"], parent_kinds[to], body)
    if action == "escalated":
        director = connection.scalar(text("""
            SELECT id FROM users WHERE org_id=:org AND role='director' AND is_active ORDER BY id LIMIT 1
        """), {"org": req["org_id"]})
        if req["risk_level"] in ("urgent", "uncertain"):
            kind = "urgent_complaint" if req["risk_level"] == "urgent" else "uncertain_complaint"
            for recipient in {req["assignee_id"], director}:
                enqueue(connection, event, req, recipient, kind)
        else:
            enqueue(connection, event, req, director, "director_report")
    elif action == "parent_confirmed":
        enqueue(connection, event, req, req["assignee_id"], "parent_confirmed")
    elif action == "slot_hold_expired":
        enqueue(connection, event, req, card["assignee_id"], "slot_hold_expired")
    elif to == "awaiting_review":
        automatic = action == "resumed" and event["detail"].get("automatic")
        if action != "resumed" or automatic:
            enqueue(connection, event, req, card["assignee_id"] if card else req["assignee_id"],
                    "hold_resumed" if automatic else "new_card")


def listing(user, page, size, sort):
    from app.core.db import transaction
    with transaction() as connection:
        # 발송기는 워커에서 연결해요. 노출은 기존 계약의 deliver_after를 기준으로 해요.
        rows = [dict(row) for row in connection.execute(text('''
            SELECT * FROM notifications WHERE org_id=:org AND recipient_id=:user AND deliver_after<=now()
            ORDER BY created_at,id
        '''), {'org': user.org_id, 'user': user.id}).mappings()]
        if sort.startswith('-'):
            rows.reverse()
        return {'items': rows[(page-1)*size:page*size], 'total': len(rows), 'page': page, 'size': size}


def read(user, notification_id):
    from app.core.db import transaction
    from app.core import scope
    with transaction() as connection:
        row = connection.execute(text('''
            UPDATE notifications SET read_at=coalesce(read_at,clock_timestamp())
            WHERE id=:id AND org_id=:org AND recipient_id=:user AND deliver_after<=now() RETURNING *
        '''), {'id': notification_id, 'org': user.org_id, 'user': user.id}).mappings().one_or_none()
        if row is None:
            scope._checked(user, None, False, "notification", notification_id)
        return dict(row)
