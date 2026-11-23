"""[제안] v0.7 피드·앨범 응답."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import UploadFile
from pydantic import BaseModel, ConfigDict, Field

from app.api.schemas.common import Page
from app.core.constants import MAX_PHOTOS

PhotoScope = Literal["family", "class", "org"]


class PostUpload(BaseModel):
    body: str = Field(min_length=1, max_length=2000)
    files: list[UploadFile] = Field(default=[], max_length=MAX_PHOTOS)
    child_ids: str = "[]"


class PhotoView(BaseModel):
    id: UUID
    post_id: UUID
    media_type: Literal["image/jpeg", "image/png", "image/webp"]
    size_bytes: int
    created_at: datetime
    file_url: str


class PostView(BaseModel):
    id: UUID
    lane: Literal["class", "org"]
    classroom_id: UUID | None
    author_id: UUID
    body: str
    status: Literal["published", "hidden"]
    created_at: datetime
    photos: list[PhotoView]


class PostResponse(BaseModel):
    post: PostView


class PostList(Page):
    items: list[PostView]


class Album(Page):
    items: list[PhotoView]


class HidePost(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["hidden"]


class ScopePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    photo_scope: PhotoScope


class ScopeResponse(ScopePatch):
    child_id: UUID
