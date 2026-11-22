"""[제안][선택] 가상 음성 분석 결과예요. 원본 파일 주소는 없어요."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class VoiceSummary(BaseModel):
    summary: str
    parent_requests: list[str]
    follow_ups: list[str]

    @field_validator("summary")
    @classmethod
    def three_lines(cls, value):
        if len(value.splitlines()) > 3:
            raise ValueError("요약은 3줄 이하여야 해요.")
        return value


class AnalysisResult(BaseModel):
    transcript: str
    result: VoiceSummary
    duration_seconds: float | None = Field(default=None, ge=0, allow_inf_nan=False)


class VoiceAnalysis(AnalysisResult):
    id: UUID
    booking_id: UUID
    status: Literal["queued", "running", "succeeded", "failed"]
    sha256: str
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class VoiceAnalysisList(BaseModel):
    items: list[VoiceAnalysis]
