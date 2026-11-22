"""영상에도 현재 보호자·사진 권한을 적용해요. 원본 파일은 복사하지 않아요."""

import logging

from app.core import feed, media
from app.core.config import settings
from app.core.errors import ApiError

QUEUED_TIMEOUT = 1800
JOB_TIMEOUT = 360
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
    result = backend.growth_videos.sources(user, ids)
    if len(result) != len(ids):
        raise ApiError(404, "NOT_FOUND")
    return result


def visible_sources(user, photos, posts, children, classrooms, organizations):
    """영상 내부의 사진 검사는 감사 기록을 남기지 않아요."""
    def deny(status):
        raise ApiError(status, "NOT_FOUND")
    result = []
    for photo in photos:
        post = posts.get(photo["post_id"])
        if not post or post["deleted_at"] or post["status"] != "published":
            continue
        if post["lane"] != "neighborhood" and post["org_id"] != user.org_id:
            continue
        try:
            feed.lane_access(user, post["lane"], post["classroom_id"] or post["org_id"],
                             classrooms, children, deny, organizations)
        except ApiError:
            continue
        if feed.visible(user, post, photo, children) and media.path(photo["storage_path"]).is_file():
            result.append(photo)
    return result


def check_capacity(rows):
    if any(r["status"] in {"queued", "running"} for r in rows):
        raise ApiError(409, "CONFLICT", "이 아이의 성장 영상을 만들고 있어요. 끝난 뒤 다시 요청해 주세요.")
    if sum(r["status"] == "succeeded" for r in rows) >= 5:
        raise ApiError(409, "CONFLICT", "성장 영상은 아이마다 5개까지 보관해요. 기존 영상을 지워 주세요.")


def select(candidates, limit):
    from app.modules.feed.growth_runner import eligible
    selected = []
    for row in sorted(candidates, key=lambda r: (r["created_at"], r["id"])):
        if eligible(media.path(row["storage_path"])):
            selected.append(row["id"])
        if len(selected) == limit:
            break
    if len(selected) < 3:
        raise ApiError(422, "VALIDATION_FAILED", problem="지금 볼 수 있는 아이 사진이 3장 이상 필요해요.")
    return selected


def clean_temp():
    """점검·시작 정리에서 죽은 작업의 임시 그림만 치워요."""
    import shutil
    import time
    cutoff = time.time() - 3600
    for folder in media.path("tmp").glob("growth-frames-*"):
        try:
            if folder.is_dir() and folder.stat().st_mtime < cutoff:
                shutil.rmtree(folder)
        except OSError:
            logging.getLogger(__name__).warning("growth_video_temp_cleanup_failed")


def remove(name):
    if name:
        try:
            media.remove(name)
        except OSError:
            logging.getLogger(__name__).warning("growth_video_delete_failed")
