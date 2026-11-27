"""[제안] 교직원 자료 질문의 입력과 검증된 출처예요."""

from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints
from typing import Annotated


class StaffAskIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class StaffEvidence(BaseModel):
    document_id: UUID
    title: str
    location: str
    effective_date: date | None


class StaffAskOut(BaseModel):
    answer: str
    evidence: list[StaffEvidence]
    conflict: bool = False
