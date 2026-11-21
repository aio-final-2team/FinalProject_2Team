"""환경 설정. 값은 .env.example의 이름을 그대로 읽는다(API 설계 문서 8장)."""

import os
import re
from math import isfinite
from dataclasses import dataclass
from datetime import date, time

_MOCK_JWT_SECRET = "local-dev-only-change-me-32-bytes-min"
_EXAMPLE_JWT_SECRET = "replace-with-a-local-random-value"


@dataclass(frozen=True)
class Settings:
    jwt_secret: str
    jwt_access_ttl_hours: int
    cors_origins: tuple[str, ...]
    holidays: tuple[date, ...] = ()
    mock_stream_delay_ms: int = 300
    work_hours: tuple[time, time] = (time(9), time(18))
    immediate_risk_categories: tuple[str, ...] = ("child_safety",)
    data_backend: str = "mock"
    daily_note_writer: str = "app.modules.daily_notes.stub_writer:write"
    daily_note_writer_timeout: float = 300.0
    request_agent: str = "app.modules.requests.agent_stub:run_request"
    run_in: str = "api"
    celery_broker_url: str = "redis://redis:6379/0"


def load_settings() -> Settings:
    backend = os.getenv("DATA_BACKEND", "mock")
    if backend not in ("mock", "db"):
        raise ValueError("DATA_BACKEND: mock 또는 db 필요")
    run_in = os.getenv("RUN_IN", "api")
    if run_in not in ("api", "worker"):
        raise ValueError("RUN_IN: api 또는 worker 필요")
    jwt_secret = os.getenv("JWT_SECRET", _MOCK_JWT_SECRET)
    if backend == "db" and (jwt_secret in (_MOCK_JWT_SECRET, _EXAMPLE_JWT_SECRET)
                            or len(jwt_secret.encode("utf-8")) < 32):
        raise ValueError("JWT_SECRET: DB 모드에서는 예시·기본값이 아닌 32바이트 이상 키 필요")
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
    writer_timeout = float(os.getenv("DAILY_NOTE_WRITER_TIMEOUT", "300"))
    if not isfinite(writer_timeout) or writer_timeout <= 0:
        raise ValueError("DAILY_NOTE_WRITER_TIMEOUT: 0보다 큰 초 필요")
    return Settings(
        jwt_secret=jwt_secret,
        jwt_access_ttl_hours=int(os.getenv("JWT_ACCESS_TTL_HOURS", "12")),
        cors_origins=tuple(o.strip() for o in origins.split(",") if o.strip()),
        holidays=tuple(date.fromisoformat(d.strip()) for d in os.getenv("HOLIDAYS", "").split(",") if d.strip()),
        mock_stream_delay_ms=max(0, int(os.getenv("MOCK_STREAM_DELAY_MS", "300"))),
        work_hours=work_hours, immediate_risk_categories=categories,
        data_backend=backend,
        daily_note_writer=os.getenv("DAILY_NOTE_WRITER", "app.modules.daily_notes.stub_writer:write"),
        daily_note_writer_timeout=writer_timeout,
        request_agent=os.getenv("REQUEST_AGENT", "app.modules.requests.agent_stub:run_request"),
        run_in=run_in,
        celery_broker_url=os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0"),
    )


settings = load_settings()
