"""[제안] v0.7: 사진은 multipart, 파일은 매번 인증·칸·공개 범위를 검사해요."""

import json
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import TypeAdapter, ValidationError

from app import backend
from app.api.schemas.common import errors
from app.api.schemas.feed import Album, HidePost, PostList, PostResponse, ScopePatch, ScopeResponse
from app.core import media
from app.core.constants import MAX_PHOTO_BYTES, MAX_PHOTOS
from app.core.auth import CurrentUser, current_user
from app.core.errors import ApiError

router = APIRouter(tags=["[제안] 피드·앨범"])
Sort = Literal["-created_at", "created_at"]


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
             responses=errors(401, 403, 404, 422))
def class_create(classroom_id: UUID, body: str = Form(..., min_length=1, max_length=2000),
                files: list[UploadFile] = File([]), child_ids: str = Form("[]"),
                user: CurrentUser = Depends(current_user)):
    if not body.strip():
        raise ApiError(422, "VALIDATION_FAILED", field="body")
    return {"post": backend.feed.create(user, "class", classroom_id, body, uploads(files, child_ids))}


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
             responses=errors(401, 403, 404, 422))
def org_create(org_id: UUID, body: str = Form(..., min_length=1, max_length=2000),
                files: list[UploadFile] = File([]), child_ids: str = Form("[]"),
                user: CurrentUser = Depends(current_user)):
    if not body.strip():
        raise ApiError(422, "VALIDATION_FAILED", field="body")
    return {"post": backend.feed.create(user, "org", org_id, body, uploads(files, child_ids))}


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


@router.get("/photos/{photo_id}/file", responses={200: {"content": {
    kind: {"schema": {"type": "string", "format": "binary"}} for kind in ("image/jpeg", "image/png", "image/webp")
}}, **errors(401, 403, 404, 422)}, response_class=FileResponse)
def photo_file(photo_id: UUID, user: CurrentUser = Depends(current_user)):
    photo = backend.feed.file(user, photo_id)
    path = media.path(photo["storage_path"])
    if not path.is_file():
        raise ApiError(404, "NOT_FOUND")
    return FileResponse(path, media_type=photo["media_type"], headers={"Cache-Control": "private, no-store"})


@router.get("/children/{child_id}/photo-scope", response_model=ScopeResponse, responses=errors(401, 403, 404, 422))
def get_scope(child_id: UUID, user: CurrentUser = Depends(current_user)):
    return backend.feed.photo_scope(user, child_id)


@router.patch("/children/{child_id}/photo-scope", response_model=ScopeResponse, responses=errors(401, 403, 404, 422))
def patch_scope(child_id: UUID, body: ScopePatch, user: CurrentUser = Depends(current_user)):
    return backend.feed.photo_scope(user, child_id, body.photo_scope)
