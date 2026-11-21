"""T24 단계의 업무 API 경계. 영역 구현을 연결할 때 해당 의존성을 걷는다.

남은 경계: 상담 시간 선택·확정(T35), 기억 규칙 결정(T39), 자료 쓰기·상세.
인증·알림장·요청·받은함·카드 결정·현황·알림은 core.auth와 backend 영역 모듈을 쓴다.
"""

from uuid import UUID

from fastapi import Depends, Request

from app.core.auth import CurrentUser, current_user, require_roles
from app.core.config import settings
from app.core.errors import ApiError


def _pending(request: Request, user: CurrentUser) -> CurrentUser:
    if settings.data_backend == "db":
        from app.core import scope

        # 상세 URL의 범위 검사는 업무 구현 전에도 작동한다.
        for name, check in (("request_id", scope.request_in_scope), ("card_id", scope.card_in_scope),
                            ("note_id", scope.note_in_scope), ("input_id", scope.note_input_in_scope),
                            ("classroom_id", scope.classroom_in_scope)):
            value = request.path_params.get(name)
            if (name == "classroom_id" and value is None
                    and request.scope["route"].name == "note_list"):
                value = request.query_params.get(name)
            if value is not None:
                try:
                    resource_id = UUID(value)
                except ValueError:
                    # 경로 형식 오류는 원래 라우트의 Pydantic 검사가 422로 답한다.
                    return user
                check(user, resource_id)
        raise ApiError(501, "NOT_IMPLEMENTED")
    return user


def workflow_user(request: Request, user: CurrentUser = Depends(current_user)) -> CurrentUser:
    return _pending(request, user)


def require_workflow_roles(*roles):
    def dependency(request: Request, user: CurrentUser = Depends(require_roles(*roles))) -> CurrentUser:
        return _pending(request, user)
    return dependency
