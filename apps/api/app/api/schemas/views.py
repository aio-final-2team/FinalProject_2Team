"""목록과 상세의 화면 계약."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.api.schemas.common import Page, Period
from app.api.schemas.requests import MessageOut, RequestStatus, RequestType, SourceOut, BookingOut, RequestView
from app.api.schemas.actions import CardKind, NoteLine


class RequestItem(BaseModel):
    id: UUID
    type: RequestType
    title: str | None
    status: RequestStatus
    status_label: str
    updated_at: datetime
    next_action: str | None
    hold_until: date | None = None


class RequestList(Page):
    items: list[RequestItem]


class CareRequestItem(RequestItem):
    child_id: UUID
    child_name: str
    version: int
    unregistered_pickup: bool
    missing_fields: list[str]


class CareRequestList(Page):
    items: list[CareRequestItem]


class MessageResponse(BaseModel):
    message: MessageOut


class RequestState(BaseModel):
    id: UUID
    status: RequestStatus
    parent_confirmed_at: datetime | None = None


class ConfirmResponse(BaseModel):
    request: RequestState


class SlotState(BaseModel):
    id: int
    status: str


class ChoicesResponse(ConfirmResponse):
    slots: list[SlotState]


class BookingResponse(ConfirmResponse):
    booking: BookingOut


class CardState(BaseModel):
    id: UUID
    status: str
    version: int


class DecisionResponse(BaseModel):
    card: CardState
    request: RequestState | None = None
    next_card_id: UUID | None = None


class Person(BaseModel):
    id: UUID
    display_name: str


class ClassroomView(BaseModel):
    id: UUID
    name: str


class CheckSummary(BaseModel):
    passed: bool
    issue_count: int


class CardItem(BaseModel):
    id: UUID
    kind: CardKind
    status: str
    status_label: str
    version: int
    request_id: UUID | None
    request_type: Literal["inquiry", "consultation", "complaint"] | None
    title: str
    urgency: str | None
    risk_level: str | None
    risk_category: str | None
    is_urgent: bool
    repeat_count: int | None
    check: CheckSummary | None
    parent_choice_count: int | None
    classroom: ClassroomView | None
    assignee: Person | None
    due_at: datetime | None
    is_delayed: bool
    hold_until: date | None


class CardList(Page):
    items: list[CardItem]
    counts: dict[str, int]
    type_counts: dict[str, int]


class CardView(CardState):
    kind: CardKind
    summary: str
    draft: dict
    check_result: dict | None
    check_attempts: int


class EvidenceView(SourceOut):
    quote: str
    is_current: bool


class ParentChoice(BaseModel):
    slot_id: int
    period: Period
    room: str
    chosen_at: datetime
    hold_expires_at: datetime


class RuleView(BaseModel):
    id: UUID
    reason_code: str
    rule_text: str
    status: str


class InstructionView(BaseModel):
    text: str
    by: Person
    at: datetime


class StaffRequest(RequestView):
    body: str
    risk_level: str | None
    risk_category: str | None
    repeat_count: int | None
    classroom_id: UUID


class EventView(BaseModel):
    id: int
    action: str
    request_id: UUID | None
    card_id: UUID | None
    agent_name: str | None
    actor_type: str
    actor_id: UUID | None
    from_status: str | None
    to_status: str | None
    detail: dict
    created_at: datetime


class CardDetail(BaseModel):
    card: CardView
    request: StaffRequest | None
    messages: list[MessageOut]
    evidence: list[EvidenceView]
    warnings: list[str]
    parent_choices: list[ParentChoice]
    rule: RuleView | None
    director_instruction: InstructionView | None
    timeline: list[EventView]


class ReclassifyResponse(BaseModel):
    request: StaffRequest


class AssignmentView(BaseModel):
    assignee: Person
    version: int


class ReassignResponse(BaseModel):
    card: AssignmentView


class RuleState(BaseModel):
    id: UUID
    status: str


class RuleResponse(BaseModel):
    rule: RuleState


class Reassignment(BaseModel):
    card_id: UUID
    from_: UUID | None = Field(alias="from")
    to: UUID
    reason: str
    at: datetime


class EvalView(BaseModel):
    suite: str
    requested_model: str
    returned_model: str | None
    passed: int
    total: int
    started_at: datetime


class Overview(BaseModel):
    unassigned: int
    waiting: int
    delayed: int
    done_today: int
    completed_unconfirmed: int
    reassignments: list[Reassignment]
    eval: list[EvalView]


class NotificationView(BaseModel):
    id: int
    kind: Literal["needs_info", "new_card", "urgent_complaint", "uncertain_complaint", "director_report",
                  "on_hold", "sent_or_booked", "parent_confirmed", "completed", "rejected", "note_sent",
                  "slot_hold_expired", "hold_resumed", "consultation_ending", "consultation_delayed", "care_requested", "care_confirmed",
                  "care_rejected", "cancelled"]
    title: str
    body: str | None
    request_id: UUID | None
    subject_type: str | None
    subject_id: UUID | None
    read_at: datetime | None
    deliver_after: datetime


class NotificationList(Page):
    items: list[NotificationView]


class NotificationResponse(BaseModel):
    notification: NotificationView


class JobError(BaseModel):
    code: str
    message: str


class DraftResponse(BaseModel):
    input_id: UUID
    draft_status: Literal["queued", "running", "succeeded", "failed"]
    error: JobError | None = None


class RegenerateResponse(DraftResponse):
    kept_edited: int = Field(ge=0)


class OpenCheck(BaseModel):
    id: str
    item_key: str
    kind: Literal["not_in_memo", "sensitive", "other_child", "date_check", "absent", "draft_failed", "check_failed", "request_missed"]
    problem: str
    sentence: str | None = None
    request_id: UUID | None = None


class NoteLineOut(NoteLine):
    request_status: RequestStatus | None = Field(default=None, description="투약·귀가 출처 요청의 현재 상태(읽기 전용)")


class NoteContentOut(BaseModel):
    items: list[NoteLineOut]


class NoteView(BaseModel):
    id: UUID
    child_id: UUID
    note_date: date
    status: Literal["draft", "needs_check", "ready", "sent"]
    content: NoteContentOut
    open_checks: list[OpenCheck]
    confirmed_at: datetime | None
    sent_at: datetime | None


class NoteList(Page):
    items: list[NoteView]


class NoteResponse(BaseModel):
    note: NoteView


MemoryKind = Literal["rejection_reason", "preference", "tone"]


class MemoryView(BaseModel):
    id: int
    kind: MemoryKind
    reason_code: str | None
    content: str
    structured: dict
    created_at: datetime


class MemoryList(Page):
    items: list[MemoryView]


class SendResponse(BaseModel):
    sent_count: int


class DocumentView(BaseModel):
    id: UUID
    title: str
    doc_type: str
    visibility: str
    classroom_ids: list[UUID]
    effective_from: date
    effective_to: date | None
    status: str
    ingest_status: Literal["queued", "running", "succeeded", "failed"]
    supersedes_id: UUID | None
    conflicts: list[dict]
    chunk_count: int
    error: JobError | None


class DocumentResponse(BaseModel):
    document: DocumentView


class DocumentChunk(BaseModel):
    index: int
    location: str | None
    content: str
    suspicious: bool


class DocumentDetailView(DocumentView):
    chunks: list[DocumentChunk]


class DocumentDetailResponse(BaseModel):
    document: DocumentDetailView


class DocumentList(Page):
    items: list[DocumentView]


class DelayedBooking(BaseModel):
    id: UUID
    period: Period
    status: Literal["confirmed"]
    expected_end_at: datetime


class ConsultationDelayResponse(BaseModel):
    booking: DelayedBooking
    affected_bookings: int = Field(ge=0)
