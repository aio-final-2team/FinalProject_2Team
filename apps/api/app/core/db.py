"""SQLAlchemy Core 연결. DATABASE_URL만 읽고, 트랜잭션마다 연결을 빌린다."""

import os
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url


def database_url():
    value = os.getenv("DATABASE_URL")
    if not value:
        raise ValueError("DATABASE_URL이 필요해요. 앱 전용 PostgreSQL 주소를 넣어 주세요.")
    url = make_url(value)
    if url.drivername not in ("postgresql", "postgresql+psycopg"):
        raise ValueError("DATABASE_URL: PostgreSQL + psycopg 3만 써요.")
    return url.set(drivername="postgresql+psycopg")


@lru_cache(maxsize=1)
def get_engine():
    """프로세스마다 엔진 하나. mock 모드에서는 만들거나 접속하지 않는다."""
    return create_engine(database_url(), pool_pre_ping=True,
                         connect_args={"options": "-c timezone=Asia/Seoul"})


@contextmanager
def transaction():
    """요청 처리의 SQL을 한 번에 커밋하고, 예외가 나면 되돌린다."""
    with get_engine().begin() as connection:
        yield connection
