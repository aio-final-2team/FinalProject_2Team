"""환경 설정. 값은 .env.example의 이름을 그대로 읽는다(API 설계 문서 8장)."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    jwt_secret: str
    jwt_access_ttl_hours: int
    cors_origins: tuple[str, ...]


def load_settings() -> Settings:
    origins = os.getenv("CORS_ORIGINS", "http://localhost:5173")
    return Settings(
        jwt_secret=os.getenv("JWT_SECRET", "local-dev-only-change-me-32-bytes-min"),
        jwt_access_ttl_hours=int(os.getenv("JWT_ACCESS_TTL_HOURS", "12")),
        cors_origins=tuple(o.strip() for o in origins.split(",") if o.strip()),
    )


settings = load_settings()
