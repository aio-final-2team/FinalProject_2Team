"""앱 안 알림만 발송 처리해요. 행 잠금과 발송 상태를 같은 트랜잭션에 두어요."""

from datetime import datetime, timedelta

from sqlalchemy import text

from app.core.db import transaction
from app.core.schedule import KST, deliver_after

MAX_ATTEMPTS = 3
RETRY_SECONDS = 60


def _failure(connection, notification, code, attempts):
    connection.execute(text("""
        INSERT INTO events(org_id,request_id,card_id,daily_note_id,actor_type,action,detail)
        VALUES (:org,:request,:card,:note,'system','tool_failed',
                jsonb_build_object('notification_id',CAST(:id AS bigint),'code',CAST(:code AS text),
                                   'attempts',CAST(:attempts AS integer)))
    """), {"org": notification["org_id"], "request": notification["request_id"],
           "card": notification["card_id"], "note": notification["subject_id"]
           if notification["subject_type"] == "daily_note" else None,
           "id": notification["id"], "code": code, "attempts": attempts})
    if attempts >= MAX_ATTEMPTS or code == "RECIPIENT_UNAVAILABLE":
        connection.execute(text("""
            UPDATE cards SET draft=draft || jsonb_build_object('notify_failed',true)
            WHERE id=:card AND org_id=:org
        """), {"card": notification["card_id"], "org": notification["org_id"]})


def _deliver(connection, notification, now):
    # 외부 전송은 없어요. sent 표시까지 같은 DB 트랜잭션으로 묶어요.
    connection.execute(text("""
        UPDATE notifications SET status='sent',sent_at=:now,attempts=attempts+1,last_error=NULL
        WHERE id=:id
    """), {"id": notification["id"], "now": now})


def deliver_pending(now=None):
    now = now or datetime.now(KST)
    sent = 0
    with transaction() as connection:
        rows = connection.execute(text("""
            SELECT n.*,u.role,u.is_active,r.risk_level,r.risk_category
            FROM notifications n JOIN users u ON (u.id,u.org_id)=(n.recipient_id,n.org_id)
            LEFT JOIN requests r ON (r.id,r.org_id)=(n.request_id,n.org_id)
            WHERE n.status='pending' AND n.attempts<:max
              AND n.deliver_after<=:now AND n.next_attempt_at<=:now
            ORDER BY n.deliver_after,n.id LIMIT 100 FOR UPDATE OF n SKIP LOCKED
        """), {"now": now, "max": MAX_ATTEMPTS}).mappings().all()
        for row in rows:
            if not row["is_active"]:
                connection.execute(text("""
                    UPDATE notifications SET status='failed',last_error='RECIPIENT_UNAVAILABLE' WHERE id=:id
                """), {"id": row["id"]})
                _failure(connection, row, "RECIPIENT_UNAVAILABLE", row["attempts"])
                continue
            after = deliver_after(now, row["role"], row["risk_level"], row["risk_category"])
            if after > now:
                connection.execute(text("UPDATE notifications SET next_attempt_at=:after WHERE id=:id"),
                                   {"id": row["id"], "after": after})
                continue
            try:
                with connection.begin_nested():
                    _deliver(connection, row, now)
                sent += 1
            except Exception:
                attempts = row["attempts"] + 1
                after = deliver_after(now + timedelta(seconds=RETRY_SECONDS * 2 ** (attempts-1)),
                                      row["role"], row["risk_level"], row["risk_category"])
                # 예외 원문에는 개인정보가 섞일 수 있어 고정 실패 코드만 남겨요.
                connection.execute(text("""
                    UPDATE notifications SET attempts=:attempts,last_error='DELIVERY_FAILED',
                        status=:status,next_attempt_at=:after WHERE id=:id
                """), {"id": row["id"], "attempts": attempts, "after": after,
                       "status": "failed" if attempts >= MAX_ATTEMPTS else "pending"})
                _failure(connection, row, "DELIVERY_FAILED", attempts)
    return sent
