"""JWT 발급·검증과 역할 검사(API 설계 문서 1.2, 4.2).

토큰에는 sub·org·role·ver·exp만 넣는다. 반 소속·아이 관계는 요청마다 저장소에서 본다.
"""

from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.core.config import settings
from app.core.errors import ApiError
from app.mock import store

Role = Literal["parent", "teacher", "director"]
_bearer = HTTPBearer(auto_error=False)


class CurrentUser(BaseModel):
    id: UUID
    org_id: UUID
    role: Role


def issue_token(user: store.User) -> str:
    now = datetime.now(timezone.utc)
    claims = {
        "sub": str(user.id),
        "org": str(user.org_id),
        "role": user.role,
        "ver": user.token_version,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=settings.jwt_access_ttl_hours)).timestamp()),
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm="HS256")


def current_user(cred: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> CurrentUser:
    if cred is None:
        raise ApiError(401, "UNAUTHENTICATED")
    try:
        claims = jwt.decode(cred.credentials, settings.jwt_secret, algorithms=["HS256"])
        user = store.get_user(UUID(claims["sub"]))
    except (jwt.PyJWTError, KeyError, ValueError):
        raise ApiError(401, "UNAUTHENTICATED") from None
    if user is None or not user.is_active or claims.get("ver") != user.token_version:
        raise ApiError(401, "UNAUTHENTICATED")
    return CurrentUser(id=user.id, org_id=user.org_id, role=user.role)


def require_roles(*roles: Role):
    """역할이 다르면 403 FORBIDDEN_ROLE. 범위(기관·반·내 아이) 밖은 각 라우트가 404로 막는다."""

    def dependency(user: CurrentUser = Depends(current_user)) -> CurrentUser:
        if user.role not in roles:
            raise ApiError(403, "FORBIDDEN_ROLE")
        return user

    return dependency
