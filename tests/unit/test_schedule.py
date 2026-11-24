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
def test_consultation_preferences_rank_overlap_then_nearest_without_changing_candidates(preferred, expected):
    from app.modules.consultations.slots import preference_key
    candidates = [{"start": at(value), "end": at(value)+timedelta(minutes=30)}
                  for value in ("2026-12-01T09:00:00", "2026-12-01T15:30:00", "2026-12-02T16:00:00")]
    result = sorted(candidates, key=preference_key(preferred, at("2026-11-30T09:00:00")))
    assert [s["start"] for s in result] == [at(value) for value in expected]
