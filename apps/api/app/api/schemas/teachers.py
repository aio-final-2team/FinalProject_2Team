"""70번 API: 원장이 카드 담당을 바꿀 때 고를 같은 기관 선생님 목록이에요."""

from uuid import UUID

from pydantic import BaseModel


class TeacherClassroom(BaseModel):
    id: UUID
    name: str


class TeacherItem(BaseModel):
    id: UUID
    display_name: str
    classrooms: list[TeacherClassroom]


class TeachersOut(BaseModel):
    items: list[TeacherItem]
