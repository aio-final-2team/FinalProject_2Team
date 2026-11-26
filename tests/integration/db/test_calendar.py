"""[제안] 일정 조회는 모델·검색 호출 없이 저장된 날짜 사실만 읽어요."""

from datetime import date

from app.core import users
from app.mock import seed
from app.modules.documents import calendar, embedding


def test_calendar_empty_database_does_not_call_embedding(seeded_db, monkeypatch):
    def unexpected(*args, **kwargs):
        raise AssertionError("[TEST] 일정 조회에서 임베딩을 호출했어요")

    monkeypatch.setattr(embedding, "embed", unexpected)
    assert calendar.listing(users.get_user(seed.PARENT), date(2025, 1, 1), date(2025, 1, 1)) == {"items": []}
