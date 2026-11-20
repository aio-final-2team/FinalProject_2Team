"""T27-a: 저장 경계·동시 접수/확인·실패 인계·카드 누락 점검을 실제 PG로 확인해요."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta
from uuid import UUID, uuid4

import anyio
import pytest
from fastapi import BackgroundTasks
from sqlalchemy import text

from app.core import users
from app.core.schedule import KST
from app.mock import seed
from app.modules.requests import agent_stub, events, requests, runner, streams


@pytest.fixture
def parent(db_client):
    response = db_client.post("/api/v1/auth/login", json={"login_id": "parent01", "password": "demo1234"})
    assert response.status_code == 200, response.text
    return {"Authorization": "Bearer " + response.json()["access_token"]}


def create(db_client, parent, **over):
    payload = {"client_request_id": str(uuid4()), "type": "inquiry", "body": "[TEST] 식단 문의", "child_id": str(seed.CHILD)}
    payload.update(over)
    return db_client.post("/api/v1/requests", headers={**parent, "X-Request-ID": "request-trace"}, json=payload)


def rows(engine, table, request_id):
    with engine.connect() as connection:
        # 표는 이 파일의 고정 호출에서만 받아요.
        column = "id" if table == "requests" else "request_id"
        return [dict(row) for row in connection.execute(text(f"SELECT * FROM {table} WHERE {column}=:id ORDER BY id"),
                                                        {"id": request_id}).mappings()]


def test_saved_before_background_dispatch_and_event_order(seeded_db):
    tasks = BackgroundTasks()
    req, created = requests.create(users.get_user(seed.PARENT), background_tasks=tasks, client_request_id=str(uuid4()),
                                   type="inquiry", body="[TEST] 식단 문의", child_id=seed.CHILD,
                                   previous_request_id=None, trace_id="before-dispatch")
    assert created and req["status"] == "received"
    assert rows(seeded_db, "requests", req["id"])[0]["status"] == "received"
    assert len(rows(seeded_db, "request_messages", req["id"])) == 1
    assert rows(seeded_db, "cards", req["id"]) == []
    assert len(tasks.tasks) == 1
    anyio.run(tasks)
    history = rows(seeded_db, "events", req["id"])
    assert [e["action"] for e in history] == ["created", "classified", "assigned", "created", "drafted", "checked"]
    assert [(e["from_status"], e["to_status"]) for e in history if e["to_status"]] == [
        (None, "received"), ("received", "classified"), ("classified", "assigned"), ("assigned", "awaiting_review")]
    assert history[0]["detail"]["trace_id"] == "before-dispatch"
    card = rows(seeded_db, "cards", req["id"])[0]
    assert card["draft"]["no_evidence"] is True and card["check_result"]["passed"] is True
    with seeded_db.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM card_evidence WHERE card_id=:id"), {"id": card["id"]}) == 0
    notices = rows(seeded_db, "notifications", req["id"])
    assert len(notices) == 1 and notices[0]["kind"] == "new_card" and notices[0]["status"] == "pending"
    assert notices[0]["dedupe_key"] == f"event:{history[-1]['id']}:{seed.TEACHER}"


def test_concurrent_same_key_creates_one_request_message_and_agent_run(db_client, parent, seeded_db):
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: create(db_client, parent, client_request_id="same-concurrent-key"), range(2)))
    assert sorted(r.status_code for r in responses) == [200, 202]
    ids = {r.json()["request"]["id"] for r in responses}
    assert len(ids) == 1
    rid = ids.pop()
    assert len(rows(seeded_db, "request_messages", rid)) == 1 and len(rows(seeded_db, "cards", rid)) == 1
    assert sum(e["action"] == "classified" for e in rows(seeded_db, "events", rid)) == 1


def test_concurrent_confirmation_keeps_one_timestamp_event_and_notice(db_client, parent, seeded_db):
    rid = create(db_client, parent, type="complaint").json()["request"]["id"]
    with seeded_db.begin() as connection:
        connection.execute(text("UPDATE requests SET status='sent_or_booked' WHERE id=:id"), {"id": rid})
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: db_client.post(f"/api/v1/requests/{rid}/confirm", headers=parent), range(2)))
    assert all(r.status_code == 200 for r in responses) and responses[0].json() == responses[1].json()
    assert sum(e["action"] == "parent_confirmed" for e in rows(seeded_db, "events", rid)) == 1
    assert sum(n["kind"] == "parent_confirmed" for n in rows(seeded_db, "notifications", rid)) == 1


def test_message_failure_rolls_back_message_event_and_timestamp(db_client, parent, seeded_db, monkeypatch):
    rid = create(db_client, parent).json()["request"]["id"]
    before = {table: rows(seeded_db, table, rid) for table in ("requests", "events", "request_messages")}
    def fail(*args, **kwargs):
        raise RuntimeError("[TEST] 저장 중 실패")
    monkeypatch.setattr(requests, "record", fail)
    response = db_client.post(f"/api/v1/requests/{rid}/messages", headers=parent, json={"body": "[TEST] 저장하면 안 됨"})
    assert response.status_code == 500
    assert before == {table: rows(seeded_db, table, rid) for table in before}


def test_agent_failure_preserves_request_and_hands_off_without_private_error(db_client, parent, seeded_db, monkeypatch):
    monkeypatch.setattr(runner, "settings", replace(runner.settings, request_agent="missing_private_module:run"))
    response = create(db_client, parent)
    assert response.status_code == 202
    rid = response.json()["request"]["id"]
    req = rows(seeded_db, "requests", rid)[0]
    assert req["status"] == "awaiting_review"
    card = rows(seeded_db, "cards", rid)[0]
    assert card["status"] == "unassigned" and card["assignee_id"] is None and card["draft"] == {}
    history = rows(seeded_db, "events", rid)
    assert any(e["detail"].get("handoff_reason") == "ai_failed" for e in history)
    assert "missing_private_module" not in str(history)
    detail = db_client.get(f"/api/v1/requests/{rid}", headers=parent)
    assert detail.status_code == 200 and "ai_failed" not in detail.text
    assert len(rows(seeded_db, "request_messages", rid)) == 1
    notices = rows(seeded_db, "notifications", rid)
    assert len(notices) == 1 and notices[0]["recipient_id"] == seed.DIRECTOR
    assert notices[0]["kind"] == "new_card" and notices[0]["card_id"] == card["id"]
    runner.run_request(UUID(rid))
    assert rows(seeded_db, "notifications", rid) == notices


def test_stub_transaction_rolls_back_then_handoff_once(db_client, parent, seeded_db, monkeypatch):
    def fail(*args):
        raise RuntimeError("[TEST] 분류 뒤 실패")
    monkeypatch.setattr(agent_stub, "propose_slots", fail)
    rid = create(db_client, parent, type="consultation").json()["request"]["id"]
    assert [e["action"] for e in rows(seeded_db, "events", rid)] == ["created", "tool_failed", "created", "checked"]
    assert len(rows(seeded_db, "cards", rid)) == 1
    runner.run_request(UUID(rid))
    assert len(rows(seeded_db, "cards", rid)) == 1


def test_custom_entrypoint_is_selected(db_client, parent, seeded_db, monkeypatch):
    import sys
    from types import SimpleNamespace
    seen = []
    def custom(request_id):
        seen.append(request_id)
        agent_stub.run_request(request_id)
    monkeypatch.setitem(sys.modules, "test_request_entry", SimpleNamespace(run=custom))
    monkeypatch.setattr(runner, "settings", replace(runner.settings, request_agent="test_request_entry:run"))
    rid = create(db_client, parent).json()["request"]["id"]
    assert seen == [UUID(rid)] and rows(seeded_db, "requests", rid)[0]["status"] == "awaiting_review"


def test_sweep_exact_age_states_card_exclusion_and_concurrent_idempotency(seeded_db, monkeypatch):
    monkeypatch.setattr(runner, "run_request", lambda request_id: None)
    now = datetime.now(KST)
    ids = {}
    with seeded_db.begin() as connection:
        for name, state, minutes in (("old", "received", 6), ("classified", "classified", 6),
                                     ("assigned", "assigned", 6), ("boundary", "received", 5),
                                     ("new", "received", 4), ("closed", "completed", 6),
                                     ("has_card", "received", 6)):
            rid = uuid4()
            ids[name] = rid
            connection.execute(text("""
                INSERT INTO requests (id,org_id,classroom_id,requester_id,client_request_id,type,body,status,created_at)
                VALUES (:id,:org,:class,:parent,:key,'inquiry','[TEST] 누락',:status,:at)
            """), {"id": rid, "org": seed.ORG, "class": seed.CLASS_STAR, "parent": seed.PARENT,
                   "key": str(rid), "status": state, "at": now-timedelta(minutes=minutes)})
        connection.execute(text("""
            INSERT INTO cards (org_id,request_id,kind) VALUES (:org,:id,'reply_draft')
        """), {"org": seed.ORG, "id": ids["has_card"]})
    # 시드의 문의도 점검 대상이에요. 투약·귀가는 아래 별도 시험에서 제외를 확인해요.
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: runner.sweep_missing_cards(now), range(2)))
    assert runner.sweep_missing_cards(now) == 0
    for name in ("old", "classified", "assigned"):
        assert rows(seeded_db, "cards", ids[name]) == []
        assert [e["action"] for e in rows(seeded_db, "events", ids[name])] == ["agent_requeued"]
    runner.sweep_missing_cards(now+timedelta(minutes=5))
    assert runner.sweep_missing_cards(now+timedelta(minutes=5)) == 0
    for name in ("old", "classified", "assigned"):
        card = rows(seeded_db, "cards", ids[name])
        assert len(card) == 1 and card[0]["status"] == "unassigned" and card[0]["draft"] == {}
        assert rows(seeded_db, "requests", ids[name])[0]["status"] == "awaiting_review"
        changes = [e for e in rows(seeded_db, "events", ids[name]) if e["to_status"]]
        assert len(changes) == 1 and changes[0]["detail"]["handoff_reason"] == "card_missing"
        assert changes[0]["actor_type"] == "system"
        agent_stub.run_request(ids[name])
        assert len(rows(seeded_db, "cards", ids[name])) == 1
    for name in ("boundary", "new", "closed"):
        assert rows(seeded_db, "cards", ids[name]) == []
    assert len(rows(seeded_db, "cards", ids["has_card"])) == 1


def test_expiry_read_once_and_private_hold_reason_is_hidden(db_client, parent, seeded_db):
    rid = create(db_client, parent).json()["request"]["id"]
    with seeded_db.begin() as connection:
        connection.execute(text("UPDATE requests SET status='on_hold' WHERE id=:id"), {"id": rid})
        connection.execute(text("UPDATE cards SET status='on_hold',hold_until=CURRENT_DATE WHERE request_id=:id"), {"id": rid})
        connection.execute(text("""
            INSERT INTO events (org_id,request_id,actor_type,action,detail)
            VALUES (:org,:id,'system','held','{"reason_text":"[TEST] 내부 보류 이유"}')
        """), {"org": seed.ORG, "id": rid})
    for _ in range(2):
        response = db_client.get("/api/v1/requests?status=awaiting_review", headers=parent)
        assert rid in [row["id"] for row in response.json()["items"]]
        detail = db_client.get(f"/api/v1/requests/{rid}", headers=parent)
        assert "[TEST] 내부 보류 이유" not in detail.text and detail.json()["request"]["hold_until"] is None
    resumed = [e for e in rows(seeded_db, "events", rid) if e["action"] == "resumed"]
    assert len(resumed) == 1 and resumed[0]["actor_type"] == "system"
    assert sum(n["kind"] == "hold_resumed" for n in rows(seeded_db, "notifications", rid)) == 1


def test_consult_slot_expiry_and_full_rejection_detail(db_client, parent, seeded_db):
    rid = create(db_client, parent, type="consultation").json()["request"]["id"]
    with seeded_db.begin() as connection:
        connection.execute(text("UPDATE requests SET status='awaiting_review' WHERE id=:id"), {"id": rid})
        connection.execute(text("""
            UPDATE consultation_slots SET status='chosen_by_parent',chosen_at=now()-interval '25 hours'
            WHERE card_id IN (SELECT id FROM cards WHERE request_id=:id)
        """), {"id": rid})
    for _ in range(2):
        data = db_client.get(f"/api/v1/requests/{rid}", headers=parent).json()
        assert data["request"]["status"] == "needs_info"
        assert len(data["consultation"]["slots"]) == 3 and all(s["status"] == "proposed" for s in data["consultation"]["slots"])
    assert sum(e["action"] == "slot_hold_expired" for e in rows(seeded_db, "events", rid)) == 1
    with seeded_db.begin() as connection:
        card_id = connection.scalar(text("SELECT id FROM cards WHERE request_id=:id"), {"id": rid})
        connection.execute(text("UPDATE requests SET status='rejected' WHERE id=:id"), {"id": rid})
        connection.execute(text("""
            INSERT INTO approvals (org_id,card_id,card_version,decided_by,decision,reason_code,reason_text)
            VALUES (:org,:card,1,:teacher,'dismiss','other','[TEST] 원 업무가 아니에요')
        """), {"org": seed.ORG, "card": card_id, "teacher": seed.TEACHER})
    data = db_client.get(f"/api/v1/requests/{rid}", headers=parent).json()
    assert data["rejection"] == {"reason_code": "other", "reason_text": "[TEST] 원 업무가 아니에요"}


def test_sse_waits_for_persisted_completion_and_has_safe_timeout(db_client, parent, seeded_db, monkeypatch):
    monkeypatch.setattr(streams, "MAX_SECONDS", 0)
    response = db_client.get(f"/api/v1/requests/{seed.REQUEST_COUGH}/stream",
                             headers={**parent, "X-Request-ID": "stream-timeout"})
    assert response.status_code == 200 and "event: error" in response.text and "event: done" not in response.text
    assert '"trace_id": "stream-timeout"' in response.text and "UPSTREAM_UNAVAILABLE" in response.text
    monkeypatch.setattr(streams, "MAX_SECONDS", 5)
    async def finish(_):
        with seeded_db.begin() as connection:
            req = dict(connection.execute(text("SELECT * FROM requests WHERE id=:id FOR UPDATE"),
                                           {"id": seed.REQUEST_COUGH}).mappings().one())
            events.set_status(connection, req, "awaiting_review", action="checked", actor_type="agent", agent_name="checker")
    monkeypatch.setattr(streams.anyio, "sleep", finish)
    response = db_client.get(f"/api/v1/requests/{seed.REQUEST_COUGH}/stream", headers=parent)
    assert "event: stage" in response.text and "event: done" in response.text
    assert '"request_status": "awaiting_review"' in response.text


def test_seed_sweep_only_inquiries_and_one_director_notice_per_handoff(seeded_db, monkeypatch):
    monkeypatch.setattr(runner, "run_request", lambda request_id: None)
    # 날짜와 무관하게 모든 시드가 5분을 넘긴 시점에서 검사해요.
    with seeded_db.connect() as connection:
        now = connection.scalar(text("SELECT max(created_at)+interval '6 minutes' FROM requests"))
    assert runner.sweep_missing_cards(now) == 9
    with seeded_db.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM cards")) == 0
        assert connection.scalar(text("SELECT count(*) FROM events WHERE action='agent_requeued'")) == 9
        assert connection.scalar(text("SELECT count(*) FROM notifications")) == 0
    assert runner.sweep_missing_cards(now+timedelta(minutes=5)) == 9
    with seeded_db.connect() as connection:
        counts = dict(connection.execute(text("""
            SELECT r.type,count(*) FROM cards c JOIN requests r ON r.id=c.request_id GROUP BY r.type
        """)).all())
        assert counts == {"inquiry": 9}
        notices = connection.execute(text("SELECT * FROM notifications")).mappings().all()
        assert len(notices) == 9
        assert all(n["recipient_id"] == seed.DIRECTOR and n["kind"] == "new_card" for n in notices)
        assert len({n["card_id"] for n in notices}) == 9
    assert runner.sweep_missing_cards(now) == 0
    with seeded_db.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM notifications")) == 9


def test_waiting_streams_leave_threads_available_for_me(db_client, parent, seeded_db, monkeypatch):
    from httpx import ASGITransport, AsyncClient
    from app.main import app

    monkeypatch.setattr(streams, "MAX_SECONDS", 10)

    async def exercise():
        # 기본 40개 풀의 포화를 작은 풀로 재현해요. 스트림은 풀 크기의 두 배예요.
        limiter = anyio.to_thread.current_default_thread_limiter()
        previous = limiter.total_tokens
        limiter.total_tokens = 4
        started = 0
        all_started = anyio.Event()

        async def observed(scope, receive, send):
            async def observed_send(message):
                nonlocal started
                if scope["path"].endswith("/stream") and message["type"] == "http.response.start":
                    assert message["status"] == 200
                    started += 1
                    if started == 8:
                        all_started.set()
                await send(message)
            await app(scope, receive, observed_send)

        try:
            async with AsyncClient(transport=ASGITransport(app=observed), base_url="http://test") as client:
                async def stream():
                    response = await client.get(f"/api/v1/requests/{seed.REQUEST_COUGH}/stream", headers=parent)
                    assert response.status_code == 200 and "event: done" in response.text
                async with anyio.create_task_group() as group:
                    for _ in range(8):
                        group.start_soon(stream)
                    with anyio.fail_after(3):
                        await all_started.wait()
                    # 열려 있는 스트림이 실제 poll 대기에 들어갈 시간을 줘요.
                    await anyio.sleep(0.1)
                    with anyio.fail_after(2):
                        response = await client.get("/api/v1/me", headers=parent)
                    assert response.status_code == 200
                    def finish():
                        with seeded_db.begin() as connection:
                            connection.execute(text("UPDATE requests SET status='awaiting_review' WHERE id=:id"),
                                               {"id": seed.REQUEST_COUGH})
                    await anyio.to_thread.run_sync(finish)
        finally:
            limiter.total_tokens = previous

    anyio.run(exercise)
