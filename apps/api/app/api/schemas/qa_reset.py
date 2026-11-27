"""71번 API: QA 서버에서 한 반·날짜의 알림장을 다시 시험해요."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.schedule import KST


class NoteResetIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    classroom_id: UUID
    note_date: date = Field(default_factory=lambda: datetime.now(KST).date())


class DeletedNotes(BaseModel):
    inputs: int
    notes: int
    cards: int
    notifications: int
    events: int


class NoteResetOut(BaseModel):
    classroom_id: UUID
    note_date: date
    deleted: DeletedNotes
    unlinked_replies: int
