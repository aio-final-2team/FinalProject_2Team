"""[제안][선택] T56 참여자·시간과 60초 신호 접속권을 검사해요."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt

from app import backend
from app.core.config import settings
from app.core.constants import VIDEO_SIGNAL_AUDIENCE
from app.core.errors import ApiError


def now():
    return datetime.now(timezone.utc)


def enabled():
    if not settings.feature_video_consult:
        raise ApiError(404, "NOT_FOUND")


def check(user, row, deny):
    if row is None or row["org_id"] != user.org_id:
        raise ApiError(404, "NOT_FOUND")
    if not ((user.role == "teacher" and row["teacher_id"] == user.id)
            or (user.role == "parent" and row["requester_id"] == user.id)):
        deny()
    if row["status"] != "confirmed":
        raise ApiError(409, "CONFLICT", "확정된 예약만 접속할 수 있어요.")
    opens = row["start"] - timedelta(minutes=10)
    closes = (row["expected_end_at"] or row["end"]) + timedelta(minutes=30)
    current = now()
    if current < opens or current > closes:
        raise ApiError(409, "CONFLICT", "상담방이 열리는 시간을 확인해 주세요.",
                       reason="room_not_open" if current < opens else "room_closed",
                       opens_at=opens.isoformat(), closes_at=closes.isoformat())
    return {**row, "opens_at": opens, "closes_at": closes}


def room(user, booking_id):
    row = backend.video_consult.access(user, booking_id)
    issued = datetime.now(timezone.utc)
    expires = issued + timedelta(seconds=60)
    account = backend.users.get_user(user.id)
    ticket = jwt.encode({"aud": VIDEO_SIGNAL_AUDIENCE, "sub": str(user.id), "booking": str(booking_id),
                         "role": user.role, "org": str(user.org_id), "ver": account.token_version,
                         "iat": int(issued.timestamp()), "exp": int(expires.timestamp())},
                        settings.jwt_secret, algorithm="HS256")
    return {"booking_id": booking_id, "opens_at": row["opens_at"], "closes_at": row["closes_at"],
            "ice_servers": settings.video_ice_servers, "signal_path": f"/api/v1/consultations/{booking_id}/signal",
            "ticket": ticket, "ticket_expires_at": datetime.fromtimestamp(int(expires.timestamp()), timezone.utc)}


def ticket_user(ticket, booking_id):
    from app.core.auth import CurrentUser
    try:
        claims = jwt.decode(ticket, settings.jwt_secret, algorithms=["HS256"], audience=VIDEO_SIGNAL_AUDIENCE,
                            options={"require": ["sub", "booking", "role", "org", "ver", "iat", "exp", "aud"]})
        user = backend.users.get_user(UUID(claims["sub"]))
        if (user is None or not user.is_active or claims["booking"] != str(booking_id)
                or claims["role"] != user.role or claims["org"] != str(user.org_id)
                or claims["ver"] != user.token_version):
            raise ValueError
    except (jwt.PyJWTError, ValueError, TypeError, KeyError):
        raise ApiError(401, "UNAUTHENTICATED") from None
    return CurrentUser(id=user.id, org_id=user.org_id, role=user.role)
