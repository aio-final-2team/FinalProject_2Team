"""[제안] v0.7: 사진은 multipart, 파일은 매번 인증·칸·공개 범위를 검사해요."""

import json
import os
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import TypeAdapter, ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException
from starlette.formparsers import MultiPartException

from app import backend
from app.api.schemas.common import errors
from app.api.schemas.feed import Album, HidePost, PostList, PostResponse, PostUpload, ScopePatch, ScopeResponse
from app.core import media
from app.core.constants import MAX_PHOTO_BYTES, MAX_PHOTOS, MAX_POST_BYTES
from app.core.auth import CurrentUser, current_user
from app.core.errors import ApiError
from app.core.consents import require_complete

router = APIRouter(tags=["[제안] 피드·앨범"])
Sort = Literal["-created_at", "created_at"]
UPLOAD_DOC = {"requestBody": {"required": True, "content": {
    "multipart/form-data": {"schema": PostUpload.model_json_schema()}}}}


async def create_post(request, user, lane, target_id):
    # FastAPI의 자동 Form 파싱보다 앞에서 권한을 검사해야 몸통을 읽지 않아요.
    await run_in_threadpool(backend.feed.check_access, user, lane, target_id)
    await run_in_threadpool(require_complete, user)
    length = request.headers.get("content-length")
    if length is not None:
        try:
            length = int(length)
        except ValueError:
            raise ApiError(422, "VALIDATION_FAILED", field="Content-Length") from None
        if length > MAX_POST_BYTES:
            raise ApiError(413, "VALIDATION_FAILED", problem="사진 업로드 몸통은 51MiB 이하여야 해요.")
    received = 0

    async def receive():
        nonlocal received
        message = await request.receive()
        received += len(message.get("body", b""))
        if received > MAX_POST_BYTES:
            # 파서가 이미 만든 임시 파일도 닫은 뒤 공통 413으로 바꿔요.
            raise MultiPartException("Upload body too large")
        return message

    limited = Request(request.scope, receive)
    try:
        async with limited.form(max_files=MAX_PHOTOS, max_fields=2) as form:
            body = PostUpload.model_validate({"body": form.get("body"), "files": form.getlist("files"),
                                              "child_ids": form.get("child_ids", "[]")})
            if not body.body.strip():
                raise ApiError(422, "VALIDATION_FAILED", field="body")
            data = await run_in_threadpool(uploads, body.files, body.child_ids)
            return {"post": await run_in_threadpool(backend.feed.create, user, lane, target_id, body.body, data)}
    except HTTPException:
        raise ApiError(413 if received > MAX_POST_BYTES else 422, "VALIDATION_FAILED", field="files/body") from None
    except ValidationError:
        raise ApiError(422, "VALIDATION_FAILED", field="body/files/child_ids") from None


def uploads(files, child_ids):
    try:
        tags = TypeAdapter(list[list[UUID]]).validate_python(json.loads(child_ids))
    except (ValueError, ValidationError):
        raise ApiError(422, "VALIDATION_FAILED", field="child_ids") from None
    if not tags:
        tags = [[] for _ in files]
    if len(files) > MAX_PHOTOS or len(tags) != len(files) or any(len(t) != len(set(t)) for t in tags):
        raise ApiError(422, "VALIDATION_FAILED", field="files/child_ids")
    result = []
    for file, children in zip(files, tags, strict=True):
        data = file.file.read(MAX_PHOTO_BYTES + 1)
        result.append((data, media.inspect(data), children))
    return result


@router.get("/classrooms/{classroom_id}/posts", response_model=PostList, responses=errors(401, 403, 404, 422))
def class_listing(classroom_id: UUID, page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
                 sort: Sort = "-created_at", user: CurrentUser = Depends(current_user)):
    return backend.feed.listing(user, "class", classroom_id, page, size, sort)


@router.post("/classrooms/{classroom_id}/posts", status_code=201, response_model=PostResponse,
             responses=errors(401, 403, 404, 413, 422), openapi_extra=UPLOAD_DOC)
async def class_create(classroom_id: UUID, request: Request, user: CurrentUser = Depends(current_user)):
    return await create_post(request, user, "class", classroom_id)


@router.get("/classrooms/{classroom_id}/albums", response_model=Album, responses=errors(401, 403, 404, 422))
def class_album(classroom_id: UUID, child_id: UUID | None = None, page: int = Query(1, ge=1),
               size: int = Query(20, ge=1, le=100), sort: Sort = "-created_at",
               user: CurrentUser = Depends(current_user)):
    return backend.feed.album(user, "class", classroom_id, child_id, page, size, sort)


@router.get("/organizations/{org_id}/posts", response_model=PostList, responses=errors(401, 403, 404, 422))
def org_listing(org_id: UUID, page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
                 sort: Sort = "-created_at", user: CurrentUser = Depends(current_user)):
    return backend.feed.listing(user, "org", org_id, page, size, sort)


@router.post("/organizations/{org_id}/posts", status_code=201, response_model=PostResponse,
             responses=errors(401, 403, 404, 413, 422), openapi_extra=UPLOAD_DOC)
async def org_create(org_id: UUID, request: Request, user: CurrentUser = Depends(current_user)):
    return await create_post(request, user, "org", org_id)


@router.get("/organizations/{org_id}/albums", response_model=Album, responses=errors(401, 403, 404, 422))
def org_album(org_id: UUID, child_id: UUID | None = None, page: int = Query(1, ge=1),
               size: int = Query(20, ge=1, le=100), sort: Sort = "-created_at",
               user: CurrentUser = Depends(current_user)):
    return backend.feed.album(user, "org", org_id, child_id, page, size, sort)


@router.get("/posts/{post_id}", response_model=PostResponse, responses=errors(401, 403, 404, 422))
def detail(post_id: UUID, user: CurrentUser = Depends(current_user)):
    return {"post": backend.feed.detail(user, post_id)}


@router.delete("/posts/{post_id}", status_code=204, responses=errors(401, 403, 404, 422))
def delete(post_id: UUID, user: CurrentUser = Depends(current_user)):
    backend.feed.delete(user, post_id)
    return Response(status_code=204)


@router.patch("/posts/{post_id}", response_model=PostResponse, responses=errors(401, 403, 404, 422))
def hide(post_id: UUID, body: HidePost, user: CurrentUser = Depends(current_user)):
    return {"post": backend.feed.hide(user, post_id)}


class OpenPhotoResponse(StreamingResponse):
    def __init__(self, handle, photo):
        self.handle = handle
        super().__init__(iter(lambda: handle.read(64 * 1024), b""), media_type=photo["media_type"], headers={
            "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
            "Content-Disposition": "inline", "Content-Length": str(os.fstat(handle.fileno()).st_size)})

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            self.handle.close()


@router.get("/photos/{photo_id}/file", responses={200: {"content": {
    kind: {"schema": {"type": "string", "format": "binary"}} for kind in ("image/jpeg", "image/png", "image/webp")
}}, **errors(401, 403, 404, 422)}, response_class=StreamingResponse)
def photo_file(photo_id: UUID, user: CurrentUser = Depends(current_user)):
    photo = backend.feed.file(user, photo_id)
    path = media.path(photo["storage_path"])
    try:
        handle = path.open("rb")
    except FileNotFoundError:
        raise ApiError(404, "NOT_FOUND") from None
    return OpenPhotoResponse(handle, photo)


@router.get("/children/{child_id}/photo-scope", response_model=ScopeResponse, responses=errors(401, 403, 404, 422))
def get_scope(child_id: UUID, user: CurrentUser = Depends(current_user)):
    return backend.feed.photo_scope(user, child_id)


@router.patch("/children/{child_id}/photo-scope", response_model=ScopeResponse, responses=errors(401, 403, 404, 422))
def patch_scope(child_id: UUID, body: ScopePatch, user: CurrentUser = Depends(current_user)):
    return backend.feed.photo_scope(user, child_id, body.photo_scope)
