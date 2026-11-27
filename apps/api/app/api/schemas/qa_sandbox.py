"""72~74번 API의 공개 필드만 정의해요."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class SandboxResetOut(BaseModel):
    org_name: str
    deleted: dict[str, int]
    seeded: dict[str, int]


class TraceEvent(BaseModel):
    created_at: datetime
    action: str
    actor_type: str
    agent_name: str | None
    request_id: UUID | None
    card_id: UUID | None
    daily_note_id: UUID | None
    detail: dict


class TraceError(BaseModel):
    at: datetime
    method: str
    path: str
    status: int
    error_type: str
    where: str


class TraceOut(BaseModel):
    trace_id: str
    events: list[TraceEvent]
    errors: list[TraceError]


class QAOrg(BaseModel):
    tag: str
    name: str
    login_prefix: str


class Switches(BaseModel):
    daily_note_writer: str
    answer_writer: str
    request_agent: str
    embedding: bool
    llm_models: dict[str, str]


class QAClassroom(BaseModel):
    id: UUID
    name: str


class QAMe(BaseModel):
    role: str
    org_name: str | None
    classrooms: list[QAClassroom]


class QAInfo(BaseModel):
    commit: str | None
    deployed_at: str | None
    migration: str | None
    data_backend: str
    switches: Switches
    qa_orgs: list[QAOrg]
    me: QAMe | None = None
