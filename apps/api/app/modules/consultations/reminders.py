"""T48 알림 생성. 담임의 명시된 지연과 시각별 알림을 저장해요."""

from datetime import datetime, time, timedelta

from sqlalchemy import text

from app.core import scope
from app.core.consultation_alerts import DELAYED, ENDING, alerts, message, notification_key, valid_delay
from app.core.constants import NOTIFICATION_TITLES
from app.core.db import transaction
from app.core.errors import ApiError
from app.core.schedule import KST, deliver_after
from app.modules.consultations.slots import find_consult_slots
from app.modules.consultations.bookings import lock_resources
from app.modules.requests.events import record


def report_delay(user, booking_id, expected_end_at, *, now=None):
    now = (now or datetime.now(KST)).astimezone(KST)
    with transaction() as connection:
        initial = connection.execute(text("SELECT * FROM consultation_bookings WHERE id=:id AND org_id=:org"),
                                     {"id": booking_id, "org": user.org_id}).mappings().one_or_none()
        if initial is None:
            scope._checked(user, None, False, "booking", booking_id)
        scoped_request = scope.request_in_scope(user, initial["request_id"], connection=connection)
        if user.role != "teacher" or initial["teacher_id"] != user.id:
            raise ApiError(403, "FORBIDDEN_ROLE")
        scope.classroom_in_scope(user, scoped_request["classroom_id"], connection=connection)
        # 점검과 직렬화하고 T35와 요청 → 담임 → 상담실 → 예약 순서를 맞춰요.
        connection.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('consult:reminders',0))"))
        req = connection.execute(text("SELECT * FROM requests WHERE id=:id FOR NO KEY UPDATE"),
                                 {"id": initial["request_id"]}).mappings().one()
        lock_resources(connection, [initial])
        row = connection.execute(text("SELECT * FROM consultation_bookings WHERE id=:id FOR UPDATE"),
                                 {"id": booking_id}).mappings().one()
        if row["status"] != "confirmed" or req["status"] != "sent_or_booked":
            raise ApiError(409, "INVALID_TRANSITION")
        if not valid_delay(row["period"].lower, row["period"].upper, expected_end_at, now):
            raise ApiError(422, "VALIDATION_FAILED")
        expected_end_at = expected_end_at.astimezone(KST)
        if row["expected_end_at"] != expected_end_at:
            connection.execute(text("UPDATE consultation_bookings SET expected_end_at=:until WHERE id=:id"),
                               {"id": booking_id, "until": expected_end_at})
            record(connection, req, "consultation_delay_reported", actor_type="user", actor_id=user.id,
                   booking_id=str(booking_id), expected_end_at=expected_end_at.isoformat())
            current = {"id": booking_id, "end": expected_end_at, "org_id": row["org_id"],
                       "request_id": row["request_id"]}
            supersede(connection, current, ENDING, [notification_key(current, ENDING, None, user.id)])
        affected = connection.scalar(text("""
            SELECT count(*) FROM consultation_bookings b JOIN requests r ON r.id=b.request_id AND r.org_id=b.org_id
            WHERE b.org_id=:org AND b.id<>:id AND b.status='confirmed' AND r.status='sent_or_booked'
              AND r.type='consultation' AND lower(b.period)>=:end AND lower(b.period)<:until
              AND coalesce(b.expected_end_at,upper(b.period))>:now
              AND (b.teacher_id=:teacher OR b.room_id=:room)
        """), {"org": row["org_id"], "id": booking_id, "end": row["period"].upper,
               "until": expected_end_at, "now": now, "teacher": row["teacher_id"], "room": row["room_id"]})
        return {"booking": {"id": booking_id, "period": {"start": row["period"].lower, "end": row["period"].upper},
                            "status": row["status"], "expected_end_at": expected_end_at}, "affected_bookings": affected}


def supersede(connection, booking, kind, keys):
    # 보낸 행은 보존하고, 아직 발송하지 않은 행만 held로 돌려요. 같은 옛 제안은 한 번만 기록해요.
    old = connection.execute(text("""
        SELECT n.id,n.status FROM notifications n
        WHERE n.org_id=:org AND n.request_id=:request AND n.kind=:kind
          AND n.dedupe_key LIKE :prefix AND NOT (n.dedupe_key=ANY(:keys))
          AND NOT EXISTS (SELECT 1 FROM events e WHERE e.request_id=n.request_id
            AND e.action='consultation_reminded' AND e.detail->>'outcome'='superseded'
            AND e.detail->>'notification_id'=n.id::text)
        ORDER BY n.id FOR UPDATE OF n
    """), {"org": booking["org_id"], "request": booking["request_id"], "kind": kind,
           "prefix": f"consultation:{booking['id']}:{kind}:%", "keys": keys}).mappings().all()
    for row in old:
        if row["status"] == "pending":
            connection.execute(text("UPDATE notifications SET status='held',last_error='SUPERSEDED' WHERE id=:id"),
                               {"id": row["id"]})
        record(connection, {"org_id": booking["org_id"], "id": booking["request_id"]}, "consultation_reminded",
               booking_id=str(booking["id"]), kind=kind, notification_id=row["id"], outcome="superseded")


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


def sweep_consultation_notifications(now=None, *, teacher_id=None, day=None):
    now = (now or datetime.now(KST)).astimezone(KST)
    filters, params = "", {"now": now}
    if teacher_id is not None:
        filters += " AND b.teacher_id=:teacher"
        params["teacher"] = teacher_id
    if day is not None:
        filters += " AND lower(b.period)>=:day_start AND lower(b.period)<:day_end"
        params["day_start"] = datetime.combine(day, time.min, KST)
        params["day_end"] = params["day_start"] + timedelta(days=1)
    count = 0
    with transaction() as connection:
        # 중복 Beat·수동 재실행과 지연 수정을 같은 자문 잠금으로 맞춰요.
        if not connection.scalar(text("SELECT pg_try_advisory_xact_lock(hashtextextended('consult:reminders',0))")):
            return 0
        rows = [dict(row) for row in connection.execute(text("""
            SELECT b.*,lower(b.period) AS start,coalesce(b.expected_end_at,upper(b.period)) AS end,
                   upper(b.period) AS scheduled_end,r.requester_id
            FROM consultation_bookings b JOIN requests r ON (r.id,r.org_id)=(b.request_id,b.org_id)
            WHERE b.status='confirmed' AND r.status='sent_or_booked' AND r.type='consultation'
              AND (upper(b.period)>:now OR b.expected_end_at>:now)
              AND lower(b.period)<:now+interval '1 day'
        """ + filters + " ORDER BY b.id"), params).mappings()]
        due = list(alerts(rows, now))
        delayed = {b["id"]: [notification_key(b, kind, until, recipient)
                              for recipient in (b["teacher_id"], b["requester_id"])]
                   for b, kind, until in due if kind == DELAYED}
        for row in rows:
            # 현재 지연 대상이 없으면 자연 종료를 제안 변경으로 기록하지 않아요.
            if row["id"] in delayed:
                supersede(connection, row, DELAYED, delayed[row["id"]])
        for booking, kind, until in due:
            recipients = [booking["teacher_id"]] if kind == ENDING else [booking["teacher_id"], booking["requester_id"]]
            keys = [notification_key(booking, kind, until, recipient) for recipient in recipients]
            existing = set(connection.scalars(text("SELECT dedupe_key FROM notifications WHERE dedupe_key=ANY(:keys)"),
                                               {"keys": keys}))
            roles = dict(connection.execute(text("SELECT id,role FROM users WHERE org_id=:org AND is_active AND id=ANY(:ids)"),
                                            {"org": booking["org_id"], "ids": recipients}).all())
            pending = []
            for recipient, key in zip(recipients, keys):
                if recipient not in roles or key in existing:
                    continue
                after = now if kind == ENDING else deliver_after(now, roles[recipient], user_id=recipient,
                                                               connection=connection)
                if after < booking["end"]:
                    pending.append((recipient, key, after))
            if not pending:
                continue
            # 알림이 필요한 예약만 잠가요. 지연 변경은 위 자문 잠금으로 함께 보호돼요.
            live = connection.scalar(text("SELECT status FROM consultation_bookings WHERE id=:id FOR UPDATE"),
                                     {"id": booking["id"]})
            if live != "confirmed":
                continue
            supersede(connection, booking, kind, keys)
            candidates = alternatives(connection, booking, until, now) if until else []
            saved = 0
            for recipient, key, after in pending:
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
                record(connection, req, "consultation_reminded", booking_id=str(booking["id"]), kind=kind,
                       until=(until or booking["end"]).isoformat(),
                       candidates=[{k: v.isoformat() for k, v in candidate.items() if k in ("start", "end")}
                                   for candidate in candidates])
                count += saved
    return count
