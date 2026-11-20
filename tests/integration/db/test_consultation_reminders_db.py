"""T48의 SQL 원자성·동시 점검·대체 후보·발송 만료·마이그레이션을 확인해요."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from types import SimpleNamespace

from alembic import command
import pytest
from sqlalchemy import event, text

from app import worker
from app.mock import seed
from app.modules.consultations import reminders
from app.modules.notifications import delivery
from tests.integration.api.test_consultation_reminders import NOW, booking, user


@pytest.fixture
def ctx(seeded_db):
    return SimpleNamespace(engine=seeded_db, module=reminders)


def test_concurrent_sweeps_leave_one_notification_and_one_event(ctx):
    booking(ctx)
    entered, release = Event(), Event()
    def pause(connection, cursor, statement, parameters, context, many):
        if "INSERT INTO notifications" in statement:
            entered.set()
            assert release.wait(10)
    event.listen(ctx.engine, "before_cursor_execute", pause)
    try:
        with ThreadPoolExecutor(2) as pool:
            first = pool.submit(reminders.sweep_consultation_notifications, NOW)
            try:
                assert entered.wait(5)
                assert pool.submit(reminders.sweep_consultation_notifications, NOW).result(3) == 0
            finally:
                release.set()
            assert first.result(5) == 1
    finally:
        event.remove(ctx.engine, "before_cursor_execute", pause)
    with ctx.engine.connect() as c:
        assert c.scalar(text("SELECT count(*) FROM notifications WHERE kind='consultation_ending'")) == 1
        assert c.scalar(text("SELECT count(*) FROM events WHERE action='consultation_reminded'")) == 1


@pytest.mark.parametrize("operation", ["report", "sweep"])
def test_event_failure_rolls_back_delay_or_notifications(ctx, monkeypatch, operation):
    bid, _ = booking(ctx)
    def fail(*args, **kwargs):
        raise RuntimeError("[TEST] event storage failed")
    monkeypatch.setattr(reminders, "record", fail)
    with pytest.raises(RuntimeError, match="event storage"):
        if operation == "report":
            reminders.report_delay(user(), bid, NOW+timedelta(hours=1), now=NOW)
        else:
            reminders.sweep_consultation_notifications(NOW)
    with ctx.engine.connect() as c:
        assert c.scalar(text("SELECT count(*) FROM notifications WHERE kind LIKE 'consultation_%'")) == 0
        assert c.scalar(text("SELECT expected_end_at FROM consultation_bookings WHERE id=:id"), {"id": bid}) is None


def test_alternatives_respect_busy_bookings_live_choice_and_approved_rules(ctx):
    first, _ = booking(ctx)
    _, rid = booking(ctx, NOW+timedelta(minutes=10))
    # DB 대역의 첫 빈 칸은 10시예요. 수업·다른 교사 상담·승인 규칙·학부모 체크를 각각 빼요.
    booking(ctx, NOW.replace(hour=10, minute=30), teacher=seed.TEACHER_OTHER)
    reminders.report_delay(user(), first, NOW+timedelta(minutes=35), now=NOW)
    with ctx.engine.begin() as c:
        c.execute(text("""
            INSERT INTO staff_busy_blocks(org_id,user_id,period,kind)
            VALUES (:org,:user,tstzrange(:start,:end,'[)'),'class')
        """), {"org": seed.ORG, "user": seed.TEACHER,
               "start": NOW.replace(hour=10, minute=0), "end": NOW.replace(hour=10, minute=30)})
        c.execute(text("""
            INSERT INTO memory_rules(org_id,owner_id,reason_code,rule_text,rule_json,status)
            VALUES (:org,:user,'slot_unavailable','[TEST] 승인 시간','{"after":"11:15"}','active'),
                   (:org,:user,'slot_unavailable','[TEST] 비활성 시간','{"after":"17:00"}','off')
        """), {"org": seed.ORG, "user": seed.TEACHER})
        card = c.scalar(text("""
            INSERT INTO cards(org_id,request_id,kind,assignee_id) VALUES (:org,:req,'consult_slots',:teacher) RETURNING id
        """), {"org": seed.ORG, "req": rid, "teacher": seed.TEACHER})
        c.execute(text("""
            INSERT INTO consultation_slots(org_id,card_id,teacher_id,room_id,period,rank,status,chosen_at)
            SELECT :org,:card,:teacher,id,tstzrange(:start,:end,'[)'),1,'chosen_by_parent',:now
            FROM rooms WHERE org_id=:org LIMIT 1
        """), {"org": seed.ORG, "card": card, "teacher": seed.TEACHER, "now": NOW,
               "start": NOW.replace(hour=11, minute=30), "end": NOW.replace(hour=12, minute=0)})
    assert reminders.sweep_consultation_notifications(NOW) == 2
    with ctx.engine.connect() as c:
        bodies = c.scalars(text("SELECT body FROM notifications WHERE kind='consultation_delayed'")).all()
        assert len(bodies) == 2
        assert all("12:00~12:30" in body and "12:30~13:00" in body and "13:00~13:30" in body for body in bodies)
        assert c.scalar(text("SELECT count(*) FROM consultation_slots")) == 1
        assert c.scalar(text("SELECT count(*) FROM consultation_bookings")) == 3


@pytest.mark.parametrize("status", [None, "done", "cancelled"])
def test_late_delivery_holds_ended_or_closed_booking(ctx, status):
    bid, _ = booking(ctx)
    assert reminders.sweep_consultation_notifications(NOW) == 1
    if status:
        with ctx.engine.begin() as c:
            c.execute(text("UPDATE consultation_bookings SET status=:status WHERE id=:id"), {"id": bid, "status": status})
    assert delivery.deliver_pending(NOW+timedelta(minutes=10) if status is None else NOW) == 0
    with ctx.engine.connect() as c:
        row = c.execute(text("SELECT * FROM notifications WHERE kind='consultation_ending'")).mappings().one()
        assert row["status"] == "held" and row["last_error"] == "CONSULTATION_ENDED"
        assert row["attempts"] == 0 and row["sent_at"] is None


def test_eager_task_creates_and_delivery_sends_app_notification(ctx, monkeypatch):
    from dataclasses import replace
    from app.core import schedule
    monkeypatch.setattr(worker, "settings", replace(worker.settings, data_backend="db", run_in="worker"))
    monkeypatch.setattr(schedule, "settings", replace(schedule.settings, holidays=()))
    bid, _ = booking(ctx)
    actual_sweep = reminders.sweep_consultation_notifications
    monkeypatch.setattr(reminders, "sweep_consultation_notifications", lambda: actual_sweep(NOW))
    assert worker.consultation_reminders.apply().get(propagate=True) == 1
    assert delivery.deliver_pending(NOW) == 1
    assert worker.consultation_reminders.apply().get(propagate=True) == 0
    assert delivery.deliver_pending(NOW) == 0
    with ctx.engine.connect() as c:
        row = c.execute(text("SELECT * FROM notifications WHERE kind='consultation_ending'")).mappings().one()
        assert str(bid) in row["dedupe_key"] and row["status"] == "sent" and row["attempts"] == 1


def test_revision_round_trip_preserves_booking_old_notifications_and_old_events(ctx, alembic_config):
    bid, _ = booking(ctx)
    reminders.report_delay(user(), bid, NOW+timedelta(hours=1), now=NOW)
    reminders.sweep_consultation_notifications(NOW+timedelta(minutes=50))
    with ctx.engine.begin() as c:
        c.execute(text("""
            INSERT INTO notifications(org_id,recipient_id,kind,title,dedupe_key)
            VALUES (:org,:parent,'new_card','[TEST] 이전 알림','[TEST] previous')
        """), {"org": seed.ORG, "parent": seed.PARENT})
        c.execute(text("INSERT INTO events(org_id,actor_type,action) VALUES (:org,'system','created')"), {"org": seed.ORG})
    command.downgrade(alembic_config, "0006")
    with ctx.engine.connect() as c:
        assert c.scalar(text("SELECT count(*) FROM consultation_bookings WHERE id=:id"), {"id": bid}) == 1
        assert c.scalar(text("SELECT count(*) FROM notifications WHERE dedupe_key='[TEST] previous'")) == 1
        assert c.scalar(text("SELECT count(*) FROM events WHERE action='created'")) >= 1
        assert c.scalar(text("SELECT count(*) FROM notifications WHERE kind LIKE 'consultation_%'")) == 0
    command.upgrade(alembic_config, "head")
    with ctx.engine.connect() as c:
        assert c.scalar(text("SELECT expected_end_at FROM consultation_bookings WHERE id=:id"), {"id": bid}) is None
