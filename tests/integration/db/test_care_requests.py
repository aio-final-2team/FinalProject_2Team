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
                       json={"decision": "confirm"}).status_code == 200
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
                               json={"decision": "complete"})
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
                            json={"decision": "complete"})
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
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0009"
        assert connection.scalar(text("SELECT status FROM requests WHERE id=:id"), {"id": rid}) == "assigned"
