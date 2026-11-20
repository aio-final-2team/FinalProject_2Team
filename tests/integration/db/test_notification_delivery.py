"""T26: 실제 PG의 발송 잠금·재시도·중복·노출·근무 시각을 확인해요."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Event

from alembic import command
import pytest
from sqlalchemy import text

from app.core import users
from app.core.schedule import KST
from app.mock import seed
from app.modules.notifications import delivery, notifications

NOW = datetime(2026, 12, 1, 10, tzinfo=KST)


def insert(engine, key="[TEST] notice", recipient=seed.PARENT, after=NOW, status="pending"):
    with engine.begin() as connection:
        return connection.scalar(text("""
            INSERT INTO notifications(org_id,recipient_id,kind,title,dedupe_key,deliver_after,next_attempt_at,status)
            VALUES (:org,:user,'new_card','[TEST] 알림',:key,:after,:after,:status) RETURNING id
        """), {"org": seed.ORG, "user": recipient, "key": key, "after": after, "status": status})


def notice(engine, notification_id):
    with engine.connect() as connection:
        return dict(connection.execute(text("SELECT * FROM notifications WHERE id=:id"),
                                       {"id": notification_id}).mappings().one())


def test_delivery_skips_future_held_failed_and_sent_and_keeps_first_sent_time(seeded_db):
    sent = insert(seeded_db)
    others = [insert(seeded_db, key=f"[TEST] {status}", status=status) for status in ("held", "failed", "sent")]
    future = insert(seeded_db, key="[TEST] future", after=NOW+timedelta(minutes=1))
    before = [notice(seeded_db, nid) for nid in others+[future]]
    assert delivery.deliver_pending(NOW) == 1
    row = notice(seeded_db, sent)
    assert row["status"] == "sent" and row["attempts"] == 1 and row["sent_at"] == NOW
    assert delivery.deliver_pending(NOW) == 0
    assert notice(seeded_db, sent) == row
    assert [notice(seeded_db, nid) for nid in others+[future]] == before


def test_failures_back_off_then_stop_at_three_without_hiding_or_erasing_read_time(seeded_db, monkeypatch):
    nid = insert(seeded_db)
    with seeded_db.begin() as connection:
        connection.execute(text("UPDATE notifications SET read_at=:now WHERE id=:id"), {"id": nid, "now": NOW})
    def fail(connection, row, now):
        # DB 오류도 savepoint 뒤에서 되돌려야 실패 상태를 저장할 수 있어요.
        connection.execute(text("SELECT 1/0"))
    monkeypatch.setattr(delivery, "_deliver", fail)
    for attempt, moment in enumerate((NOW, NOW+timedelta(minutes=1), NOW+timedelta(minutes=3)), 1):
        assert delivery.deliver_pending(moment) == 0
        row = notice(seeded_db, nid)
        assert row["attempts"] == attempt and row["last_error"] == "DELIVERY_FAILED"
        assert row["deliver_after"] == NOW and row["sent_at"] is None and row["read_at"] == NOW
        assert row["status"] == ("failed" if attempt == 3 else "pending")
        assert row["next_attempt_at"] == moment+timedelta(seconds=60*2**(attempt-1))
        assert delivery.deliver_pending(moment+timedelta(seconds=59)) == 0
        assert notice(seeded_db, nid)["attempts"] == attempt
    assert delivery.deliver_pending(NOW+timedelta(days=1)) == 0
    assert notice(seeded_db, nid)["attempts"] == 3
    with seeded_db.connect() as connection:
        failures = connection.scalars(text("SELECT detail FROM events WHERE detail->>'notification_id'=:id ORDER BY id"),
                                      {"id": str(nid)}).all()
        assert failures == [{"notification_id": nid, "code": "DELIVERY_FAILED", "attempts": n} for n in (1, 2, 3)]


def test_retry_success_rolls_back_partial_delivery_and_keeps_other_rows_moving(seeded_db, monkeypatch):
    nid, other = insert(seeded_db), insert(seeded_db, "[TEST] other")
    real_deliver = delivery._deliver
    def fail_one(connection, row, now):
        real_deliver(connection, row, now)
        if row["id"] == nid:
            raise RuntimeError("[TEST] private memo")
    with monkeypatch.context() as patch:
        patch.setattr(delivery, "_deliver", fail_one)
        assert delivery.deliver_pending(NOW) == 1
    assert notice(seeded_db, nid)["sent_at"] is None
    assert notice(seeded_db, other)["status"] == "sent"
    assert delivery.deliver_pending(NOW+timedelta(minutes=1)) == 1
    row = notice(seeded_db, nid)
    assert row["attempts"] == 2 and row["status"] == "sent" and row["last_error"] is None


def test_inactive_recipient_fails_without_delivery_or_retry(seeded_db, monkeypatch):
    nid = insert(seeded_db)
    with seeded_db.begin() as connection:
        connection.execute(text("UPDATE users SET is_active=false WHERE id=:id"), {"id": seed.PARENT})
    def fail(*args):
        pytest.fail("없는 수신자에게 보내면 안 돼요")
    monkeypatch.setattr(delivery, "_deliver", fail)
    assert delivery.deliver_pending(NOW) == 0
    row = notice(seeded_db, nid)
    assert row["status"] == "failed" and row["attempts"] == 0 and row["last_error"] == "RECIPIENT_UNAVAILABLE"


def test_terminal_failure_keeps_card_and_surfaces_existing_warning(seeded_db, monkeypatch):
    from app.modules.cards import card_views
    nid = insert(seeded_db)
    with seeded_db.begin() as connection:
        card_id = connection.scalar(text("""
            INSERT INTO cards(org_id,request_id,kind,status,assignee_id,draft)
            VALUES (:org,:request,'reply_draft','pending',:teacher,'{}') RETURNING id
        """), {"org": seed.ORG, "request": seed.REQUEST_COUGH, "teacher": seed.TEACHER})
        connection.execute(text("UPDATE notifications SET request_id=:request,card_id=:card WHERE id=:id"),
                           {"id": nid, "request": seed.REQUEST_COUGH, "card": card_id})
    def fail(*args):
        raise RuntimeError("[TEST] delivery unavailable")
    monkeypatch.setattr(delivery, "_deliver", fail)
    for moment in (NOW, NOW+timedelta(minutes=1), NOW+timedelta(minutes=3)):
        assert delivery.deliver_pending(moment) == 0
    result = card_views.detail(users.get_user(seed.TEACHER), card_id)
    assert "notify_failed" in result["warnings"]
    assert result["card"]["status"] == "pending"
    with seeded_db.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM events WHERE card_id=:id AND action='tool_failed'"),
                                 {"id": card_id}) == 3


def test_concurrent_delivery_locks_each_notification_once(seeded_db, monkeypatch):
    nid = insert(seeded_db)
    started, release = Event(), Event()
    real_deliver = delivery._deliver
    def block(connection, row, now):
        started.set()
        assert release.wait(10)
        real_deliver(connection, row, now)
    monkeypatch.setattr(delivery, "_deliver", block)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(delivery.deliver_pending, NOW)
        try:
            assert started.wait(10)
            assert pool.submit(delivery.deliver_pending, NOW).result(timeout=2) == 0
        finally:
            release.set()
        assert first.result(timeout=10) == 1
    assert notice(seeded_db, nid)["attempts"] == 1


@pytest.mark.parametrize("recipient,risk,category,immediate", [
    (seed.TEACHER, "normal", None, False), (seed.TEACHER, "uncertain", None, False),
    (seed.TEACHER, "urgent", "child_safety", True),
    (seed.TEACHER, "urgent", "staff_attack", False),
    (seed.TEACHER, "urgent", "legal_external", False),
    (seed.TEACHER, "urgent", "privacy_leak", False),
    (seed.DIRECTOR, "urgent", "child_safety", True), (seed.PARENT, "normal", None, True),
])
def test_event_dedupe_and_work_hours(recipient, risk, category, immediate, seeded_db):
    outside = datetime(2026, 12, 4, 18, tzinfo=KST)
    with seeded_db.begin() as connection:
        req = dict(connection.execute(text("SELECT * FROM requests WHERE id=:id"),
                                      {"id": seed.REQUEST_COUGH}).mappings().one())
        event = {"id": 123456, "card_id": None, "created_at": outside}
        for _ in range(2):
            notifications.enqueue(connection, event, {**req, "risk_level": risk, "risk_category": category}, recipient, "new_card")
        row = connection.execute(text("SELECT * FROM notifications WHERE dedupe_key=:key"),
                                 {"key": f"event:{event['id']}:{recipient}"}).mappings().one()
        assert row["deliver_after"] == (outside if immediate else datetime(2026, 12, 7, 9, tzinfo=KST))
    assert delivery.deliver_pending(outside-timedelta(seconds=1)) == 0


def test_delayed_beat_respects_work_hours_without_changing_list_visibility(seeded_db):
    # 주간에 생성했지만 Beat가 퇴근 뒤에 실행돼도 일반 교직원 알림은 다음 근무일이에요.
    friday = datetime(2026, 12, 4, 17, 59, tzinfo=KST)
    nid = insert(seeded_db, recipient=seed.TEACHER, after=friday)
    outside = friday+timedelta(minutes=1)
    assert delivery.deliver_pending(outside) == 0
    row = notice(seeded_db, nid)
    assert row["attempts"] == 0 and row["deliver_after"] == friday
    assert row["next_attempt_at"] == datetime(2026, 12, 7, 9, tzinfo=KST)
    # 목록 노출은 원래 deliver_after만 보고 재시도 시간 때문에 사라지지 않아요.
    # listing은 DB now()를 쓰므로 실제 현재보다 앞선 시각으로 돌려 별도로 검증해요.
    with seeded_db.begin() as connection:
        connection.execute(text("UPDATE notifications SET deliver_after=now()-interval '1 minute' WHERE id=:id"), {"id": nid})
    result = notifications.listing(users.get_user(seed.TEACHER), 1, 20, "-created_at")
    assert nid in [n["id"] for n in result["items"]]
    assert delivery.deliver_pending(datetime(2026, 12, 7, 9, tzinfo=KST)) == 1


def test_backoff_crossing_closing_time_waits_until_next_workday(seeded_db, monkeypatch):
    friday = datetime(2026, 12, 4, 17, 59, 30, tzinfo=KST)
    nid = insert(seeded_db, recipient=seed.TEACHER, after=friday)
    def fail(*args):
        raise RuntimeError("[TEST] fail before closing")
    monkeypatch.setattr(delivery, "_deliver", fail)
    assert delivery.deliver_pending(friday) == 0
    assert notice(seeded_db, nid)["next_attempt_at"] == datetime(2026, 12, 7, 9, tzinfo=KST)
    assert delivery.deliver_pending(friday+timedelta(minutes=2)) == 0
    assert notice(seeded_db, nid)["attempts"] == 1


def test_retry_column_backfills_existing_notification_and_round_trips(seeded_db, alembic_config):
    command.downgrade(alembic_config, "0004")
    with seeded_db.begin() as connection:
        old = dict(connection.execute(text("""
            INSERT INTO notifications(org_id,recipient_id,kind,title,dedupe_key)
            VALUES (:org,:user,'new_card','[TEST] 이전 알림','[TEST] migration') RETURNING *
        """), {"org": seed.ORG, "user": seed.PARENT}).mappings().one())
    command.upgrade(alembic_config, "head")
    row = notice(seeded_db, old["id"])
    assert row.pop("next_attempt_at") is not None and row == old
    command.downgrade(alembic_config, "0004")
    assert notice(seeded_db, old["id"]) == old
    command.upgrade(alembic_config, "head")
    assert notice(seeded_db, old["id"])["next_attempt_at"] is not None
