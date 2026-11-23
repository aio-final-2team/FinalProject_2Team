"""녹화한 응답(fixtures/)으로만 시험한다. 실제 호출은 python -m tools.public_apis.check."""

import json
import urllib.error
from datetime import date, datetime
from pathlib import Path

import pytest

from tools.public_apis.common import KST, PublicApiError
from tools.public_apis.law import LawClient, article_code, get_law_article
from tools.public_apis.weather import WeatherClient, base_time_for

FIXTURES = Path(__file__).parent / "fixtures"
AFTERNOON = datetime(2026, 11, 20, 16, 40, tzinfo=KST)


def body(name):
    return (FIXTURES / name).read_bytes()


class FakeOpener:
    """주소 조각 → 응답. 부른 주소·시간 제한을 남겨 둔다."""

    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def __call__(self, url, timeout):
        self.calls.append((url, timeout))
        for part, answer in self.routes.items():
            if part in url:
                if isinstance(answer, Exception):
                    raise answer
                return answer
        raise AssertionError(f"예상 못 한 주소: {url}")


def law(article_file="law_article_33.json", search_file="law_search.json"):
    return FakeOpener({"lawSearch.do": (200, body(search_file)), "lawService.do": (200, body(article_file))})


def test_article_code_reads_korean_article_numbers():
    assert article_code("제33조") == ("003300", "제33조")
    assert article_code("33") == ("003300", "제33조")
    assert article_code("제31조의2") == ("003102", "제31조의2")
    with pytest.raises(PublicApiError) as error:
        article_code("급식 조항")
    assert error.value.code == "NOT_FOUND"


def test_get_law_article_matches_tool_contract():
    opener = law()
    result = get_law_article("영유아보육법", "제33조", client=LawClient("TESTKEY", opener), trace_id="t-1")
    assert result["ok"] is True and result["trace_id"] == "t-1"
    assert set(result["data"]) == {"text", "source_url", "fetched_at"}
    assert result["data"]["text"].startswith("제33조(급식 관리) 어린이집의 원장은")
    assert result["data"]["source_url"].startswith("https://www.law.go.kr/")
    assert "TESTKEY" not in result["data"]["source_url"]
    assert "MST=286057" in opener.calls[1][0] and "JO=003300" in opener.calls[1][0]  # 시행령이 아닌 법률
    assert all(timeout == 10 for _, timeout in opener.calls)


def test_article_text_joins_paragraphs():
    data = LawClient("K", law("law_article_3.json")).get_article("영유아보육법", "3")
    lines = data["text"].split("\n")
    assert lines[0] == "제3조(보육 이념)" and lines[1].startswith("① ") and len(lines) == 4


def test_unknown_law_and_missing_article_are_not_found():
    no_law = get_law_article("없는법령", "제1조", client=LawClient("K", law(search_file="law_search_empty.json")))
    no_article = get_law_article("영유아보육법", "제999조", client=LawClient("K", law("law_article_missing.json")))
    for result in (no_law, no_article):
        assert result["ok"] is False
        assert result["error"]["code"] == "NOT_FOUND" and result["error"]["retryable"] is False


@pytest.mark.parametrize("failure, retryable", [
    (TimeoutError("timed out"), True),
    (urllib.error.HTTPError("u", 503, "down", None, None), True),
    (urllib.error.HTTPError("u", 429, "slow", None, None), True),
    (urllib.error.HTTPError("u", 401, "key", None, None), False),
    (urllib.error.URLError("dns"), True),
])
def test_upstream_failures_become_upstream_unavailable(failure, retryable):
    result = get_law_article("영유아보육법", "제33조",
                             client=LawClient("K", FakeOpener({"lawSearch.do": failure})))
    assert result["error"]["code"] == "UPSTREAM_UNAVAILABLE"
    assert result["error"]["retryable"] is retryable


def test_missing_key_fails_without_calling():
    opener = FakeOpener({})
    result = get_law_article("영유아보육법", "제33조", client=LawClient("", opener))
    assert result["error"]["code"] == "UPSTREAM_UNAVAILABLE" and opener.calls == []
    with pytest.raises(PublicApiError):
        WeatherClient("", opener).get_daily_forecast(now=AFTERNOON)


def test_daily_forecast_summarizes_today():
    opener = FakeOpener({"getVilageFcst": (200, body("weather_forecast.json"))})
    data = WeatherClient("TESTKEY", opener).get_daily_forecast(60, 127, now=AFTERNOON)
    assert data["date"] == "2026-11-20" and data["base"] == "20261120 0500"
    assert (data["temp_min"], data["temp_max"], data["pop_max"]) == (-3.0, 3.0, 0)
    assert data["precipitation"] == []
    assert "TESTKEY" not in data["source_url"] and "serviceKey" not in data["source_url"]
    assert opener.calls[0][1] == 10


def test_daily_forecast_lists_rain_times():
    raw = json.loads(body("weather_forecast.json"))
    for item in raw["response"]["body"]["items"]["item"]:
        if item["category"] == "PTY" and item["fcstTime"] == "1500":
            item["fcstValue"] = "1"
    opener = FakeOpener({"getVilageFcst": (200, json.dumps(raw).encode())})
    data = WeatherClient("K", opener).get_daily_forecast(now=AFTERNOON)
    assert data["precipitation"] == [{"time": "1500", "type": "비"}]


def test_weather_key_error_is_not_retryable():
    error = urllib.error.HTTPError("u", 403, "forbidden", None, None)
    with pytest.raises(PublicApiError) as raised:
        WeatherClient("BAD", FakeOpener({"getVilageFcst": error})).get_daily_forecast(now=AFTERNOON)
    assert raised.value.code == "UPSTREAM_UNAVAILABLE" and raised.value.retryable is False  # 실제 응답: 403 SERVICE_KEY_IS_NOT_REGISTERED_ERROR


def test_base_time_uses_latest_release():
    assert base_time_for(date(2026, 11, 20), AFTERNOON) == ("20261120", "0500")
    assert base_time_for(date(2026, 11, 21), AFTERNOON) == ("20261120", "1400")
    night = datetime(2026, 11, 21, 1, 0, tzinfo=KST)
    assert base_time_for(date(2026, 11, 21), night) == ("20261120", "2300")
