"""[제안] 원 일정 조회 응답이에요."""

from datetime import date as Date
from uuid import UUID

from pydantic import BaseModel


class CalendarItem(BaseModel):
    date: Date
    end_date: Date | None
    title: str
    document_id: UUID
    document_title: str
    location: str


class CalendarOut(BaseModel):
    items: list[CalendarItem]
