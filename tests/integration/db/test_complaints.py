"""T31: 분류 동시 실행·30일 경계·기한과 알림 저장을 실제 PG로 확인해요."""

from concurrent.futures import ThreadPoolExecutor, TimeoutError
from dataclasses import replace
from datetime import datetime, timedelta, date
from threading import Event
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.core import schedule
from app.core.auth import issue_token
from app.core.users import get_user
from app.mock import seed
from app.modules.requests.complaints import repeat_count
from app.modules.notifications.notifications import notify_event
from app.modules.requests import agent_stub


def save(connection, *, body="[TEST] 가방 분실", created_at=None, topic=None):
    return dict(connection.execute(text("""
        INSERT INTO requests (org_id,classroom_id,child_id,requester_id,client_request_id,type,body,title,created_at,topic_key)
        VALUES (:org,:class,:child,:parent,:key,'complaint',:body,:body,coalesce(:at,now()),:topic) RETURNING *
    """), {"org": seed.ORG, "class": seed.CLASS_STAR, "child": seed.CHILD, "parent": seed.PARENT,
           "key": str(uuid4()), "body": body, "at": created_at, "topic": topic}).mappings().one())


def test_repeat_window_includes_exactly_thirty_days_and_excludes_older(seeded_db):
    with seeded_db.begin() as connection:
        now = connection.scalar(text("SELECT now()"))
        req = save(connection, topic="belongings")
        save(connection, topic="belongings", created_at=now - timedelta(days=30))
        save(connection, topic="belongings", created_at=now - timedelta(days=30, microseconds=1))
        assert repeat_count(connection, req) == 2
        assert repeat_count(connection, {**req, "topic_key": "other"}) is None
        assert repeat_count(connection, {**req, "topic_key": None}) is None
        assert repeat_count(connection, {**req, "type": "inquiry"}) is None


def test_delay_boundary_counts_waiting_cards_and_does_not_create_reports(seeded_db):
    with seeded_db.begin() as connection:
        rid = save(connection)["id"]
    agent_stub.run_request(rid)
    with seeded_db.begin() as connection:
        connection.execute(text("UPDATE cards SET due_at=now() WHERE request_id=:id"), {"id": rid})
        assert connection.scalar(text("SELECT delayed FROM director_overview WHERE org_id=:org"), {"org": seed.ORG}) == 0
        connection.execute(text("UPDATE cards SET due_at=now()-interval '1 microsecond' WHERE request_id=:id"), {"id": rid})
        assert connection.scalar(text("SELECT delayed FROM director_overview WHERE org_id=:org"), {"org": seed.ORG}) == 1
        connection.execute(text("UPDATE cards SET status='done' WHERE request_id=:id"), {"id": rid})
        assert connection.scalar(text("SELECT delayed FROM director_overview WHERE org_id=:org"), {"org": seed.ORG}) == 0
        assert connection.scalar(text("SELECT count(*) FROM cards WHERE kind='director_report'")) == 0


def test_concurrent_second_and_third_complaints_cannot_miss_report(seeded_db, monkeypatch):
    with seeded_db.begin() as connection:
        first, second, third = [save(connection)["id"] for _ in range(3)]
    agent_stub.run_request(first)
    entered, release = Event(), Event()
    original = agent_stub.set_status

    def pause_first(connection, req, status, *args, **kwargs):
        event = original(connection, req, status, *args, **kwargs)
        if req["id"] == second and status == "awaiting_review":
            entered.set()
            assert release.wait(10), "[TEST] 첫 트랜잭션 해제 시간 초과"
        return event

    monkeypatch.setattr(agent_stub, "set_status", pause_first)
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(agent_stub.run_request, second)
        try:
            assert entered.wait(10), "[TEST] 두 번째 분류 진입 시간 초과"
            concurrent = pool.submit(agent_stub.run_request, third)
            try:
                concurrent.result(timeout=0.5)
            except TimeoutError:
                pass
        finally:
            release.set()
        pending.result(timeout=10)
        concurrent.result(timeout=10)
    # 요청당 한 번만 저장하고, 세 번째 분류가 앞선 커밋을 포함해야 해요.
    agent_stub.run_request(third)
    with seeded_db.connect() as connection:
        reports = connection.execute(text("SELECT request_id FROM cards WHERE kind='director_report'")).scalars().all()
        assert reports == [third]
        assert connection.scalar(text("SELECT count(*) FROM cards")) == 4
        assert connection.scalar(text("SELECT count(*) FROM events WHERE action='escalated'")) == 1
        assert connection.scalar(text("SELECT count(*) FROM notifications WHERE kind='director_report'")) == 1
        assert connection.scalar(text("SELECT count(*) FROM approvals")) == 0


@pytest.mark.parametrize("body,risk,expected", [
    ("[TEST] 가방 분실", "normal", "2026-11-17T18:00:00+09:00"),
    ("[TEST] 아이가 다쳤어요", "urgent", "2026-11-13T20:00:00+09:00"),
    ("[TEST] 판단 필요", "uncertain", "2026-11-13T20:00:00+09:00"),
])
def test_persisted_deadlines_skip_holidays_only_for_normal_and_overdue_does_not_escalate(
    db_client, seeded_db, monkeypatch, body, risk, expected
):
    monkeypatch.setattr(schedule, "settings", replace(schedule.settings, holidays=(date(2026, 11, 16),)))
    start = datetime.fromisoformat("2026-11-13T18:00:00+09:00")
    with seeded_db.begin() as connection:
        rid = save(connection, body=body, created_at=start)["id"]
    agent_stub.run_request(rid)
    auth = {"Authorization": "Bearer " + issue_token(get_user(seed.DIRECTOR))}
    response = db_client.get("/api/v1/cards?size=100", headers=auth)
    assert response.status_code == 200, response.text
    rows = [c for c in response.json()["items"] if c["request_id"] == str(rid)]
    assert len(rows) == (1 if risk == "normal" else 2)
    assert all(c["due_at"] == expected and c["is_delayed"] for c in rows)
    assert db_client.get("/api/v1/overview", headers=auth).json()["delayed"] == len(rows)
    for _ in range(2):
        assert db_client.get("/api/v1/cards", headers=auth).status_code == 200
    with seeded_db.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM cards WHERE kind='director_report'")) == (risk != "normal")
        assert connection.scalar(text("SELECT count(*) FROM approvals")) == 0
        assert connection.scalar(text("SELECT count(*) FROM request_messages WHERE request_id=:id"), {"id": rid}) == 0


@pytest.mark.parametrize("body,categories,kind,immediate", [
    ("[TEST] 아이가 다쳤어요", ("child_safety",), "urgent_complaint", True),
    ("[TEST] 가만두지 않겠어요", ("child_safety",), "urgent_complaint", False),
    ("[TEST] 변호사에게 물었어요", ("child_safety",), "urgent_complaint", False),
    ("[TEST] 개인정보 유출", ("child_safety",), "urgent_complaint", False),
    ("[TEST] 판단 필요", ("child_safety",), "uncertain_complaint", False),
    ("[TEST] 가만두지 않겠어요", ("child_safety", "staff_attack"), "urgent_complaint", True),
])
def test_high_risk_notifications_persist_configured_after_hours_delivery_without_parent_reply(
    seeded_db, monkeypatch, body, categories, kind, immediate
):
    from app.core import config

    monkeypatch.setenv("IMMEDIATE_RISK_CATEGORIES", ",".join(categories))
    monkeypatch.setenv("HOLIDAYS", "2026-12-25")
    monkeypatch.setattr(schedule, "settings", config.load_settings())
    at = datetime.fromisoformat("2026-12-24T20:00:00+09:00")
    with seeded_db.begin() as connection:
        rid = save(connection, body=body)["id"]
    agent_stub.run_request(rid)
    with seeded_db.begin() as connection:
        req = connection.execute(text("SELECT * FROM requests WHERE id=:id"), {"id": rid}).mappings().one()
        event = connection.execute(text("""
            UPDATE events SET created_at=:at WHERE request_id=:id AND action='escalated' RETURNING *
        """), {"id": rid, "at": at}).mappings().one()
        connection.execute(text("DELETE FROM notifications WHERE request_id=:id"), {"id": rid})
        notify_event(connection, event, req, None)
        notify_event(connection, event, req, None)
        notices = connection.execute(text("SELECT * FROM notifications WHERE request_id=:id"),
                                     {"id": rid}).mappings().all()
        assert len(notices) == 2
        assert {n["recipient_id"] for n in notices} == {seed.TEACHER, seed.DIRECTOR}
        expected = at if immediate else datetime.fromisoformat("2026-12-28T09:00:00+09:00")
        assert all(n["kind"] == kind and n["deliver_after"] == expected and n["status"] == "pending" for n in notices)
        assert connection.scalar(text("SELECT count(*) FROM approvals")) == 0
