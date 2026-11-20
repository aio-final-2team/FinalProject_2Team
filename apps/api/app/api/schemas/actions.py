"""실행 API의 형식 검사. DB 상태는 저장소가 검사한다."""

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.schedule import KST
from datetime import datetime

Reason = Literal["wrong_fact", "tone", "missing_info", "privacy", "policy",
                 "slot_unavailable", "room_unavailable", "other"]
RiskCategory = Literal["child_safety", "staff_attack", "legal_external", "privacy_leak"]
CardKind = Literal["reply_draft", "consult_slots", "director_report", "needs_info", "daily_note", "rule_proposal"]
InboxFilter = Literal["unassigned", "needs_review", "uncertain", "on_hold", "in_progress", "done"]


class MessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


class SlotChoicesIn(BaseModel):
    slot_ids: list[int] | None = Field(default=None, min_length=1, max_length=3)
    none_fit: bool = False
    preferred_times: str | None = Field(default=None, min_length=1, max_length=200)

    @model_validator(mode="after")
    def choices(self):
        if self.none_fit:
            if self.slot_ids is not None or not self.preferred_times or not self.preferred_times.strip():
                raise ValueError("preferred_times가 필요하고 slot_ids는 함께 보낼 수 없어요")
        elif not self.slot_ids or len(set(self.slot_ids)) != len(self.slot_ids):
            raise ValueError("서로 다른 slot_ids 1~3개가 필요해요")
        return self


class VersionIn(BaseModel):
    version: int = Field(ge=1)


class DecisionIn(VersionIn):
    decision: Literal["approve", "edit_approve", "reject", "hold", "resume", "dismiss", "complete", "escalate"]
    reason_code: Reason | None = None
    reason_text: str | None = Field(default=None, min_length=1, max_length=500)
    hold_until: date | None = None
    edited_content: dict | None = None

    @field_validator("reason_text")
    @classmethod
    def meaningful_reason(cls, value):
        if value is not None and not value.strip():
            raise ValueError("이유를 적어 주세요")
        return value

    @model_validator(mode="after")
    def required_fields(self):
        if self.decision in ("reject", "dismiss") and self.reason_code is None:
            raise ValueError("reason_code가 필요해요")
        if self.reason_code == "other" and self.reason_text is None:
            raise ValueError("reason_text가 필요해요")
        if self.decision == "hold" and (self.reason_text is None or self.hold_until is None
                                       or self.hold_until <= datetime.now(KST).date()):
            raise ValueError("보류 이유와 오늘 이후의 hold_until이 필요해요")
        if self.decision == "edit_approve" and not self.edited_content:
            raise ValueError("edited_content가 필요해요")
        return self


class ReclassifyIn(VersionIn):
    risk_level: Literal["normal", "urgent"]
    risk_category: RiskCategory | None = None
    reason: str = Field(min_length=1, max_length=500, pattern=r"\S")

    @model_validator(mode="after")
    def category(self):
        if self.risk_level == "urgent" and self.risk_category is None:
            raise ValueError("긴급 사유 risk_category가 필요해요")
        return self


class BookingIn(VersionIn):
    slot_id: int = Field(ge=1)


class InstructionIn(VersionIn):
    instruction: str = Field(min_length=1, max_length=500, pattern=r"\S")


class ReassignIn(BaseModel):
    assignee_id: UUID
    reason: str = Field(min_length=1, max_length=500, pattern=r"\S")


class RuleDecisionIn(BaseModel):
    decision: Literal["activate", "decline"]


class NoteBatchIn(BaseModel):
    classroom_id: UUID
    note_date: date

    @field_validator("note_date")
    @classmethod
    def past_or_today(cls, value):
        if value > datetime.now(KST).date():
            raise ValueError("오늘 또는 지난 날짜만 쓸 수 있어요")
        return value


class ChildMemoIn(BaseModel):
    child_id: UUID
    memo: str = Field(min_length=1, max_length=500)


class NoteDraftIn(NoteBatchIn):
    activities: str = Field(min_length=1, max_length=2000)
    supplies: str = Field(max_length=2000)
    child_memos: list[ChildMemoIn] = Field(default_factory=list)

    @field_validator("child_memos")
    @classmethod
    def unique_children(cls, value):
        if len({memo.child_id for memo in value}) != len(value):
            raise ValueError("같은 아이의 메모는 한 번만 보내 주세요")
        return value


class NoteSource(BaseModel):
    type: Literal["teacher_input", "document", "request"]
    document_id: UUID | None = None
    document_title: str | None = None
    request_id: UUID | None = None

    @model_validator(mode="after")
    def source_fields(self):
        if self.type == "document" and (self.document_id is None or not self.document_title):
            raise ValueError("문서 출처가 필요해요")
        if self.type == "request" and self.request_id is None:
            raise ValueError("request_id가 필요해요")
        return self


class NoteLine(BaseModel):
    key: Literal["day", "meal", "medication", "pickup", "supplies", "child", "inquiry"]
    label: str = Field(min_length=1)
    value: str
    source: NoteSource

    @model_validator(mode="after")
    def child_source(self):
        if self.key == "child" and self.source.type != "teacher_input":
            raise ValueError("아이 메모의 출처는 teacher_input이에요")
        if self.key in ("inquiry", "medication", "pickup") and self.source.type != "request":
            raise ValueError("보호자 요청 줄의 출처는 request예요")
        return self


class NoteContent(BaseModel):
    items: list[NoteLine]


class NotePatchIn(BaseModel):
    content: NoteContent | None = None
    resolved_checks: list[str] = Field(default_factory=list)
    confirm: bool = False


class ConsultationDelayIn(BaseModel):
    expected_end_at: datetime
