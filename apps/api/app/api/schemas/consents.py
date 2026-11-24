"""[제안] 필수 동의 저장·조회와 반 현황이에요."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ConsentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[str]
    terms_version: str


class ConsentItem(BaseModel):
    item: str
    label: str
    required: Literal[True]
    agreed_at: datetime | None


class ConsentOut(BaseModel):
    terms_version: str
    complete: bool
    items: list[ConsentItem]


class ChildConsent(BaseModel):
    child_id: UUID
    display_name: str
    guardians_total: int
    guardians_complete: int
    complete: bool


class ClassroomConsents(BaseModel):
    items: list[ChildConsent]
