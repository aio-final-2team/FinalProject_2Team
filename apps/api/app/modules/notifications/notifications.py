"""요청 이력과 같은 트랜잭션에서 앱 안 알림을 저장해요. 발송은 워커에서 해요."""

from sqlalchemy import text

from app.api.labels import parent_label
from app.core.care import unregistered_pickup_key
from app.core.constants import (CARE_REQUEST_TYPES, CARE_MESSAGE_NOTICE, CARE_UPDATED_NOTICE, UNREGISTERED_PICKUP_CHECK,
                                consultation_booking_body, notification_title, rejection_body)
from app.core.schedule import deliver_after



def enqueue(connection, event, req, recipient_id, kind, body=None, *, dedupe_key=None, subject_id=None):
    org_id = req["org_id"] if req else event["org_id"]
    recipient = connection.execute(text("SELECT role FROM users WHERE id=:id AND org_id=:org"),
                                   {"id": recipient_id, "org": org_id}).mappings().one_or_none()
    if recipient is None:
        return
    connection.execute(text("""
        INSERT INTO notifications (org_id,recipient_id,request_id,card_id,kind,title,body,dedupe_key,deliver_after,
                                   subject_type,subject_id)
        VALUES (:org,:recipient,:request,:card,:kind,:title,:body,:key,:deliver,
                CASE WHEN CAST(:subject AS uuid) IS NULL THEN NULL ELSE 'daily_note' END,:subject)
        ON CONFLICT (dedupe_key) DO NOTHING
    """), {"org": org_id, "recipient": recipient_id, "request": req["id"] if req else None, "card": event["card_id"],
           "kind": kind, "title": notification_title(kind, req.get("type") if req else None), "body": body,
           "key": dedupe_key or f"event:{event['id']}:{recipient_id}", "subject": subject_id,
           "deliver": deliver_after(event["created_at"], recipient["role"], req["risk_level"] if req else None,
                                    req["risk_category"] if req else None, request_type=req.get("type") if req else None,
                                    user_id=recipient_id, connection=connection)})


def notify_event(connection, event, req, card):
    if event["action"] == "reassigned":
        enqueue(connection, event, req, card["assignee_id"], "reassigned")
        return
    if req is None:
        if card and card["kind"] == "rule_proposal" and event["action"] == "created":
            enqueue(connection, event, None, card["assignee_id"], "new_card")
        return
    to, action = event["to_status"], event["action"]
    if req.get("type") == "consultation" and (
        (action == "created" and card and card["kind"] == "consult_slots" and not card["assignee_id"])
        or (action == "info_requested" and "preferred_times" in event["detail"])
    ):
        recipient = card["assignee_id"] or connection.scalar(text(
            "SELECT id FROM users WHERE org_id=:org AND role='director' AND is_active ORDER BY id LIMIT 1"),
            {"org": req["org_id"]})
        enqueue(connection, event, req, recipient,
                "parent_message" if "preferred_times" in event["detail"] else "new_card",
                event["detail"].get("preferred_times"))
        return
    if req.get("type") in CARE_REQUEST_TYPES:
        if action == "cancelled":
            recipient = req["assignee_id"] or connection.scalar(text(
                "SELECT id FROM users WHERE org_id=:org AND role='director' AND is_active ORDER BY id LIMIT 1"),
                {"org": req["org_id"]})
            enqueue(connection, event, req, recipient, "cancelled")
        elif event["detail"].get("care_decision") == "reject":
            enqueue(connection, event, req, req["requester_id"], "care_rejected", event["detail"]["reason_text"])
        elif event["detail"].get("unregistered_pickup"):
            director = connection.scalar(text(
                "SELECT id FROM users WHERE org_id=:org AND role='director' AND is_active ORDER BY id LIMIT 1"),
                {"org": req["org_id"]})
            enqueue(connection, event, req, director, "care_requested", UNREGISTERED_PICKUP_CHECK,
                    dedupe_key=unregistered_pickup_key(req["id"], event["detail"].get("pickup_snapshot", {})))
        elif event["detail"].get("care_message") or action == "care_updated":
            recipient = req["assignee_id"] or connection.scalar(text(
                "SELECT id FROM users WHERE org_id=:org AND role='director' AND is_active ORDER BY id LIMIT 1"),
                {"org": req["org_id"]})
            enqueue(connection, event, req, recipient, "care_requested",
                    CARE_UPDATED_NOTICE if action == "care_updated" else CARE_MESSAGE_NOTICE)
        elif action == "created" and to == "received":
            recipient = req["assignee_id"] or connection.scalar(text(
                "SELECT id FROM users WHERE org_id=:org AND role='director' AND is_active ORDER BY id LIMIT 1"),
                {"org": req["org_id"]})
            enqueue(connection, event, req, recipient, "care_requested")
        elif event["detail"].get("care_decision") in ("confirm", "complete"):
            enqueue(connection, event, req, req["requester_id"],
                    "care_confirmed" if to == "assigned" else "completed", parent_label(to, req["type"], req["assignee_id"]))
        return
    if action == "message_added":
        if req["type"] == "consultation" and req["status"] in ("needs_info", "sent_or_booked"):
            recipients = {req["assignee_id"]: None} if req["assignee_id"] else {}
        elif req["status"] in ("awaiting_review", "on_hold", "escalated", "needs_info"):
            recipients = {row["assignee_id"]: row["id"] for row in connection.execute(text("""
                SELECT id,assignee_id FROM cards WHERE request_id=:id AND org_id=:org
                  AND status NOT IN ('done','rejected') AND assignee_id IS NOT NULL
                ORDER BY created_at,id
            """), {"id": req["id"], "org": req["org_id"]}).mappings()}
        else:
            return
        if not recipients:
            director = connection.scalar(text(
                "SELECT id FROM users WHERE org_id=:org AND role='director' AND is_active ORDER BY id LIMIT 1"),
                {"org": req["org_id"]})
            recipients = {director: None}
        for recipient, card_id in recipients.items():
            enqueue(connection, {**event, "card_id": card_id}, req, recipient, "parent_message")
        return
    parent_kinds = {"needs_info": "needs_info", "on_hold": "on_hold", "sent_or_booked": "sent_or_booked",
                    "rejected": "rejected"}
    if to == "completed" and req["type"] == "complaint":
        enqueue(connection, event, req, req["requester_id"], "completed")
    elif to in parent_kinds:
        kind = parent_kinds[to]
        body = parent_label(to, req["type"], req["assignee_id"], req["parent_confirmed_at"])
        if to == "sent_or_booked" and req["type"] == "consultation":
            booking = connection.execute(text("""
                SELECT lower(period) AS start,upper(period) AS end FROM consultation_bookings
                WHERE request_id=:id AND org_id=:org AND status='confirmed'
            """), {"id": req["id"], "org": req["org_id"]}).mappings().one_or_none()
            # 예약 없이 글로 답한 상담(예전 인계 카드)은 일반 회신 알림으로 보내요.
            if booking:
                kind = "consultation_booked"
                body = consultation_booking_body(booking["start"], booking["end"])
        if to == "on_hold":
            body += f" · 예정일 {card['hold_until']}"
        if action == "dismissed":
            body = rejection_body(event["detail"].get("reason_code"), event["detail"].get("reason_text"))
        enqueue(connection, event, req, req["requester_id"], kind, body)
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
    elif (action == "risk_reclassified" and event["from_status"] == "escalated"
          and to == "awaiting_review" and req["risk_level"] == "normal"):
        reply = connection.execute(text("""
            SELECT id,assignee_id FROM cards WHERE request_id=:id AND kind='reply_draft'
              AND status IN ('pending','in_review') ORDER BY created_at DESC,id DESC LIMIT 1
        """), {"id": req["id"]}).mappings().one_or_none()
        if reply:
            # 재분류 이력의 보고 카드 연결은 두고 알림은 담임 회신 카드로 보내요.
            enqueue(connection, {**event, "card_id": reply["id"]}, req, reply["assignee_id"], "new_card")
    elif to == "awaiting_review" and action != "risk_reclassified":
        automatic = action == "resumed" and event["detail"].get("automatic")
        if action != "resumed" or automatic:
            recipient = card["assignee_id"] if card else req["assignee_id"]
            if card and card["status"] == "unassigned" and recipient is None:
                recipient = connection.scalar(text("""
                    SELECT id FROM users WHERE org_id=:org AND role='director' AND is_active ORDER BY id LIMIT 1
                """), {"org": req["org_id"]})
            enqueue(connection, event, req, recipient,
                    "hold_resumed" if automatic else "new_card")


def listing(user, page, size, sort):
    from app.core.db import transaction
    with transaction() as connection:
        # 발송·재시도 상태와 별개로 노출은 기존 계약의 deliver_after를 기준으로 해요.
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
