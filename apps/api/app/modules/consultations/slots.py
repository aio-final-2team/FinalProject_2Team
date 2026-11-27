"""상담 후보는 30분씩 계산해요. 후보·학부모 체크는 확정 예약이 아니에요."""

from datetime import date, datetime, time, timedelta
from math import ceil
import re

from sqlalchemy import text

from app.core.config import settings
from app.core.schedule import KST, working_day


def preference_key(preferred_times, now):
    """명시한 날짜·요일·시각/오전·오후를 겹침 → 거리 → 시각 순으로 비교해요.

    해석하지 못한 자유 문장은 이력에 보존하고 기존의 빠른 시간 순서를 써요.
    """
    value = preferred_times or ""
    days = None
    explicit = re.search(r"(\d{4})-(\d{2})-(\d{2})", value)
    if explicit:
        try:
            days = [date(*map(int, explicit.groups()))]
        except ValueError:
            pass
    elif "다음 주" in value or "다음주" in value:
        first = now.date() + timedelta(days=7-now.weekday())
        days = [first + timedelta(days=n) for n in range(7)]
    else:
        for word, offset in (("모레", 2), ("내일", 1), ("오늘", 0)):
            if word in value:
                days = [now.date() + timedelta(days=offset)]
                break
    weekdays = [n for n, word in enumerate("월화수목금토일") if word+"요일" in value]
    if weekdays:
        days = ([day for day in days if day.weekday() in weekdays] if days else
                [now.date()+timedelta(days=(n-now.weekday()) % 7 or 7) for n in weekdays])
    matches = list(re.finditer(r"(?:(오전|오후)\s*)?(\d{1,2})(?::([0-5]\d)|시(?:\s*([0-5]?\d)분)?)", value))
    minutes = []
    meridiem = None
    for match in matches:
        meridiem = match[1] or meridiem
        hour, minute = int(match[2]), int(match[3] or match[4] or 0)
        if meridiem and 1 <= hour <= 12:
            hour = hour % 12 + (12 if meridiem == "오후" else 0)
        if hour < 24:
            minutes.append(hour*60+minute)
    if len(minutes) >= 2 and re.search(r"[~∼–-]|부터", value[matches[0].end():matches[1].start()]):
        spans = [(minutes[0], minutes[1])] if minutes[0] < minutes[1] else []
    elif len(minutes) == 1 and ("이후" in value or "부터" in value):
        spans = [(minutes[0], 24*60)]
    elif len(minutes) == 1 and ("이전" in value or "까지" in value):
        spans = [(0, minutes[0])]
    elif minutes:
        spans = [(minute, minute+30) for minute in minutes]
    elif "오후" in value:
        spans = [(12*60, 24*60)]
    elif "오전" in value:
        spans = [(0, 12*60)]
    else:
        spans = [(0, 24*60)]

    def key(candidate):
        start, end = candidate["start"].astimezone(KST), candidate["end"].astimezone(KST)
        distances = []
        for day in days or [start.date()]:
            for lower, upper in spans:
                midnight = datetime.combine(day, time(), KST)
                lo, hi = midnight+timedelta(minutes=lower), midnight+timedelta(minutes=upper)
                overlaps = start < hi and lo < end
                distances.append((not overlaps, max(lo-end, start-hi, timedelta(0)), start))
        return min(distances) if distances else (False, timedelta(0), start)

    return key


def preferred_or_memory(preferred_times, memories):
    # 요청 글·재선택에 시간 표현이 있을 때는 그 뜻이 우선이에요.
    if not re.search(r"요일|오전|오후|\d{1,2}(?::[0-5]\d|시)|오늘|내일|다음\s*주|\d{4}-\d{2}-\d{2}", preferred_times or ""):
        for memory in memories:
            data = memory["structured"]
            if any(key in data for key in ("after", "before", "weekday")):
                preferred_times = " ".join(["월화수목금토일"[data["weekday"]]+"요일" if type(data.get("weekday")) is int and 0 <= data["weekday"] <= 6 else "",
                                           data.get("after", "")+" 이후" if data.get("after") else "",
                                           data.get("before", "")+" 이전" if data.get("before") else ""])
                if data.get("after") and data.get("before"):
                    preferred_times = preferred_times.split("요일")[0]+"요일 " if "요일" in preferred_times else ""
                    preferred_times += data["after"]+"~"+data["before"]
                break
    return preferred_times


def find_consult_slots(connection, teacher_id, date, *, org_id, request_id=None, rules=(), now=None, not_before=None,
                       preferred_times=None):
    """그날의 빈 시간 최대 세 개. 같은 시작 시각에는 상담실 하나만 골라요."""
    now = now or datetime.now(KST)
    if not working_day(date):
        return []
    opening, closing = settings.work_hours
    start, end = (datetime.combine(date, value, KST) for value in (opening, closing))
    # 기억 규칙은 백엔드가 승인된 것만 넘겨요. 제안 상태는 적용하지 않아요.
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        for key in ("after", "before"):
            value = rule.get(key)
            if not isinstance(value, str) or not re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", value):
                continue
            bound = datetime.fromisoformat(f"{date}T{value}").replace(tzinfo=KST)
            if key == "after":
                start = max(start, bound)
            else:
                end = min(end, bound)
    opening_at = datetime.combine(date, opening, KST)
    start = opening_at + ceil((start-opening_at)/timedelta(minutes=30))*timedelta(minutes=30)
    candidates = [dict(row) for row in connection.execute(text("""
        SELECT DISTINCT ON (t.start) t.start, t.start + interval '30 minutes' AS end,
               r.id AS room_id, r.name AS room
        FROM generate_series(CAST(:start AS timestamptz), CAST(:end AS timestamptz)-interval '30 minutes',
                             interval '30 minutes') AS t(start)
        CROSS JOIN rooms r
        WHERE r.org_id=:org AND r.is_active AND t.start>:now
          AND t.start>=coalesce(CAST(:not_before AS timestamptz),:now)
          AND EXISTS (SELECT 1 FROM users u WHERE u.id=:teacher AND u.org_id=:org
                      AND u.role='teacher' AND u.is_active)
          AND NOT EXISTS (
            SELECT 1 FROM staff_busy_blocks b WHERE b.org_id=:org AND b.user_id=:teacher
              AND b.period && tstzrange(t.start,t.start+interval '30 minutes','[)'))
          AND NOT EXISTS (
            SELECT 1 FROM consultation_bookings b WHERE b.org_id=:org AND b.status='confirmed'
              AND (b.teacher_id=:teacher OR b.room_id=r.id)
              AND tstzrange(lower(b.period),coalesce(b.expected_end_at,upper(b.period)),'[)')
                  && tstzrange(t.start,t.start+interval '30 minutes','[)'))
          AND NOT EXISTS (
            SELECT 1 FROM consultation_slots s WHERE s.org_id=:org AND s.status='chosen_by_parent'
              AND s.chosen_at>:now-interval '24 hours'
              AND (s.teacher_id=:teacher OR s.room_id=r.id)
              AND s.period && tstzrange(t.start,t.start+interval '30 minutes','[)')
              AND NOT EXISTS (SELECT 1 FROM cards c WHERE c.id=s.card_id AND c.request_id=:request))
          AND NOT EXISTS (
            SELECT 1 FROM consultation_slots s JOIN cards c ON c.id=s.card_id AND c.org_id=s.org_id
            WHERE c.request_id=:request AND s.period && tstzrange(t.start,t.start+interval '30 minutes','[)'))
        ORDER BY t.start,r.id LIMIT :limit
    """), {"start": start, "end": end, "org": org_id, "teacher": teacher_id,
           "request": request_id, "now": now, "not_before": not_before,
           "limit": None if preferred_times else 3}).mappings()]
    return sorted(candidates, key=preference_key(preferred_times, now))[:3]


def propose_slots(connection, req, card, teacher, round_no=None, *, preferred_times=None, count=3):
    """날짜 칸이 없는 HTTP 대역은 내일부터 14일 안에서 빠른 후보 세 개를 모아요."""
    if teacher is None:
        return []
    if round_no is None:
        round_no = connection.scalar(text("SELECT coalesce(max(round),0)+1 FROM consultation_slots WHERE card_id=:id"),
                                     {"id": card["id"]})
    rules = connection.scalars(text("""
        SELECT rule_json FROM memory_rules WHERE org_id=:org AND owner_id=:teacher AND status='active'
          AND reason_code='slot_unavailable'
        ORDER BY created_at,id
    """), {"org": req["org_id"], "teacher": teacher}).all()
    if preferred_times is None:
        preferred_times = connection.scalar(text("""
            SELECT detail->>'preferred_times' FROM events WHERE request_id=:id AND detail ? 'preferred_times'
            ORDER BY id DESC LIMIT 1
        """), {"id": req["id"]})
    if preferred_times is None:
        # 첫 후보는 상담 요청 글의 희망(예: '다음 주 오후 4시 이후')을 읽어요(T04 4.1 주제·방식·선호 시간).
        # 해석하지 못한 글이면 preference_key가 빠른 순서를 써요.
        preferred_times = req.get("body")
    from app.modules.memories.memories import load_preferences
    preferred_times = preferred_or_memory(preferred_times, load_preferences(connection, req["org_id"], req["requester_id"]))
    now = datetime.now(KST)
    candidates = []
    for offset in range(1, 15):
        day = now.date() + timedelta(days=offset)
        candidates.extend(find_consult_slots(connection, teacher, day, org_id=req["org_id"],
                                             request_id=req["id"], rules=rules, now=now,
                                             preferred_times=preferred_times))
        if len(candidates) >= count and not preferred_times:
            break
    saved = []
    for rank, candidate in enumerate(sorted(candidates, key=preference_key(preferred_times, now))[:count], 1):
        saved.append(dict(connection.execute(text("""
            INSERT INTO consultation_slots (card_id,org_id,teacher_id,room_id,period,round,rank)
            VALUES (:card,:org,:teacher,:room,tstzrange(:start,:end,'[)'),:round,:rank)
            RETURNING id,status
        """), {"card": card["id"], "org": req["org_id"], "teacher": teacher,
               "room": candidate["room_id"], "start": candidate["start"], "end": candidate["end"],
               "round": round_no, "rank": rank}).mappings().one()))
    return saved
