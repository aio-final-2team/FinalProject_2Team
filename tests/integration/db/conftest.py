"""TEST_DATABASE_URL을 준 전용 DB만 사용한다. up/down 시험은 스키마를 지운다."""

import os
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy.engine import make_url

from app.core import db

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="session")
def db_engine():
    value = os.getenv("TEST_DATABASE_URL")
    if not value:
        pytest.skip("TEST_DATABASE_URL이 없어 DB 시험을 건너뛰어요. tools/test_db.sh로 임시 DB를 띄워 주세요.")
    url = make_url(value)
    if url.host in ("localhost", "127.0.0.1", "::1") and (url.port or 5432) == 5432:
        pytest.fail("중앙 PG(5432)에서는 DB 시험을 실행할 수 없어요. tools/test_db.sh를 써 주세요.")
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("DATABASE_URL", value)
        db.get_engine.cache_clear()
        engine = db.get_engine()
        try:
            yield engine
        finally:
            engine.dispose()
            db.get_engine.cache_clear()


@pytest.fixture
def alembic_config(db_engine):
    return Config(str(ROOT / "apps/api/alembic.ini"))
