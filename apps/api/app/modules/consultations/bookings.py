"""API의 담임 확인 뒤 호출해요. 최종 충돌 판정은 DB 배제 제약이 맡아요."""

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.errors import ApiError


def book_slot(connection, slot, *, request_id, confirmed_by):
    try:
        return connection.scalar(text("""
            INSERT INTO consultation_bookings (org_id,request_id,slot_id,teacher_id,room_id,period,confirmed_by)
            VALUES (:org,:request,:slot,:teacher,:room,:period,:user) RETURNING id
        """), {"org": slot["org_id"], "request": request_id, "slot": slot["id"],
               "teacher": slot["teacher_id"], "room": slot["room_id"], "period": slot["period"], "user": confirmed_by})
    except IntegrityError as error:
        if error.orig.sqlstate == "23P01" or (
            error.orig.sqlstate == "23505"
            and error.orig.diag.constraint_name == "consultation_bookings_one_per_request"
        ):
            # 호출 쪽 트랜잭션도 빠져나가므로 승인·상태·알림은 함께 롤백돼요.
            raise ApiError(409, "SLOT_TAKEN") from error
        raise
