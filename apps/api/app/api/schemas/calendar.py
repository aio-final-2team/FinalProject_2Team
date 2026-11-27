"""[제안] 원 일정 조회 응답이에요."""

from datetime import date as Date
from uuid import UUID

from pydantic import BaseModel


class CalendarSource(BaseModel):
    document_id: UUID
    document_title: str
    location: str


class CalendarItem(BaseModel):
    date: Date
    end_date: Date | None
    title: str
    document_id: UUID  # 아래 세 칸은 sources의 첫 자료와 같아요
    document_title: str
    location: str
    sources: list[CalendarSource]  # 같은 일정을 적은 자료 전부예요
    conflict: bool  # 다른 자료가 같은 일정을 2주 안의 다른 날로 적었으면 true예요(반복 행사는 아니에요)
    conflict_dates: list[Date]  # 그 시작일들이에요. 충돌이 없으면 빈 목록이에요


class CalendarOut(BaseModel):
    items: list[CalendarItem]
