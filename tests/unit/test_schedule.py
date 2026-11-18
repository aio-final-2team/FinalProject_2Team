"""API 설계 문서 6.5 예시와 6.6 표를 그대로 고정한다."""

from datetime import datetime, date
from types import SimpleNamespace

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
    monkeypatch.setattr(schedule, "settings", SimpleNamespace(holidays=(date(2026, 12, 7),)))
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
    settings = config.load_settings()
    assert settings.holidays == (date(2026, 12, 25), date(2027, 1, 1))
    assert settings.mock_stream_delay_ms == 0
    monkeypatch.setenv("HOLIDAYS", "bad-date")
    with pytest.raises(ValueError):
        config.load_settings()
