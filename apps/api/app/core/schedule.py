"""주말·공휴일을 제외한 기한과 근무 시간 밖 알림(API 설계 6.5·6.6)."""

from datetime import datetime, time, timedelta, timezone

from app.core.config import settings
from app.core.request_rules import RISK_TYPES

KST = timezone(timedelta(hours=9))


def working_day(day):
    return day.weekday() < 5 and day not in settings.holidays


def due_at(start: datetime, request_type=None, risk_level=None, kind=None):
    start = start.astimezone(KST)
    if kind in ("needs_info", "rule_proposal"):
        return None
    if kind == "daily_note":
        return datetime.combine(start.date(), time(17), KST)
    if request_type in RISK_TYPES and risk_level in ("urgent", "uncertain"):
        return start + timedelta(hours=2)
    remaining = timedelta(hours=4 if request_type == "inquiry" else 24)
    while remaining:
        midnight = datetime.combine(start.date() + timedelta(days=1), time(), KST)
        if not working_day(start.date()):
            start = midnight
            continue
        available = midnight - start
        if remaining <= available:
            return start + remaining
        remaining -= available
        start = midnight


def deliver_after(start: datetime, role: str, risk_level=None, risk_category=None, *, request_type=None):
    start = start.astimezone(KST)
    if (request_type == "pickup" or role == "parent"
            or (risk_level == "urgent" and risk_category in settings.immediate_risk_categories)):
        return start
    opening, closing = settings.work_hours
    while not working_day(start.date()) or start.time() >= closing:
        start = datetime.combine(start.date() + timedelta(days=1), opening, KST)
    return max(start, datetime.combine(start.date(), opening, KST))
