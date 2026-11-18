"""여러 API가 같이 쓰는 모양(API 설계 문서 1.4·1.5)."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class Period(BaseModel):
    """DB의 tstzrange를 API에서는 시작·끝으로 주고받는다."""

    start: datetime
    end: datetime


class ErrorBody(BaseModel):
    code: str = Field(examples=["CARD_VERSION_CONFLICT"])
    message: str
    trace_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorBody


def errors(*statuses: int) -> dict[int | str, dict]:
    """라우트 responses= 에 넣어 /docs에 오류 형식을 보이게 한다."""
    return {s: {"model": ErrorResponse} for s in statuses}
