"""하루 중 기록의 입력과 아이별 시간순 목록이에요."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.schedule import KST


class DailyRecordIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    child_id: UUID
    body: str = Field(min_length=1, max_length=500)
    note_date: date = Field(default_factory=lambda: datetime.now(KST).date())


class DailyRecordOut(DailyRecordIn):
    model_config = ConfigDict(extra="ignore")
    id: UUID
    classroom_id: UUID
    author_id: UUID
    created_at: datetime


class DailyRecordsOut(BaseModel):
    items: list[DailyRecordOut]
