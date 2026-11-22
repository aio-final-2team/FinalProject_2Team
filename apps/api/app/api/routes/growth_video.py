"""[제안][선택] 보호자 성장 영상. 파일은 현재 원본 권한을 검사해요."""

import os
import re
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Body, Depends, Request, Response
from starlette.responses import FileResponse
from starlette.concurrency import iterate_in_threadpool

from app import backend
from app.api.routes.feed import OpenPhotoResponse
from app.api.schemas.common import errors
from app.api.schemas.growth_video import GrowthVideo, GrowthVideoCreate, GrowthVideoList
from app.core import growth_video as rules, jobs, media
from app.core.auth import CurrentUser, current_user
from app.core.errors import ApiError, error_response

router = APIRouter(tags=["[제안][선택] 성장 영상"], dependencies=[Depends(rules.enabled)])


@router.post("/children/{child_id}/growth-videos", status_code=202, response_model=GrowthVideo,
             responses=errors(401, 403, 404, 409, 422))
def create(child_id: UUID, background_tasks: BackgroundTasks, body: GrowthVideoCreate = Body(default_factory=GrowthVideoCreate),
           user: CurrentUser = Depends(current_user)):
    row = backend.growth_videos.create(user, child_id, body.photo_limit)
    jobs.dispatch("growth_video", row["id"], background_tasks)
    return row


@router.get("/children/{child_id}/growth-videos", response_model=GrowthVideoList, responses=errors(401, 403, 404, 422))
def listing(child_id: UUID, user: CurrentUser = Depends(current_user)):
    return backend.growth_videos.listing(user, child_id)


@router.get("/growth-videos/{video_id}/file", response_class=FileResponse,
            responses={200: {"content": {"video/mp4": {}}}, 206: {"content": {"video/mp4": {}}},
                       **errors(401, 403, 404, 416, 422)})
def file(video_id: UUID, request: Request, user: CurrentUser = Depends(current_user)):
    row = backend.growth_videos.file(user, video_id)
    try:
        handle = media.path(row["storage_path"]).open("rb")
    except FileNotFoundError:
        raise ApiError(404, "NOT_FOUND") from None
    # 열린 FD를 직접 스트리밍해서 삭제 경쟁에서도 500 없이 끝내요.
    size = os.fstat(handle.fileno()).st_size
    start, end, status = 0, size - 1, 200
    value = request.headers.get("range")
    if value:
        match = re.fullmatch(r"bytes=(\d{0,20})-(\d{0,20})", value, re.IGNORECASE)
        if match and any(match.groups()):
            first, last = match.groups()
            # 못 읽는 값·역순·여러 구간은 무시하고 전체를 보내요.
            if (first and (not last or int(first) <= int(last))) or (not first and int(last) > 0):
                start, end = ((int(first), min(int(last), end) if last else end) if first
                              else (max(0, size-int(last)), end))
                if start >= size:
                    handle.close()
                    response = error_response(request, 416, "VALIDATION_FAILED", details={"size_bytes": size})
                    response.headers["Content-Range"] = f"bytes */{size}"
                    return response
                status = 206
    handle.seek(start)
    response = OpenPhotoResponse(handle, {"media_type": "video/mp4"})
    def chunks():
        remaining = end - start + 1
        while remaining > 0:
            data = handle.read(min(64 * 1024, remaining))
            if not data:
                break
            remaining -= len(data)
            yield data
    response.body_iterator = iterate_in_threadpool(chunks())
    response.status_code = status
    response.headers.update({"Accept-Ranges": "bytes", "Content-Length": str(end-start+1)})
    if status == 206:
        response.headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    return response


@router.delete("/growth-videos/{video_id}", status_code=204, responses=errors(401, 403, 404, 422))
def delete(video_id: UUID, user: CurrentUser = Depends(current_user)):
    backend.growth_videos.delete(user, video_id)
    return Response(status_code=204)
