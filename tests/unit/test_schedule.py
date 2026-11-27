"""API 설계 문서 6.5 예시와 6.6 표를 그대로 고정한다."""

from datetime import datetime, date, time, timedelta
from dataclasses import replace

import pytest

from app.core import config, schedule


def at(value):
    return datetime.fromisoformat(value + "+09:00")


@pytest.mark.parametrize("start,kind,risk,expected", [
    ("2026-12-01T10:00:00", "inquiry", None, "2026-12-01T14:00:00"),
    ("2026-12-04T18:00:00", "complaint", "normal", "2026-12-07T18:00:00"),
    ("2026-12-05T10:00:00", "consultation", None, "2026-12-08T00:00:00"),
    ("2026-12-04T23:00:00", "complaint", "urgent", "2026-12-05T01:00:00"),
])
def test_documented_due_dates(start, kind, risk, expected):
    assert schedule.due_at(at(start), kind, risk) == at(expected)


@pytest.mark.parametrize("kind", ["inquiry", "consultation", "complaint"])
def test_risky_requests_share_two_hour_due_and_normal_keeps_type_due(kind):
    start = at("2026-12-01T10:00:00")
    assert schedule.due_at(start, kind, "urgent") == schedule.due_at(start, kind, "uncertain") == at("2026-12-01T12:00:00")
    assert schedule.due_at(start, kind, "normal") == schedule.due_at(start, kind, None)
    assert schedule.due_at(start, "medication", "urgent") == schedule.due_at(start, "medication")


@pytest.mark.parametrize("role,risk,category,immediate", [
    ("teacher", "urgent", "child_safety", True),
    ("director", "urgent", "staff_attack", False),
    ("teacher", "urgent", "legal_external", False),
    ("teacher", "urgent", "privacy_leak", False),
    ("teacher", "uncertain", None, False),
    ("teacher", "normal", None, False),
    ("parent", "normal", None, True),
])
def test_notification_table_inside_and_outside_hours(role, risk, category, immediate):
    inside, outside = at("2026-12-04T10:00:00"), at("2026-12-04T18:00:00")
    assert schedule.deliver_after(inside, role, risk, category) == inside
    assert schedule.deliver_after(outside, role, risk, category) == (outside if immediate else at("2026-12-07T09:00:00"))


def test_holidays_and_start_before_work(monkeypatch):
    monkeypatch.setattr(schedule, "settings", replace(config.settings, holidays=(date(2026, 12, 7),)))
    assert schedule.due_at(at("2026-12-04T18:00:00"), "complaint", "normal") == at("2026-12-08T18:00:00")
    assert schedule.deliver_after(at("2026-12-04T19:00:00"), "teacher") == at("2026-12-08T09:00:00")
    assert schedule.deliver_after(at("2026-12-08T08:59:59"), "teacher") == at("2026-12-08T09:00:00")
    assert schedule.due_at(at("2026-12-05T10:00:00"), "complaint", "uncertain") == at("2026-12-05T12:00:00")


def test_other_card_kinds_and_settings(monkeypatch):
    start = at("2026-12-01T10:00:00")
    assert schedule.due_at(start, kind="daily_note") == at("2026-12-01T17:00:00")
    assert schedule.due_at(start, kind="rule_proposal") is None
    assert schedule.due_at(start, kind="needs_info") is None
    assert schedule.due_at(start, "complaint", "normal", "director_report") == schedule.due_at(start, "complaint", "normal")
    monkeypatch.setenv("HOLIDAYS", "2026-12-25, 2027-01-01")
    monkeypatch.setenv("MOCK_STREAM_DELAY_MS", "0")
    monkeypatch.setenv("WORK_HOURS", "10:30-16:30")
    monkeypatch.setenv("IMMEDIATE_RISK_CATEGORIES", "child_safety, staff_attack")
    settings = config.load_settings()
    assert settings.holidays == (date(2026, 12, 25), date(2027, 1, 1))
    assert settings.mock_stream_delay_ms == 0
    assert settings.work_hours == (time(10, 30), time(16, 30)) and settings.immediate_risk_categories == ("child_safety", "staff_attack")
    monkeypatch.setattr(schedule, "settings", settings)
    assert schedule.deliver_after(start, "teacher") == at("2026-12-01T10:30:00")
    assert schedule.deliver_after(at("2026-12-04T16:30:00"), "teacher") == at("2026-12-07T10:30:00")
    assert schedule.deliver_after(start, "teacher", "urgent", "staff_attack") == start
    monkeypatch.setenv("HOLIDAYS", "bad-date")
    with pytest.raises(ValueError):
        config.load_settings()

@pytest.mark.parametrize("start,risk,category,delivery,due", [
    ("2026-12-18T18:30:00", "normal", None, "2026-12-21T09:00:00", "2026-12-21T18:30:00"),
    ("2026-12-24T17:30:00", "normal", None, "2026-12-24T17:30:00", "2026-12-28T17:30:00"),
    ("2026-12-24T18:30:00", "normal", None, "2026-12-28T09:00:00", "2026-12-28T18:30:00"),
    ("2026-12-18T20:00:00", "urgent", "child_safety", "2026-12-18T20:00:00", "2026-12-18T22:00:00"),
    ("2026-12-18T20:00:00", "urgent", "staff_attack", "2026-12-21T09:00:00", "2026-12-18T22:00:00"),
])
def test_documented_holiday_notification_examples(monkeypatch, start, risk, category, delivery, due):
    monkeypatch.setattr(schedule, "settings", replace(config.settings, holidays=(date(2026, 12, 25),)))
    assert schedule.deliver_after(at(start), "teacher", risk, category) == at(delivery)
    assert schedule.deliver_after(at(start), "parent", risk, category) == at(start)
    deadline = schedule.due_at(at(start), "complaint", risk)
    assert deadline == at(due) and not (deadline < at(due)) and deadline < at(due) + timedelta(microseconds=1)

@pytest.mark.parametrize("name,value", [("WORK_HOURS", v) for v in ("9:00-18:00", "24:00-25:00", "18:00-09:00", "09:00-09:00")] + [("IMMEDIATE_RISK_CATEGORIES", v) for v in ("", "typo", "child_safety,")])
def test_invalid_schedule_settings(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError):
        config.load_settings()


@pytest.mark.parametrize("preferred,expected", [
    ("[TEST] 오후 4시~5시", ["2026-12-02T16:00:00", "2026-12-01T15:30:00", "2026-12-01T09:00:00"]),
    ("[TEST] 16:00~17:00", ["2026-12-02T16:00:00", "2026-12-01T15:30:00", "2026-12-01T09:00:00"]),
    ("[TEST] 2026-12-01 오후", ["2026-12-01T15:30:00", "2026-12-01T09:00:00", "2026-12-02T16:00:00"]),
    ("[TEST] 수요일 오후", ["2026-12-02T16:00:00", "2026-12-01T15:30:00", "2026-12-01T09:00:00"]),
    ("[TEST] 내일 오전", ["2026-12-01T09:00:00", "2026-12-01T15:30:00", "2026-12-02T16:00:00"]),
    ("[TEST] 다른 시간", ["2026-12-01T09:00:00", "2026-12-01T15:30:00", "2026-12-02T16:00:00"]),
    ("[TEST] 2026-99-99 25:00", ["2026-12-01T09:00:00", "2026-12-01T15:30:00", "2026-12-02T16:00:00"]),
])
def test_model_absent_fallback_preferences_rank_overlap_then_nearest_without_changing_candidates(preferred, expected):
    """[TEST] 모델 없음 대역: 정규식이 읽은 희망 구조값으로 겹침 → 거리 → 시각 순이에요."""
    from app.modules.consultations.slots import fallback_preference, preference_key
    now = at("2026-11-30T09:00:00")
    result = sorted(slot_candidates(), key=preference_key(fallback_preference(preferred, now), now))
    assert [s["start"] for s in result] == [at(value) for value in expected]


def slot_candidates():
    return [{"start": at(value), "end": at(value)+timedelta(minutes=30)}
            for value in ("2026-12-01T09:00:00", "2026-12-01T15:30:00", "2026-12-02T16:00:00")]


def test_ai_preference_is_used_and_model_failure_falls_back(monkeypatch):
    """[TEST] 감독 모델이 켜져 있으면 AI 구조값을 쓰고, 계약 밖 값·실패는 정규식 대역으로 넘겨요."""
    from types import SimpleNamespace
    from app.modules.consultations import slots
    now, seen = at("2026-11-30T09:00:00"), []
    monkeypatch.setenv("LLM_MODEL_SUPERVISOR", "fake-model")

    def model(reply):
        return lambda role, timeout=None, retry_delays=None: SimpleNamespace(json=lambda system, user: seen.append(user) or (
            reply() if callable(reply) else reply))
    monkeypatch.setattr(slots, "OpenAIModel", model({"date_from": "2026-12-02", "date_to": "2026-12-02",
                                                      "weekdays": [], "part_of_day": None, "after": "16:00", "before": None}))
    value = slots.read_preference("[TEST] 셋째 날 느지막이 010-1234-5678", now)
    assert value == {"date_from": "2026-12-02", "date_to": "2026-12-02", "after": "16:00"}
    assert '"today": "2026-11-30 (월)"' in seen[-1] and "010-1234-5678" not in seen[-1]
    assert sorted(slot_candidates(), key=slots.preference_key(value, now))[0]["start"] == at("2026-12-02T16:00:00")
    monkeypatch.setattr(slots, "OpenAIModel", model({"weekdays": [], "after": None}))
    assert slots.read_preference("[TEST] 내일 오전", now) is None  # AI가 희망이 없다고 하면 정규식이 덮지 않아요.
    for broken in ({"after": "4pm"}, {"weekdays": [9]}, {"date_from": "2026-12-03", "date_to": "2026-12-01"}, ["x"]):
        monkeypatch.setattr(slots, "OpenAIModel", model(broken))
        assert slots.read_preference("[TEST] 내일 오전", now) == {"date_from": "2026-12-01", "date_to": "2026-12-01",
                                                                   "part_of_day": "am"}
    monkeypatch.setattr(slots, "OpenAIModel", model(lambda: (_ for _ in ()).throw(RuntimeError("[TEST] 실패"))))
    assert slots.read_preference("[TEST] 수요일 오후", now) == {"weekdays": [2], "part_of_day": "pm"}
    monkeypatch.delenv("LLM_MODEL_SUPERVISOR")
    monkeypatch.setattr(slots, "OpenAIModel", lambda *a, **k: pytest.fail("[TEST] 모델 없음인데 불렀어요"))
    assert slots.read_preference("[TEST] 16:00 이후", now) == {"after": "16:00"}


def test_rule_bounds_apply_weekdays_only_on_listed_days():
    """[TEST] 켠 규칙의 weekdays는 그 요일에만 after·before를 적용해요."""
    from app.modules.consultations.slots import rule_bounds
    rules = [{"weekdays": [1], "after": "12:00"}, {"before": "17:00"}, {"weekdays": "x", "after": "10:00"}]
    tuesday, wednesday = at("2026-12-01T00:00:00").date(), at("2026-12-02T00:00:00").date()
    assert rule_bounds(rules, tuesday, at("2026-12-01T09:00:00"), at("2026-12-01T18:00:00")) == (
        at("2026-12-01T12:00:00"), at("2026-12-01T17:00:00"))
    assert rule_bounds(rules, wednesday, at("2026-12-02T09:00:00"), at("2026-12-02T18:00:00")) == (
        at("2026-12-02T10:00:00"), at("2026-12-02T17:00:00"))
