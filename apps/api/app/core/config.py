"""환경 설정. 값은 .env.example의 이름을 그대로 읽는다(API 설계 문서 8장)."""

import os
import re
from dataclasses import dataclass
from datetime import date, time


@dataclass(frozen=True)
class Settings:
    jwt_secret: str
    jwt_access_ttl_hours: int
    cors_origins: tuple[str, ...]
    holidays: tuple[date, ...] = ()
    mock_stream_delay_ms: int = 300
    work_hours: tuple[time, time] = (time(9), time(18))
    immediate_risk_categories: tuple[str, ...] = ("child_safety",)


def load_settings() -> Settings:
    origins = os.getenv("CORS_ORIGINS", "http://localhost:5173")
    hours = os.getenv("WORK_HOURS", "09:00-18:00").strip()
    if not re.fullmatch(r"\d{2}:\d{2}-\d{2}:\d{2}", hours):
        raise ValueError("WORK_HOURS: HH:MM-HH:MM 필요")
    work_hours = tuple(time.fromisoformat(t) for t in hours.split("-"))
    if work_hours[0] >= work_hours[1]:
        raise ValueError("WORK_HOURS: 시작 < 끝 필요")
    categories = tuple(c.strip() for c in os.getenv("IMMEDIATE_RISK_CATEGORIES", "child_safety").split(","))
    if any(c not in ("child_safety", "staff_attack", "legal_external", "privacy_leak") for c in categories):
        raise ValueError("IMMEDIATE_RISK_CATEGORIES: 긴급 위험 종류 필요")
    return Settings(
        jwt_secret=os.getenv("JWT_SECRET", "local-dev-only-change-me-32-bytes-min"),
        jwt_access_ttl_hours=int(os.getenv("JWT_ACCESS_TTL_HOURS", "12")),
        cors_origins=tuple(o.strip() for o in origins.split(",") if o.strip()),
        holidays=tuple(date.fromisoformat(d.strip()) for d in os.getenv("HOLIDAYS", "").split(",") if d.strip()),
        mock_stream_delay_ms=max(0, int(os.getenv("MOCK_STREAM_DELAY_MS", "300"))),
        work_hours=work_hours, immediate_risk_categories=categories,
    )


settings = load_settings()
