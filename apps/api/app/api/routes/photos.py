"""75~77번 API: 아이 프로필 사진과 급식 참고 사진(시연용 가상 사진)."""

import os
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app import backend
from app.api.schemas.common import errors
from app.api.schemas.photos import MealPhotoList
from app.core.auth import CurrentUser, current_user
from app.core.errors import ApiError

router = APIRouter(tags=["사진"])
IMAGE = {200: {"content": {kind: {"schema": {"type": "string", "format": "binary"}}
                           for kind in ("image/jpeg", "image/png", "image/webp")}}}


class OpenFileResponse(StreamingResponse):
    def __init__(self, handle, kind):
        self.handle = handle
        super().__init__(iter(lambda: handle.read(64 * 1024), b""), media_type=kind, headers={
            "Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff",
            "Content-Disposition": "inline", "Content-Length": str(os.fstat(handle.fileno()).st_size)})

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            self.handle.close()


def _open(found):
    try:
        handle = found["path"].open("rb")
    except FileNotFoundError:
        raise ApiError(404, "NOT_FOUND") from None
    return OpenFileResponse(handle, found["media_type"])


@router.get("/children/{child_id}/profile-photo", responses={**IMAGE, **errors(401, 404, 422)},
            response_class=StreamingResponse, summary="아이 프로필 사진")
def profile_photo(child_id: UUID, user: CurrentUser = Depends(current_user)):
    return _open(backend.photos.profile_file(user, child_id))


@router.get("/meal-photos", response_model=MealPhotoList, responses=errors(401, 422), summary="급식 참고 사진 목록")
def meal_photos(date_from: date = Query(alias="from"), date_to: date = Query(alias="to"),
                user: CurrentUser = Depends(current_user)):
    return backend.photos.meals(user, date_from, date_to)


@router.get("/meal-photos/{meal_date}/file", responses={**IMAGE, **errors(401, 404, 422)},
            response_class=StreamingResponse, summary="급식 참고 사진 파일")
def meal_photo_file(meal_date: date, user: CurrentUser = Depends(current_user)):
    return _open(backend.photos.meal_file(user, meal_date))
