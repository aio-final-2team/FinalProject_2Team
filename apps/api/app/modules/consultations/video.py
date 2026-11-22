"""T56 SQLAlchemy Core 예약 조회와 요청 연결 이력이에요."""

from sqlalchemy import text

from app.core import video_consult as rules
from app.core.db import transaction
from app.core.errors import ApiError
from app.modules.requests.events import record as request_event


def access(user, booking_id):
    with transaction() as connection:
        row = connection.execute(text("""
            SELECT b.*, lower(b.period) AS start, upper(b.period) AS end, r.requester_id
            FROM consultation_bookings b JOIN requests r ON (r.id,r.org_id)=(b.request_id,b.org_id)
            WHERE b.id=:id AND b.org_id=:org
        """), {"id": booking_id, "org": user.org_id}).mappings().one_or_none()
    def deny():
        # 먼저 업무 연결을 닫았으므로 403 예외가 나도 이력은 커밋돼요.
        record(user, booking_id, "permission_denied")
        raise ApiError(403, "FORBIDDEN")
    return rules.check(user, row, deny)


def record(user, booking_id, action):
    with transaction() as connection:
        req = connection.execute(text("""
            SELECT r.* FROM requests r JOIN consultation_bookings b ON (r.id,r.org_id)=(b.request_id,b.org_id)
            WHERE b.id=:id AND b.org_id=:org
        """), {"id": booking_id, "org": user.org_id}).mappings().one()
        request_event(connection, req, action, actor_type="user", actor_id=user.id, booking_id=str(booking_id))
