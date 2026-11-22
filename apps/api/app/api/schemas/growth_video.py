"""[제안][선택] 성장 영상 접수와 상태 조회예요."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class GrowthVideoCreate(BaseModel):
    photo_limit: int = Field(12, ge=3, le=20)


class GrowthVideo(BaseModel):
    id: UUID
    child_id: UUID
    status: Literal["queued", "running", "succeeded", "failed"]
    photo_count: int
    duration_seconds: float | None
    size_bytes: int | None
    sha256: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    file_url: str | None


class GrowthVideoList(BaseModel):
    items: list[GrowthVideo]
