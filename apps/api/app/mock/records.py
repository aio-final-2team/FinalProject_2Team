"""확장 저장소의 행. 칸 이름은 스키마 초안과 같다."""

from dataclasses import dataclass, field
from copy import deepcopy
from datetime import date, datetime
from uuid import UUID
from app.core.schedule import KST


@dataclass
class Approval:
    id: int
    card_id: UUID
    org_id: UUID
    card_version: int
    decided_by: UUID
    decision: str
    created_at: datetime
    reason_code: str | None = None
    reason_text: str | None = None
    edited_content: dict | None = None


@dataclass
class Booking:
    id: UUID
    org_id: UUID
    request_id: UUID
    slot_id: int
    teacher_id: UUID
    room_id: UUID
    period: dict
    confirmed_by: UUID
    status: str = "confirmed"
    expected_end_at: datetime | None = None


@dataclass
class Notification:
    id: int
    org_id: UUID
    recipient_id: UUID
    kind: str
    title: str
    body: str | None
    dedupe_key: str
    deliver_after: datetime
    created_at: datetime
    request_id: UUID | None = None
    card_id: UUID | None = None
    subject_type: str | None = None
    subject_id: UUID | None = None
    status: str = "pending"
    sent_at: datetime | None = None
    read_at: datetime | None = None


@dataclass
class Document:
    id: UUID
    org_id: UUID
    title: str
    doc_type: str
    visibility: str
    content_sha256: str
    effective_from: date
    created_at: datetime
    source: str = "virtual"
    status: str = "active"
    ingest_status: str = "succeeded"
    effective_to: date | None = None
    supersedes_id: UUID | None = None
    uploaded_by: UUID | None = None


@dataclass
class Chunk:
    id: int
    org_id: UUID
    document_id: UUID
    chunk_index: int
    location: str
    content: str


@dataclass
class Evidence:
    card_id: UUID
    org_id: UUID
    chunk_id: int
    rank: int
    quote: str


@dataclass
class Rule:
    id: UUID
    org_id: UUID
    owner_id: UUID
    reason_code: str
    rule_text: str
    rule_json: dict
    status: str = "proposed"
    decided_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(KST))


@dataclass
class NoteInput:
    id: UUID
    org_id: UUID
    classroom_id: UUID
    note_date: date
    activities: str
    supplies: str
    author_id: UUID
    draft_status: str = "succeeded"
    created_at: datetime = field(default_factory=lambda: datetime.now(KST))
    child_memos: list[dict] = field(default_factory=list)


@dataclass
class Note:
    id: UUID
    org_id: UUID
    input_id: UUID
    child_id: UUID
    note_date: date
    content: dict
    status: str = "draft"
    open_checks: list[dict] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(KST))
    confirmed_by: UUID | None = None
    confirmed_at: datetime | None = None
    sent_at: datetime | None = None
    ai_original: dict = field(default_factory=dict)
    version: int = 1
    corrected_at: datetime | None = None

    def __post_init__(self):
        self.ai_original = deepcopy(self.content)


@dataclass
class Memory:
    id: int
    org_id: UUID
    owner_id: UUID
    kind: str
    content: str
    reason_code: str | None = None
    structured: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(KST))
    deleted_at: datetime | None = None
    source_card_id: UUID | None = None
    child_id: UUID | None = None
    confirm_status: str = "confirmed"
    confirmed_at: datetime | None = None
