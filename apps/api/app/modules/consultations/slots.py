"""상담 후보는 30분씩 계산해요. 후보·학부모 체크는 확정 예약이 아니에요."""

from datetime import datetime, timedelta
from math import ceil
import re

from sqlalchemy import text

from app.core.config import settings
from app.core.schedule import KST, working_day


def find_consult_slots(connection, teacher_id, date, *, org_id, request_id=None, rules=()):
    """그날의 빈 시간 최대 세 개. 같은 시작 시각에는 상담실 하나만 골라요."""
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
    return [dict(row) for row in connection.execute(text("""
        SELECT DISTINCT ON (t.start) t.start, t.start + interval '30 minutes' AS end,
               r.id AS room_id, r.name AS room
        FROM generate_series(CAST(:start AS timestamptz), CAST(:end AS timestamptz)-interval '30 minutes',
                             interval '30 minutes') AS t(start)
        CROSS JOIN rooms r
        WHERE r.org_id=:org AND r.is_active AND t.start>now()
          AND EXISTS (SELECT 1 FROM users u WHERE u.id=:teacher AND u.org_id=:org
                      AND u.role='teacher' AND u.is_active)
          AND NOT EXISTS (
            SELECT 1 FROM staff_busy_blocks b WHERE b.org_id=:org AND b.user_id=:teacher
              AND b.period && tstzrange(t.start,t.start+interval '30 minutes','[)'))
          AND NOT EXISTS (
            SELECT 1 FROM consultation_bookings b WHERE b.org_id=:org AND b.status='confirmed'
              AND (b.teacher_id=:teacher OR b.room_id=r.id)
              AND b.period && tstzrange(t.start,t.start+interval '30 minutes','[)'))
          AND NOT EXISTS (
            SELECT 1 FROM consultation_slots s WHERE s.org_id=:org AND s.status='chosen_by_parent'
              AND s.chosen_at>now()-interval '24 hours'
              AND (s.teacher_id=:teacher OR s.room_id=r.id)
              AND s.period && tstzrange(t.start,t.start+interval '30 minutes','[)')
              AND NOT EXISTS (SELECT 1 FROM cards c WHERE c.id=s.card_id AND c.request_id=:request))
          AND NOT EXISTS (
            SELECT 1 FROM consultation_slots s JOIN cards c ON c.id=s.card_id AND c.org_id=s.org_id
            WHERE c.request_id=:request AND s.period && tstzrange(t.start,t.start+interval '30 minutes','[)'))
        ORDER BY t.start,r.id LIMIT 3
    """), {"start": start, "end": end, "org": org_id, "teacher": teacher_id,
           "request": request_id}).mappings()]


def propose_slots(connection, req, card, teacher, round_no=None):
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
    candidates = []
    for offset in range(1, 15):
        day = datetime.now(KST).date() + timedelta(days=offset)
        candidates.extend(find_consult_slots(connection, teacher, day, org_id=req["org_id"],
                                             request_id=req["id"], rules=rules))
        if len(candidates) >= 3:
            break
    saved = []
    for rank, candidate in enumerate(candidates[:3], 1):
        saved.append(dict(connection.execute(text("""
            INSERT INTO consultation_slots (card_id,org_id,teacher_id,room_id,period,round,rank)
            VALUES (:card,:org,:teacher,:room,tstzrange(:start,:end,'[)'),:round,:rank)
            RETURNING id,status
        """), {"card": card["id"], "org": req["org_id"], "teacher": teacher,
               "room": candidate["room_id"], "start": candidate["start"], "end": candidate["end"],
               "round": round_no, "rank": rank}).mappings().one()))
    return saved
