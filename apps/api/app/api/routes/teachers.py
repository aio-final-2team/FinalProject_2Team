"""70번 API: 원장이 카드 담당을 바꿀 때(19번) 고를 선생님 목록이에요.

같은 기관의 활성 선생님과 오늘 맡은 반만 줘요. 연락처·로그인 ID는 넣지 않아요.
"""

from fastapi import APIRouter, Depends

from app import backend
from app.api.schemas.common import errors
from app.api.schemas.teachers import TeachersOut
from app.core.auth import CurrentUser, require_roles

router = APIRouter(tags=["교직원 받은함"])


@router.get("/staff/teachers", response_model=TeachersOut, responses=errors(401, 403))
def teachers(user: CurrentUser = Depends(require_roles("director"))):
    return {"items": backend.users.teachers_of(user.org_id)}
