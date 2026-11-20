"""학부모 요청(API 설계 문서 3.1·3.2·3.7)."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.api.schemas.common import Period

RequestType = Literal["inquiry", "consultation", "complaint"]
# 알림장 연결용 귀가 시드는 읽기만 해요. 등록·인계 확인은 T46에서 열어요.
RequestReadType = Literal[RequestType, "pickup"]
RequestStatus = Literal["received", "classified", "needs_info", "assigned", "awaiting_review", "approved",
                        "sent_or_booked", "completed", "on_hold", "escalated", "rejected"]


class RequestCreateIn(BaseModel):
    client_request_id: str = Field(min_length=8, max_length=64, description="같은 제출을 두 번 받지 않기 위한 키")
    type: RequestType = Field(description="medication·pickup은 T46에서 연다")
    body: str = Field(min_length=1, max_length=2000)
    child_id: UUID
    previous_request_id: UUID | None = Field(default=None, description="끝난 요청을 다시 열 때(T04 2.1)")


class RequestAccepted(BaseModel):
    id: UUID
    status: RequestStatus
    stream_url: str


class RequestAcceptedOut(BaseModel):
    request: RequestAccepted


class RequestView(BaseModel):
    id: UUID
    type: RequestReadType
    title: str | None
    status: RequestStatus
    status_label: str
    missing_fields: list[str]
    hold_until: date | None = None
    parent_confirmed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class MessageOut(BaseModel):
    id: int
    sender_type: Literal["user", "agent", "system"]
    body: str
    created_at: datetime


class TimelineItem(BaseModel):
    label: str
    at: datetime


class SlotOut(BaseModel):
    id: int
    period: Period
    room: str
    status: Literal["proposed", "chosen_by_parent", "confirmed", "discarded"]


class BookingOut(BaseModel):
    id: UUID
    room: str
    period: Period


class ConsultationOut(BaseModel):
    slots: list[SlotOut]
    booking: BookingOut | None = None


class RejectionOut(BaseModel):
    reason_code: str
    reason_text: str | None = None


class SourceOut(BaseModel):
    document_title: str
    location: str | None = None
    effective_from: date | None = None


class RequestDetailOut(BaseModel):
    """학부모용. 위험 등급·보류 이유·도구 호출·처리한 교직원은 넣지 않는다(계약표 2.1)."""

    request: RequestView
    messages: list[MessageOut]
    timeline: list[TimelineItem]
    consultation: ConsultationOut | None = None
    rejection: RejectionOut | None = None
    sources: list[SourceOut] = Field(default_factory=list)
