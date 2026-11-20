"""T48 알림 생성. 지연 기록은 내부 입구이며 공개 HTTP 계약은 늘리지 않아요."""

from datetime import datetime, timedelta

from sqlalchemy import text

from app.core import scope
from app.core.consultation_alerts import ENDING, alerts, message
from app.core.constants import NOTIFICATION_TITLES
from app.core.db import transaction
from app.core.errors import ApiError
from app.core.schedule import KST, deliver_after
from app.modules.consultations.slots import find_consult_slots
from app.modules.requests.events import record


def report_delay(user, booking_id, expected_end_at, *, now=None):
    """담임이 예상 종료를 기록해요. 화면/API 연결 전에도 호출·시험할 수 있는 내부 입구예요."""
    now = now or datetime.now(KST)
    with transaction() as connection:
        initial = connection.execute(text("SELECT * FROM consultation_bookings WHERE id=:id AND org_id=:org"),
                                     {"id": booking_id, "org": user.org_id}).mappings().one_or_none()
        if initial is None:
            scope._checked(user, None, False, "booking", booking_id)
        scope.request_in_scope(user, initial["request_id"], connection=connection)
        # 요청 → 예약 순서예요. 예약 확정 경로와 같은 순서를 유지해요.
        req = connection.execute(text("SELECT * FROM requests WHERE id=:id FOR NO KEY UPDATE"),
                                 {"id": initial["request_id"]}).mappings().one()
        row = connection.execute(text("SELECT * FROM consultation_bookings WHERE id=:id FOR UPDATE"),
                                 {"id": booking_id}).mappings().one()
        if user.role != "teacher" or row["teacher_id"] != user.id:
            raise ApiError(403, "FORBIDDEN_ROLE")
        if row["status"] != "confirmed" or req["status"] != "sent_or_booked":
            raise ApiError(409, "INVALID_TRANSITION")
        if (expected_end_at.tzinfo is None or row["period"].lower > now
                or expected_end_at <= max(row["period"].upper, now)):
            raise ApiError(422, "VALIDATION_FAILED")
        if row["expected_end_at"] == expected_end_at:
            return
        connection.execute(text("UPDATE consultation_bookings SET expected_end_at=:until WHERE id=:id"),
                           {"id": booking_id, "until": expected_end_at})
        record(connection, req, "consultation_delay_reported", actor_type="user", actor_id=user.id,
               booking_id=str(booking_id), expected_end_at=expected_end_at.isoformat())


def alternatives(connection, booking, until, now):
    rules = connection.scalars(text("""
        SELECT rule_json FROM memory_rules WHERE org_id=:org AND owner_id=:teacher
          AND status='active' AND reason_code='slot_unavailable' ORDER BY created_at,id
    """), {"org": booking["org_id"], "teacher": booking["teacher_id"]}).all()
    result = []
    for offset in range(14):
        result.extend(find_consult_slots(connection, booking["teacher_id"], now.date()+timedelta(days=offset),
                                        org_id=booking["org_id"], rules=rules, now=now, not_before=until))
        if len(result) >= 3:
            break
    return result[:3]


def sweep_consultation_notifications(now=None):
    now = (now or datetime.now(KST)).astimezone(KST)
    count = 0
    with transaction() as connection:
        # 중복 Beat·수동 재실행은 한 번씩 처리해요. 지연 기록과는 예약 행 잠금으로 맞춰요.
        if not connection.scalar(text("SELECT pg_try_advisory_xact_lock(hashtextextended('consult:reminders',0))")):
            return 0
        rows = [dict(row) for row in connection.execute(text("""
            SELECT b.*,lower(b.period) AS start,coalesce(b.expected_end_at,upper(b.period)) AS end,
                   upper(b.period) AS scheduled_end,r.requester_id
            FROM consultation_bookings b JOIN requests r ON (r.id,r.org_id)=(b.request_id,b.org_id)
            WHERE b.status='confirmed' AND r.status='sent_or_booked' AND r.type='consultation'
              AND (upper(b.period)>:now OR b.expected_end_at>:now)
            ORDER BY b.id FOR UPDATE OF b
        """), {"now": now}).mappings()]
        for booking, kind, until in alerts(rows, now):
            recipients = [booking["teacher_id"]] if kind == ENDING else [booking["teacher_id"], booking["requester_id"]]
            keys = [f"consultation:{booking['id']}:{kind}:{recipient}" for recipient in recipients]
            if connection.scalar(text("SELECT count(*) FROM notifications WHERE dedupe_key=ANY(:keys)"),
                                 {"keys": keys}) == len(keys):
                continue
            candidates = alternatives(connection, booking, until, now) if until else []
            saved = 0
            for recipient, key in zip(recipients, keys):
                role = connection.scalar(text("SELECT role FROM users WHERE id=:id AND org_id=:org AND is_active"),
                                         {"id": recipient, "org": booking["org_id"]})
                if role is None:
                    continue
                after = deliver_after(now, role)
                if after >= booking["end"]:
                    continue
                saved += connection.execute(text("""
                    INSERT INTO notifications(org_id,recipient_id,request_id,kind,title,body,dedupe_key,
                                              deliver_after,next_attempt_at,created_at)
                    VALUES (:org,:recipient,:request,:kind,:title,:body,:key,:after,:now,:now)
                    ON CONFLICT (dedupe_key) DO NOTHING RETURNING id
                """), {"org": booking["org_id"], "recipient": recipient, "request": booking["request_id"],
                       "kind": kind, "title": NOTIFICATION_TITLES[kind], "body": message(booking, kind, candidates),
                       "key": key, "after": after, "now": now}).scalar_one_or_none() is not None
            if saved:
                req = {"org_id": booking["org_id"], "id": booking["request_id"]}
                record(connection, req, "consultation_reminded", booking_id=str(booking["id"]), kind=kind)
                count += saved
    return count
