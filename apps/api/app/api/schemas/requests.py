"""학부모 요청(API 설계 문서 3.1·3.2·3.7)."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.api.schemas.common import Period

RequestType = Literal["inquiry", "consultation", "complaint", "medication", "pickup"]
RequestReadType = RequestType
RequestStatus = Literal["received", "classified", "needs_info", "assigned", "awaiting_review", "approved",
                        "sent_or_booked", "completed", "on_hold", "escalated", "rejected"]


class RequestCreateIn(BaseModel):
    client_request_id: str = Field(min_length=8, max_length=64, description="같은 제출을 두 번 받지 않기 위한 키")
    type: RequestType
    body: str = Field(min_length=1, max_length=2000)
    child_id: UUID
    previous_request_id: UUID | None = Field(default=None, description="끝난 요청을 다시 열 때(T04 2.1)")
    pickup_guardian_id: UUID | None = Field(default=None, description="귀가 요청의 등록된 인계자. 미등록이면 생략해요")
    pickup_name: str | None = Field(default=None, max_length=100)
    pickup_relation: str | None = Field(default=None, max_length=100)
    medication_name: str | None = Field(default=None, max_length=100)
    medication_dose: str | None = Field(default=None, max_length=100)
    medication_time: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def pickup_guardian(self):
        if self.type != "pickup" and any(v is not None for v in (
                self.pickup_guardian_id, self.pickup_name, self.pickup_relation)):
            raise ValueError("인계자 정보는 귀가 요청에만 보내요")
        if self.type != "medication" and any(v is not None for v in (
                self.medication_name, self.medication_dose, self.medication_time)):
            raise ValueError("투약 정보는 투약 요청에만 보내요")
        return self


class CareDecisionIn(BaseModel):
    decision: Literal["confirm", "complete"]
    version: int = Field(ge=1, description="교직원이 본 care.version. 보호자 새 글마다 증가해요")
    pickup_guardian_id: UUID | None = None


class PickupGuardian(BaseModel):
    id: UUID
    display_name: str


class PickupGuardiansOut(BaseModel):
    items: list[PickupGuardian]


class CareOut(BaseModel):
    version: int = Field(ge=1)
    pickup_guardian_id: UUID | None = None
    pickup_name: str | None = None
    pickup_relation: str | None = None
    unregistered_pickup: bool = False
    medication_name: str | None = None
    medication_dose: str | None = None
    medication_time: str | None = None
    missing_fields: list[str] = Field(default_factory=list)
    confirmed_at: datetime | None = None
    completed_at: datetime | None = None


class CareState(BaseModel):
    id: UUID
    status: RequestStatus


class CareDecisionOut(BaseModel):
    request: CareState
    care: CareOut


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
    sender_role: Literal["parent", "teacher", "director"] | None = Field(
        description="사람이 쓴 글이면 쓴 사람의 역할, AI·시스템 글이면 null. 화면은 이 값으로 말풍선을 나눠요")
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
    care: CareOut | None = None
