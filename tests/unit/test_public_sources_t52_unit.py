"""T52: 행사·날씨 문의 날짜 찾기와 법령 주제표를 확인한다."""

from datetime import date

import pytest

from app.modules.documents.public_sources import event_day, forecast_line, law_evidence, law_rule_key, law_topics, prefetch_public

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


def test_law_topics_only_have_two_known_rules():
    topics = law_topics()
    assert set(topics) == {"infection", "child_safety"}
    assert (topics["infection"]["law_name"], topics["infection"]["article"]) == ("학교보건법", "제8조")
    assert (topics["child_safety"]["law_name"], topics["child_safety"]["article"]) == ("아동복지법", "제17조")


@pytest.mark.parametrize("topic, risk, body, expected", [
    ("teacher", None, "선생님 말투가 너무 차가워요", None),
    ("health_hygiene", None, "투약 실수가 있었어요", None),
    ("health_hygiene", None, "낮잠 시간에 이불이 지저분했어요", None),
    ("health_hygiene", None, "아이가 수족구에 걸렸는데 언제 가나요", "infection"),
    ("health_hygiene", None, "독감 때문에 등원 중지라고 들었어요", "infection"),
    ("health_hygiene", None, "반에 노로바이러스가 돈대요", "infection"),
    ("teacher", "child_safety", "선생님이 아이를 때렸대요", "child_safety"),
    ("other", None, "코로나 걸렸어요", None),  # 건강·위생 주제가 아니면 감염병 낱말만으로 붙이지 않는다
])
def test_law_rule_key_needs_narrow_condition(topic, risk, body, expected):
    assert law_rule_key(topic, risk, body) == expected


def test_teacher_topic_alone_never_gets_child_welfare_law():
    assert law_rule_key("teacher", "staff_attack", "선생님이 가만두지 않겠대요") is None


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
    """고정 검색 대역(ANSWER_GATHER=fixed): 예보를 질문 낱말로 미리 가져와요."""
    from app.modules.documents import public_sources
    monkeypatch.setenv("ANSWER_GATHER", "fixed")
    calls = []
    monkeypatch.setattr(public_sources, "fetch_law", lambda topic: calls.append(("law", topic)) or {"unchecked": True})
    monkeypatch.setattr(public_sources, "fetch_forecast", lambda day: calls.append(("forecast", day)) or {"x": 1})
    assert prefetch_public("complaint", "민원", "fee", TODAY) == {}
    assert prefetch_public("complaint", "수족구 걸렸어요", "health_hygiene", TODAY) == {"law": ("infection", {"unchecked": True})}
    assert prefetch_public("complaint", "투약 실수예요", "health_hygiene", TODAY) == {}
    assert prefetch_public("complaint", "아이를 때렸대요", "teacher", TODAY, risk_category="child_safety") == {
        "law": ("child_safety", {"unchecked": True})}
    assert prefetch_public("inquiry", "내일 비 오나요?", "other", TODAY, with_forecast=False) == {}
    assert prefetch_public("inquiry", "내일 준비물?", "other", TODAY) == {}
    assert prefetch_public("inquiry", "내일 비 오나요?", "other", TODAY) == {"forecast": (date(2026, 11, 24), {"x": 1})}
    assert prefetch_public("consultation", "내일 비 오나요?", "other", TODAY) == {}
    assert calls == [("law", "infection"), ("law", "child_safety"), ("forecast", date(2026, 11, 24))]
    # 자료 찾는 AI 경로에서는 예보를 낱말로 미리 가져오지 않아요(AI가 forecast 도구로 불러요).
    monkeypatch.setenv("ANSWER_GATHER", "agent")
    assert prefetch_public("inquiry", "내일 비 오나요?", "other", TODAY) == {}
    assert calls[-1] == ("forecast", date(2026, 11, 24)) and len(calls) == 3


def test_prefetch_law_error_becomes_unchecked(monkeypatch):
    from app.modules.documents import public_sources

    def boom(topic):
        raise RuntimeError("법령 API 오류")
    monkeypatch.setattr(public_sources, "fetch_law", boom)
    assert prefetch_public("complaint", "독감이에요", "health_hygiene", TODAY) == {
        "law": ("infection", {"unchecked": True})}
