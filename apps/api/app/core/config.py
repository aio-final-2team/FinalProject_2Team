"""환경 설정. 값은 .env.example의 이름을 그대로 읽는다(API 설계 문서 8장)."""

import os
import re
import json
import logging
from math import isfinite
from dataclasses import dataclass, field
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
    media_dir: str = "var/media"
    data_backend: str = "mock"
    daily_note_writer: str = "app.modules.daily_notes.stub_writer:write"
    daily_note_writer_timeout: float = 300.0
    request_agent: str = "app.modules.requests.agent_stub:run_request"
    run_in: str = "api"
    celery_broker_url: str = "redis://redis:6379/0"
    feature_video_consult: bool = False
    feature_voice_analysis: bool = False
    consult_voice_analyzer: str = "app.modules.consultations.voice_stub:analyze"
    openai_stt_model: str = "gpt-4o-mini-transcribe"
    feature_neighborhood_feed: bool = False
    feature_growth_video: bool = False
    video_ice_servers: list[dict] = field(default_factory=lambda: [{"urls": "stun:stun.l.google.com:19302"}])


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
    video_enabled = os.getenv("FEATURE_VIDEO_CONSULT", "false").lower() == "true"
    default_ice = [{"urls": "stun:stun.l.google.com:19302"}]
    try:
        ice_servers = json.loads(os.getenv("VIDEO_ICE_SERVERS") or json.dumps(default_ice))
        if not isinstance(ice_servers, list) or any(
            not isinstance(server, dict) or not server.get("urls")
            or not isinstance(server["urls"], (str, list))
            or (isinstance(server["urls"], list) and any(not isinstance(url, str) or not url for url in server["urls"]))
            for server in ice_servers
        ):
            raise ValueError("VIDEO_ICE_SERVERS: urls가 있는 JSON 배열 필요")
    except ValueError:
        if video_enabled:
            raise
        logging.getLogger(__name__).warning("VIDEO_ICE_SERVERS: 기능이 꺼져 기본 STUN을 사용해요")
        ice_servers = default_ice
    return Settings(
        jwt_secret=jwt_secret,
        jwt_access_ttl_hours=int(os.getenv("JWT_ACCESS_TTL_HOURS", "12")),
        cors_origins=tuple(o.strip() for o in origins.split(",") if o.strip()),
        holidays=tuple(date.fromisoformat(d.strip()) for d in os.getenv("HOLIDAYS", "").split(",") if d.strip()),
        mock_stream_delay_ms=max(0, int(os.getenv("MOCK_STREAM_DELAY_MS", "300"))),
        work_hours=work_hours, immediate_risk_categories=categories,
        media_dir=os.getenv("MEDIA_DIR", "var/media"),
        data_backend=backend,
        daily_note_writer=os.getenv("DAILY_NOTE_WRITER", "app.modules.daily_notes.stub_writer:write"),
        daily_note_writer_timeout=writer_timeout,
        request_agent=os.getenv("REQUEST_AGENT", "app.modules.requests.agent_stub:run_request"),
        run_in=run_in,
        celery_broker_url=os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0"),
        feature_video_consult=video_enabled,
        feature_voice_analysis=os.getenv("FEATURE_VOICE_ANALYSIS", "false").lower() == "true",
        consult_voice_analyzer=os.getenv("CONSULT_VOICE_ANALYZER", "app.modules.consultations.voice_stub:analyze"),
        openai_stt_model=os.getenv("OPENAI_STT_MODEL", "gpt-4o-mini-transcribe"),
        feature_neighborhood_feed=os.getenv("FEATURE_NEIGHBORHOOD_FEED", "false").lower() == "true",
        feature_growth_video=os.getenv("FEATURE_GROWTH_VIDEO", "false").lower() == "true",
        video_ice_servers=ice_servers,
    )


settings = load_settings()
