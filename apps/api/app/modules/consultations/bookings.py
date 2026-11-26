"""API의 카드 담당 교사 확인 뒤 호출해요. 최종 충돌 판정은 DB 배제 제약이 맡아요."""

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.errors import ApiError


def lock_resources(connection, slots):
    # 여러 후보도 담임 전체 → 상담실 전체, 각 ID 순서로 잡아요.
    for kind, field in (("staff", "teacher_id"), ("room", "room_id")):
        for resource_id in sorted({str(slot[field]) for slot in slots}):
            connection.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
                               {"key": f"consult:{kind}:{resource_id}"})


def book_slot(connection, slot, *, request_id, confirmed_by):
    try:
        lock_resources(connection, [slot])
        if connection.scalar(text("SELECT :start<=clock_timestamp()"), {"start": slot["period"].lower}):
            raise ApiError(409, "SLOT_PAST")
        if connection.scalar(text("""
            SELECT EXISTS (SELECT 1 FROM staff_busy_blocks
              WHERE org_id=:org AND user_id=:teacher AND period && :period)
            OR EXISTS (SELECT 1 FROM consultation_bookings b
              WHERE b.org_id=:org AND b.status='confirmed'
                AND (b.teacher_id=:teacher OR b.room_id=:room)
                AND tstzrange(lower(b.period),coalesce(b.expected_end_at,upper(b.period)),'[)') && :period)
        """), {"org": slot["org_id"], "teacher": slot["teacher_id"], "room": slot["room_id"], "period": slot["period"]}):
            raise ApiError(409, "SLOT_TAKEN")
        return connection.scalar(text("""
            INSERT INTO consultation_bookings (org_id,request_id,slot_id,teacher_id,room_id,period,confirmed_by)
            VALUES (:org,:request,:slot,:teacher,:room,:period,:user) RETURNING id
        """), {"org": slot["org_id"], "request": request_id, "slot": slot["id"],
               "teacher": slot["teacher_id"], "room": slot["room_id"], "period": slot["period"], "user": confirmed_by})
    except DBAPIError as error:
        if error.orig.sqlstate in ("40P01", "23P01") or (
            error.orig.sqlstate == "23505"
            and error.orig.diag.constraint_name == "consultation_bookings_one_per_request"
        ):
            # 호출 쪽 savepoint를 되돌린 뒤 승인 없이 재제안·상태·알림을 저장해요.
            raise ApiError(409, "SLOT_TAKEN") from error
        raise
