"""T52: 행사·날씨 문의 날짜 찾기와 법령 주제표를 확인한다."""

from datetime import date

import pytest

from app.modules.documents.public_sources import event_day, forecast_line, law_evidence, law_topics, prefetch_public

TODAY = date(2026, 11, 23)


@pytest.mark.parametrize("question, expected", [
    ("오늘 날씨 어때요?", date(2026, 11, 23)),
    ("내일 현장체험 때 비 오나요?", date(2026, 11, 24)),
    ("모레 소풍 우산 챙길까요?", date(2026, 11, 25)),
    ("11월 25일 행사 날씨가 궁금해요", date(2026, 11, 25)),
    ("11/25 운동회 추워요?", date(2026, 11, 25)),
    ("11월 26일 행사 날씨가 궁금해요", date(2026, 11, 26)),
    ("11월 27일 행사 날씨가 궁금해요", None),
    ("11월 22일 행사 날씨가 궁금해요", None),
    ("내일 준비물이 뭐예요?", None),
    ("내일 비용은 얼마예요?", None),
    ("내일 눈이 올까요?", date(2026, 11, 24)),
    ("12월 24일 겨울방학 행사", None),
])
def test_event_day(question, expected):
    assert event_day(question, TODAY) == expected


def test_event_day_needs_weather_word():
    assert event_day("내일 몇 시에 가나요?", TODAY) is None


def test_event_day_handles_invalid_date_and_year_end():
    assert event_day("2월 30일 행사", TODAY) is None
    assert event_day("1월 1일 행사 날씨", date(2026, 12, 30)) == date(2027, 1, 1)


def test_law_topics_only_have_two_known_topics():
    topics = law_topics()
    assert set(topics) == {"health_hygiene", "teacher"}
    assert topics["health_hygiene"]["law_name"] == "학교보건법"
    assert topics["teacher"]["article"] == "제17조"


def test_law_evidence_returns_none_for_unlisted_topic():
    assert law_evidence(None, "org", "fee") is None
    assert law_evidence(None, "org", None) is None


def test_forecast_line_reads_naturally():
    line = forecast_line(date(2026, 11, 24), {"temp_min": 3.0, "temp_max": 11.0, "pop_max": 60,
                                              "precipitation": [{"time": "1500", "type": "비"}]})
    assert line == "11월 24일 예보: 최저 3도·최고 11도, 강수확률 최대 60%, 비 15시"
    dry = forecast_line(date(2026, 11, 24), {"temp_min": 3.5, "temp_max": 11.0, "pop_max": None, "precipitation": []})
    assert dry == "11월 24일 예보: 최저 3.5도·최고 11도, 비·눈 예보 없음"


def test_prefetch_only_fetches_what_the_request_needs(monkeypatch):
    from app.modules.documents import public_sources
    calls = []
    monkeypatch.setattr(public_sources, "fetch_law", lambda topic: calls.append(("law", topic)) or {"unchecked": True})
    monkeypatch.setattr(public_sources, "fetch_forecast", lambda day: calls.append(("forecast", day)) or {"x": 1})
    assert prefetch_public("complaint", "민원", "fee", TODAY) == {}
    assert prefetch_public("complaint", "민원", "health_hygiene", TODAY) == {"law": ("health_hygiene", {"unchecked": True})}
    assert prefetch_public("inquiry", "내일 비 오나요?", "other", TODAY, with_forecast=False) == {}
    assert prefetch_public("inquiry", "내일 준비물?", "other", TODAY) == {}
    assert prefetch_public("inquiry", "내일 비 오나요?", "other", TODAY) == {"forecast": (date(2026, 11, 24), {"x": 1})}
    assert prefetch_public("consultation", "내일 비 오나요?", "other", TODAY) == {}
    assert calls == [("law", "health_hygiene"), ("forecast", date(2026, 11, 24))]


def test_prefetch_law_error_becomes_unchecked(monkeypatch):
    from app.modules.documents import public_sources

    def boom(topic):
        raise RuntimeError("법령 API 오류")
    monkeypatch.setattr(public_sources, "fetch_law", boom)
    assert prefetch_public("complaint", "민원", "teacher", TODAY) == {"law": ("teacher", {"unchecked": True})}
