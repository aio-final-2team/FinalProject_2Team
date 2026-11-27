"""64·65번 API: 내 알림 받는 시간을 조회·저장해요."""

from fastapi import APIRouter, Depends

from app import backend
from app.api.schemas.common import errors
from app.api.schemas.notification_settings import NotificationSettings
from app.core.auth import CurrentUser, require_roles

router = APIRouter(tags=["알림 설정"])


@router.get("/me/notification-settings", response_model=NotificationSettings, responses=errors(401, 403))
def get_settings(user: CurrentUser = Depends(require_roles("teacher", "director"))):
    return backend.notification_settings.get(user.id)


@router.patch("/me/notification-settings", response_model=NotificationSettings, responses=errors(401, 403, 422))
def patch_settings(body: NotificationSettings, user: CurrentUser = Depends(require_roles("teacher", "director"))):
    return backend.notification_settings.save(user, body)
