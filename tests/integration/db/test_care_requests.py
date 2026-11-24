"""T46 동시 완료·감사 실패 롤백과 0008 되돌리기를 실제 임시 DB에서 검사해요."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event

from alembic import command
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import text

from app.main import app
from app.mock import seed
from app.modules.requests import events


BASE = "/api/v1"


def setup_request(client):
    def login(who):
        result = client.post(BASE + "/auth/login", json={"login_id": who, "password": "demo1234"})
        assert result.status_code == 200, result.text
        return {"Authorization": "Bearer " + result.json()["access_token"]}
    parent, teacher = login("parent01"), login("teacher01")
    result = client.post(BASE + "/requests", headers=parent, json={
        "client_request_id": "care-db-test-0001", "child_id": str(seed.CHILD),
        "type": "medication", "body": "[TEST] 보호자 원문 그대로"})
    assert result.status_code == 202, result.text
    rid = result.json()["request"]["id"]
    assert client.post(f"{BASE}/requests/{rid}/care-decisions", headers=teacher,
                       json={"decision": "confirm", "version": 1}).status_code == 200
    return rid, teacher


def test_overlapping_completions_wait_and_create_one_event_and_notification(db_client, seeded_db, monkeypatch):
    rid, teacher = setup_request(db_client)
    entered, release, second_started = Event(), Event(), Event()
    original = events.record
    def pause_record(connection, req, action, **kw):
        if action == "completed":
            entered.set()
            assert release.wait(5)
        return original(connection, req, action, **kw)
    monkeypatch.setattr(events, "record", pause_record)
    def complete(second=False):
        with TestClient(app) as client:
            if second:
                second_started.set()
            return client.post(f"{BASE}/requests/{rid}/care-decisions", headers=teacher,
                               json={"decision": "complete", "version": 1})
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(complete)
        assert entered.wait(5)
        second = pool.submit(complete, True)
        try:
            assert second_started.wait(5)
            with pytest.raises(TimeoutError):
                second.result(timeout=0.25)
        finally:
            release.set()
        left, right = first.result(timeout=5), second.result(timeout=5)
    assert left.status_code == right.status_code == 200
    assert left.json() == right.json()
    with seeded_db.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM events WHERE request_id=:id AND action='completed'"),
                                 {"id": rid}) == 1
        assert connection.scalar(text("SELECT count(*) FROM notifications WHERE request_id=:id AND kind='completed'"),
                                 {"id": rid}) == 1


def test_audit_failure_rolls_back_completion_and_notification(db_client, seeded_db, monkeypatch):
    rid, teacher = setup_request(db_client)
    original = events.notify_event
    def fail_after_notification(connection, event, req, card):
        original(connection, event, req, card)
        if event["action"] == "completed":
            raise RuntimeError("[TEST] 완료 이력 처리 실패")
    monkeypatch.setattr(events, "notify_event", fail_after_notification)
    result = db_client.post(f"{BASE}/requests/{rid}/care-decisions", headers=teacher,
                            json={"decision": "complete", "version": 1})
    assert result.status_code == 500 and result.json()["error"]["code"] == "INTERNAL_ERROR"
    with seeded_db.connect() as connection:
        assert connection.scalar(text("SELECT status FROM requests WHERE id=:id"), {"id": rid}) == "assigned"
        assert connection.scalar(text("SELECT count(*) FROM events WHERE request_id=:id AND action='completed'"),
                                 {"id": rid}) == 0
        assert connection.scalar(text("SELECT count(*) FROM notifications WHERE request_id=:id AND kind='completed'"),
                                 {"id": rid}) == 0


def test_0008_round_trip_preserves_request_and_check_records(db_client, seeded_db, alembic_config):
    rid, _ = setup_request(db_client)
    command.downgrade(alembic_config, "0007")
    with seeded_db.connect() as connection:
        assert connection.scalar(text("SELECT status FROM requests WHERE id=:id"), {"id": rid}) == "assigned"
        assert connection.scalar(text("SELECT count(*) FROM events WHERE request_id=:id"), {"id": rid}) == 2
        assert connection.scalar(text("SELECT count(*) FROM notifications WHERE request_id=:id"), {"id": rid}) == 0
    command.upgrade(alembic_config, "head")
    with seeded_db.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0014"
        assert connection.scalar(text("SELECT status FROM requests WHERE id=:id"), {"id": rid}) == "assigned"


def test_correction_holds_request_lock_and_stale_confirmation_waits_then_conflicts(db_client, seeded_db, monkeypatch):
    from app.modules.requests import requests

    rid, teacher = setup_request(db_client)
    login = db_client.post(BASE + "/auth/login", json={"login_id": "parent01", "password": "demo1234"})
    parent = {"Authorization": "Bearer " + login.json()["access_token"]}
    entered, release, second_started = Event(), Event(), Event()
    original = requests.set_status
    def pause_correction(connection, req, to_status, **kw):
        if kw.get("care_message"):
            entered.set()
            assert release.wait(5)
        return original(connection, req, to_status, **kw)
    monkeypatch.setattr(requests, "set_status", pause_correction)
    def send(cancel):
        with TestClient(app) as client:
            if cancel:
                return client.post(f"{BASE}/requests/{rid}/messages", headers=parent, json={"body": "[TEST] 취소"})
            second_started.set()
            return client.post(f"{BASE}/requests/{rid}/care-decisions", headers=teacher,
                               json={"decision": "confirm", "version": 1})
    with ThreadPoolExecutor(max_workers=2) as pool:
        cancellation = pool.submit(send, True)
        assert entered.wait(5)
        confirmation = pool.submit(send, False)
        try:
            assert second_started.wait(5)
            with pytest.raises(TimeoutError):
                confirmation.result(timeout=0.5)
        finally:
            release.set()
        assert cancellation.result(timeout=5).status_code == 201
        result = confirmation.result(timeout=5)
    assert result.status_code == 409 and result.json()["error"]["code"] == "CARD_VERSION_CONFLICT"
    detail = db_client.get(f"{BASE}/requests/{rid}", headers=teacher).json()
    assert detail["care"]["version"] == 2 and detail["care"]["confirmed_at"] is None


def test_detail_keeps_messages_and_version_consistent_while_correction_arrives(db_client, seeded_db, monkeypatch):
    from app.modules.requests import care

    rid, teacher = setup_request(db_client)
    login = db_client.post(BASE + "/auth/login", json={"login_id": "parent01", "password": "demo1234"})
    parent = {"Authorization": "Bearer " + login.json()["access_token"]}
    entered, release, second_started = Event(), Event(), Event()
    original = care.view
    def pause_view(connection, req):
        if not entered.is_set():
            entered.set()
            assert release.wait(5)
        return original(connection, req)
    monkeypatch.setattr(care, "view", pause_view)
    def send(correction):
        with TestClient(app) as client:
            if correction:
                second_started.set()
                return client.post(f"{BASE}/requests/{rid}/messages", headers=parent, json={"body": "[TEST] 정정"})
            return client.get(f"{BASE}/requests/{rid}", headers=teacher)
    with ThreadPoolExecutor(max_workers=2) as pool:
        detail = pool.submit(send, False)
        assert entered.wait(5)
        correction = pool.submit(send, True)
        try:
            assert second_started.wait(5)
            with pytest.raises(TimeoutError):
                correction.result(timeout=0.5)
        finally:
            release.set()
        seen = detail.result(timeout=5)
        assert correction.result(timeout=5).status_code == 201
    assert seen.status_code == 200, seen.text
    assert seen.json()["care"]["version"] == 1 and len(seen.json()["messages"]) == 1
    latest = db_client.get(f"{BASE}/requests/{rid}", headers=teacher).json()
    assert latest["care"]["version"] == 2 and len(latest["messages"]) == 2


def test_pickup_notification_delivers_and_retries_after_hours_without_workday_delay(db_client, seeded_db, monkeypatch):
    from datetime import datetime, timedelta
    from app.core.schedule import KST
    from app.modules.notifications import delivery

    evening = datetime(2026, 11, 20, 19, 30, tzinfo=KST)
    with seeded_db.begin() as connection:
        connection.execute(text("DELETE FROM notifications"))
        connection.execute(text("""
            INSERT INTO notifications(org_id,recipient_id,request_id,kind,title,dedupe_key,deliver_after,next_attempt_at)
            VALUES (:org,:teacher,:request,'care_requested','[TEST] 귀가 변경','test:pickup-evening',:now,:now)
        """), {"org": seed.ORG, "teacher": seed.TEACHER, "request": seed.REQUEST_PICKUP, "now": evening})
    original = delivery._deliver
    def fail_once(*args):
        raise RuntimeError("[TEST] 앱 안 발송 실패")
    monkeypatch.setattr(delivery, "_deliver", fail_once)
    assert delivery.deliver_pending(evening) == 0
    with seeded_db.connect() as connection:
        retry = connection.execute(text("SELECT * FROM notifications WHERE dedupe_key='test:pickup-evening'")).mappings().one()
    assert retry["next_attempt_at"] == evening + timedelta(seconds=60)
    assert retry["attempts"] == 1
    monkeypatch.setattr(delivery, "_deliver", original)
    assert delivery.deliver_pending(evening + timedelta(seconds=60)) == 1
    with seeded_db.connect() as connection:
        assert connection.scalar(text("SELECT status FROM notifications WHERE dedupe_key='test:pickup-evening'")) == "sent"


def test_note_listing_uses_one_connection_and_one_bulk_request_query(db_client, seeded_db, monkeypatch):
    from contextlib import contextmanager
    from sqlalchemy import event
    from app.modules.daily_notes import notes
    from app.core.schedule import KST
    from datetime import datetime

    _, teacher = setup_request(db_client)
    day = datetime.now(KST).date().isoformat()
    result = db_client.post(BASE + "/daily-notes/drafts", headers=teacher, json={
        "classroom_id": str(seed.CLASS_STAR), "note_date": day, "activities": "[TEST] 놀이", "supplies": "수건"})
    assert result.status_code == 202, result.text
    opens, queries = [], []
    original = notes.transaction
    @contextmanager
    def counted_connection():
        opens.append(True)
        with original() as connection:
            yield connection
    def count_query(connection, cursor, statement, parameters, context, many):
        if "SELECT id,type,status,child_id FROM requests" in statement:
            queries.append(statement)
    monkeypatch.setattr(notes, "transaction", counted_connection)
    event.listen(seeded_db, "before_cursor_execute", count_query)
    try:
        listed = db_client.get(BASE + "/daily-notes", headers=teacher,
                               params={"date": day, "classroom_id": str(seed.CLASS_STAR), "size": 100})
    finally:
        event.remove(seeded_db, "before_cursor_execute", count_query)
    assert listed.status_code == 200, listed.text
    assert len(listed.json()["items"]) == 20
    assert len(opens) == len(queries) == 1
