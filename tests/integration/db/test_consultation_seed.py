"""실제 데모 실행 경로와 상담 시드의 보존·충돌·지연 알림을 전용 DB에서 확인해요."""

import os
import subprocess
import sys
from datetime import datetime, time, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from app.core.schedule import KST
from app.mock import seed
from app.modules.consultations import reminders
from app.modules.notifications import delivery
from db.seeds.consultations import seed_consultations
from tests.integration.api.test_consultation_reminders import booking, user

REQUEST_IDS = [seed.demo_id(f"7b{n}") for n in (1, 2, 3)]


def snapshot(connection):
    return {table: connection.execute(text(f"SELECT * FROM {table} ORDER BY id")).mappings().all()
            for table in ("requests", "request_messages", "cards", "consultation_slots", "consultation_bookings",
                          "approvals", "events", "notifications")}


def test_demo_cli_seeds_consultations_with_linked_requests_cards_slots_and_notifications(seeded_db):
    today = datetime.now(KST).date()
    result = subprocess.run([sys.executable, "-m", "db.seeds.demo"],
                            env={**os.environ, "PYTHONPATH": "apps/api"}, capture_output=True, text=True, check=True)
    assert "가상 원 시드 완료" in result.stdout
    with seeded_db.connect() as c:
        rows = c.execute(text("""
            SELECT b.*,r.status AS request_status,r.closed_at,r.classroom_id,r.child_id,r.requester_id,r.assignee_id,
                   c.kind,c.status AS card_status,c.closed_at AS card_closed_at,c.version,
                   s.status AS slot_status,s.chosen_at,s.period AS slot_period,s.teacher_id AS slot_teacher,s.room_id AS slot_room,
                   a.decision,a.decided_by,a.card_version
            FROM consultation_bookings b JOIN requests r ON r.id=b.request_id
            JOIN cards c ON c.request_id=r.id JOIN consultation_slots s ON s.id=b.slot_id AND s.card_id=c.id
            JOIN approvals a ON a.card_id=c.id ORDER BY r.id
        """)).mappings().all()
        assert len(rows) == 3
        for row, offset, teacher, classroom, parent, child in zip(
            rows, (0, 1, -1), (seed.TEACHER, seed.TEACHER_OTHER, seed.TEACHER),
            (seed.CLASS_STAR, seed.CLASS_SUN, seed.CLASS_STAR), (seed.PARENT, seed.PARENT_OTHER, seed.PARENT_OTHER),
            (seed.CHILD, seed.CHILD_OTHER, seed.demo_id("503")), strict=True,
        ):
            start = datetime.combine(today + timedelta(days=offset), time(15), KST)
            assert row["period"].lower == start and row["period"].upper == start + timedelta(minutes=30)
            assert row["period"] == row["slot_period"] and row["slot_status"] == "confirmed" and row["chosen_at"]
            assert row["teacher_id"] == row["slot_teacher"] == row["confirmed_by"] == row["decided_by"] == teacher
            assert row["room_id"] == row["slot_room"] == seed.ROOM
            assert (row["classroom_id"], row["child_id"], row["requester_id"], row["assignee_id"]) == (
                classroom, child, parent, teacher)
            assert (row["kind"], row["card_status"], row["decision"], row["version"], row["card_version"]) == (
                "consult_slots", "done", "approve", 2, 1)
            assert row["card_closed_at"] is not None
            assert row["status"] == ("done" if offset < 0 else "confirmed")
            assert row["request_status"] == ("completed" if offset < 0 else "sent_or_booked")
            assert (row["closed_at"] is not None) == (offset < 0)
            values = {"id": row["request_id"], "parent": parent}
            assert c.scalar(text("SELECT count(*) FROM request_messages WHERE request_id=:id AND sender_id=:parent"), values) == 1
            assert c.scalars(text("SELECT action FROM events WHERE request_id=:id ORDER BY id"), values).all() == [
                "created", "classified", "info_requested", "checked", "approved", "booked",
            ] + (["completed"] if offset < 0 else [])
            notice = c.execute(text("""
                SELECT * FROM notifications WHERE request_id=:id AND kind='consultation_booked'
            """), values).mappings().one()
            assert notice["recipient_id"] == parent and notice["status"] == "sent" and notice["sent_at"]
            assert start.strftime("%Y-%m-%d") in notice["body"] and "15:00~15:30" in notice["body"]
        assert c.scalar(text("""
            SELECT count(*) FROM consultation_bookings b JOIN staff_busy_blocks s
              ON s.org_id=b.org_id AND s.user_id=b.teacher_id AND s.period && b.period
        """)) == 0


def test_consultation_seed_preserves_dates_state_and_history_on_later_rerun(seeded_db):
    on = datetime(2026, 12, 31).date()
    with seeded_db.begin() as c:
        seed_consultations(c, on=on)
        c.execute(text("UPDATE consultation_bookings SET status='cancelled' WHERE request_id=:id"), {"id": REQUEST_IDS[0]})
        c.execute(text("UPDATE notifications SET read_at=now() WHERE request_id=:id"), {"id": REQUEST_IDS[0]})
        c.execute(text("UPDATE cards SET draft='{}',version=version+1 WHERE request_id=:id"), {"id": REQUEST_IDS[0]})
        before = snapshot(c)
        seed_consultations(c, on=on + timedelta(days=7))
        assert snapshot(c) == before
        assert c.scalar(text("SELECT lower(period) FROM consultation_bookings WHERE request_id=:id"),
                        {"id": REQUEST_IDS[1]}).astimezone(KST).date().isoformat() == "2027-01-01"


@pytest.mark.parametrize("conflict", ["busy", "booking", "withdrawn"])
def test_consultation_seed_skips_conflicts_without_partial_rows(seeded_db, conflict):
    start = datetime(2026, 11, 16, 15, tzinfo=KST)
    if conflict == "booking":
        booking(SimpleNamespace(engine=seeded_db), start)
    with seeded_db.begin() as c:
        if conflict == "busy":
            c.execute(text("""
                INSERT INTO staff_busy_blocks(org_id,user_id,period,kind)
                VALUES (:org,:teacher,tstzrange(:start,:end,'[)'),'meeting')
            """), {"org": seed.ORG, "teacher": seed.TEACHER, "start": start, "end": start + timedelta(minutes=30)})
        if conflict == "withdrawn":
            c.execute(text("DELETE FROM child_guardians WHERE child_id=:child AND user_id=:parent"),
                      {"child": seed.CHILD, "parent": seed.PARENT})
        seed_consultations(c, on=start.date())
        assert not c.scalar(text("SELECT EXISTS (SELECT 1 FROM requests WHERE id=:id)"), {"id": REQUEST_IDS[0]})
        assert not c.scalar(text("SELECT EXISTS (SELECT 1 FROM cards WHERE id=:id)"), {"id": seed.demo_id("8b1")})
        assert c.scalar(text("SELECT count(*) FROM consultation_bookings WHERE request_id=ANY(:ids)"),
                        {"ids": REQUEST_IDS}) == 2


def test_consultation_seed_supports_delay_report_and_ending_ten_minutes_before_revised_end(seeded_db):
    now = datetime(2026, 11, 16, 15, 10, tzinfo=KST)
    with seeded_db.begin() as c:
        seed_consultations(c, on=now.date())
        bid = c.scalar(text("SELECT id FROM consultation_bookings WHERE request_id=:id"), {"id": REQUEST_IDS[0]})
    until = now.replace(hour=16, minute=0)
    result = reminders.report_delay(user(), bid, until, now=now)
    assert result["booking"]["expected_end_at"] == until and result["affected_bookings"] == 0
    assert reminders.sweep_consultation_notifications(now.replace(minute=20)) == 0
    tick = until - timedelta(minutes=10)
    assert reminders.sweep_consultation_notifications(tick - timedelta(microseconds=1)) == 0
    assert reminders.sweep_consultation_notifications(tick) == 1
    assert reminders.sweep_consultation_notifications(tick) == 0
    assert delivery.deliver_pending(tick) == 1
    assert delivery.deliver_pending(tick) == 0
    with seeded_db.connect() as c:
        row = c.execute(text("SELECT * FROM notifications WHERE kind='consultation_ending'")).mappings().one()
        assert row["request_id"] == REQUEST_IDS[0] and row["recipient_id"] == seed.TEACHER
        assert row["status"] == "sent" and row["sent_at"] == tick and "16:00" in row["body"]
        assert c.scalar(text("SELECT count(*) FROM events WHERE action='consultation_delay_reported'")) == 1
        assert c.scalar(text("SELECT count(*) FROM events WHERE action='consultation_reminded'")) == 1
        assert c.scalar(text("SELECT count(*) FROM notifications WHERE kind='consultation_delayed'")) == 0
