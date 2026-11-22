"""[제안][선택] T56 참여자·시간과 60초 신호 접속권을 검사해요."""

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
from threading import Lock

import jwt
import logging
import re

from app import backend
from app.core.config import settings
from app.core.constants import VIDEO_SIGNAL_AUDIENCE
from app.core.errors import ApiError


_used_tickets = {}
_ticket_lock = Lock()


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
                         "role": user.role, "org": str(user.org_id), "ver": account.token_version, "jti": str(uuid4()),
                         "iat": int(issued.timestamp()), "exp": int(expires.timestamp())},
                        settings.jwt_secret, algorithm="HS256")
    return {"booking_id": booking_id, "opens_at": row["opens_at"], "closes_at": row["closes_at"],
            "ice_servers": settings.video_ice_servers, "signal_path": f"/api/v1/consultations/{booking_id}/signal",
            "ticket": ticket, "ticket_expires_at": datetime.fromtimestamp(int(expires.timestamp()), timezone.utc)}


def ticket_user(ticket, booking_id):
    try:
        claims = jwt.decode(ticket, settings.jwt_secret, algorithms=["HS256"], audience=VIDEO_SIGNAL_AUDIENCE,
                            options={"require": ["sub", "booking", "role", "org", "ver", "iat", "exp", "aud", "jti"]})
        user = recheck_user(claims)
        if claims["booking"] != str(booking_id) or not isinstance(claims["jti"], str) or not claims["jti"]:
            raise ValueError
        with _ticket_lock:
            current = datetime.now(timezone.utc).timestamp()
            for jti, expiry in list(_used_tickets.items()):
                if expiry <= current:
                    del _used_tickets[jti]
            if claims["jti"] in _used_tickets:
                raise ValueError
            _used_tickets[claims["jti"]] = claims["exp"]
    except (jwt.PyJWTError, ValueError, TypeError, KeyError):
        raise ApiError(401, "UNAUTHENTICATED") from None
    return user, claims


def recheck_user(claims):
    """연결 뒤에는 접속권 만료 대신 현재 계정·토큰 판을 다시 봐요."""
    from app.core.auth import CurrentUser
    user = backend.users.get_user(UUID(claims["sub"]))
    if (user is None or not user.is_active or claims["role"] != user.role
            or claims["org"] != str(user.org_id) or claims["ver"] != user.token_version):
        raise ApiError(401, "UNAUTHENTICATED")
    return CurrentUser(id=user.id, org_id=user.org_id, role=user.role)


class TicketLogFilter(logging.Filter):
    def filter(self, record):
        def redact(value):
            return re.sub(r"([?&]ticket=)[^&\s\"]+", r"\1[redacted]", value) if isinstance(value, str) else value
        record.msg = redact(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(redact(value) for value in record.args)
        elif isinstance(record.args, dict):
            record.args = {key: redact(value) for key, value in record.args.items()}
        return True


def install_log_filter():
    # uvicorn은 HTTP를 access, WebSocket 접속을 error 로거에 남겨요.
    for name in ("uvicorn.access", "uvicorn.error"):
        logger = logging.getLogger(name)
        if not any(isinstance(item, TicketLogFilter) for item in logger.filters):
            logger.addFilter(TicketLogFilter())


install_log_filter()
