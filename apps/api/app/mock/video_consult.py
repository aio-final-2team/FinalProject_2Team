"""T56 메모리 예약 조회. 거부·입장·퇴장 이력을 요청에 연결해요."""

from app.core import video_consult as rules
from app.core.errors import ApiError
from app.mock import store


def access(user, booking_id):
    with store._lock:
        booking = store.state().bookings.get(booking_id)
        row = None
        if booking is not None:
            req = store.state().requests[booking.request_id]
            row = {**booking.__dict__, **booking.period, "requester_id": req.requester_id}
        def deny():
            record(user, booking_id, "permission_denied")
            raise ApiError(403, "FORBIDDEN")
        return rules.check(user, row, deny)


def record(user, booking_id, action):
    with store._lock:
        booking = store.state().bookings[booking_id]
        store.add_event(store.state().requests[booking.request_id], action, actor_type="user", actor_id=user.id,
                        booking_id=str(booking_id))
