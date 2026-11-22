"""영상에도 현재 보호자·사진 권한을 적용해요. 원본 파일은 복사하지 않아요."""

import logging

from app.core import media
from app.core.config import settings
from app.core.errors import ApiError

JOB_TIMEOUT = 300
ENCODE_TIMEOUT = 120
SECONDS_PER_PHOTO = 2


def enabled():
    if not settings.feature_growth_video:
        raise ApiError(404, "NOT_FOUND")


def view(row):
    from app.api.schemas.growth_video import GrowthVideo
    return GrowthVideo.model_validate({**row, "file_url": (
        f"/api/v1/growth-videos/{row['id']}/file" if row["status"] == "succeeded" else None)}).model_dump()


def source_photos(user, ids):
    from app import backend
    try:
        result = [backend.feed.file(user, photo_id) for photo_id in ids]
    except ApiError:
        raise ApiError(404, "NOT_FOUND") from None
    if any(not media.path(p["storage_path"]).is_file() for p in result):
        raise ApiError(404, "NOT_FOUND")
    return result


def select(user, candidates, limit):
    selected = []
    for row in sorted(candidates, key=lambda r: (r["created_at"], r["id"])):
        try:
            source_photos(user, [row["id"]])
        except ApiError:
            continue
        selected.append(row["id"])
        if len(selected) == limit:
            break
    if len(selected) < 3:
        raise ApiError(422, "VALIDATION_FAILED", problem="지금 볼 수 있는 아이 사진이 3장 이상 필요해요.")
    return selected


def remove(name):
    if name:
        try:
            media.remove(name)
        except OSError:
            logging.getLogger(__name__).warning("growth_video_delete_failed")
