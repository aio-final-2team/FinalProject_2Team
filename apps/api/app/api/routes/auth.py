"""1·2번 API: 로그인, 내 정보."""

from fastapi import APIRouter, Depends

from app.api.schemas.auth import ChildOut, LoginIn, LoginOut, MeOut, UserOut
from app.api.schemas.common import errors
from app.core.auth import CurrentUser, current_user, issue_token
from app.core.errors import ApiError
from app.backend import store

router = APIRouter(tags=["인증"])


def _me(user: store.User) -> MeOut:
    classroom_ids = store.classroom_ids_of(user.id) if user.role == "teacher" else []
    children = store.children_of(user.id) if user.role == "parent" else []
    return MeOut(
        user=UserOut(id=user.id, role=user.role, display_name=user.display_name, org_id=user.org_id,
                     classroom_ids=classroom_ids),
        children=[ChildOut(id=c.id, display_name=c.display_name, classroom_id=c.classroom_id) for c in children],
    )


@router.post("/auth/login", response_model=LoginOut, responses=errors(401, 422),
             summary="로그인, 토큰 발급 (FR-01)")
def login(body: LoginIn) -> LoginOut:
    user = store.find_user_by_login(body.login_id)
    if user is None or user.password != body.password or not user.is_active:
        raise ApiError(401, "UNAUTHENTICATED", "아이디나 비밀번호가 맞지 않아요.")
    return LoginOut(access_token=issue_token(user), **_me(user).model_dump())


@router.get("/me", response_model=MeOut, responses=errors(401), summary="내 정보 (FR-01)")
def me(user: CurrentUser = Depends(current_user)) -> MeOut:
    return _me(store.get_user(user.id))
