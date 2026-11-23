"""T29 그래프의 체크포인트와 중복 요청 처리 경계를 실제 DB에서 확인한다."""

from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from uuid import uuid4

from sqlalchemy import text

from app.modules.requests import graph_agent, runner
from app.mock import seed
from app.core.auth import issue_token
from app.core import users
from app.core.schedule import KST


def test_graph_agent_stores_thread_and_does_not_duplicate_card(db_client, seeded_db, monkeypatch):
    monkeypatch.setattr(runner, "settings", replace(runner.settings,
        request_agent="app.modules.requests.graph_agent:run_request"))
    login = db_client.post("/api/v1/auth/login", json={"login_id": "parent01", "password": "demo1234"})
    headers = {"Authorization": "Bearer " + login.json()["access_token"]}
    response = db_client.post("/api/v1/requests", headers=headers, json={
        "client_request_id": str(uuid4()), "type": "inquiry", "body": "[TEST] 식단 문의",
        "child_id": str(seed.CHILD)})
    assert response.status_code in (200, 201, 202), response.text
    request_id = response.json()["request"]["id"] if "request" in response.json() else response.json()["id"]
    with seeded_db.connect() as connection:
        before = connection.scalar(text("SELECT count(*) FROM events WHERE request_id=:id"), {"id": request_id})
        card = connection.execute(text("SELECT id, graph_thread_id FROM cards WHERE request_id=:id"),
                                  {"id": request_id}).mappings().one()
        assert card["graph_thread_id"] == graph_agent.thread_id(request_id)
        assert connection.scalar(text("SELECT count(*) FROM checkpoints WHERE thread_id=:thread"),
                                 {"thread": card["graph_thread_id"]}) > 0
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(graph_agent.run_request, [request_id, request_id]))
    with seeded_db.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM cards WHERE request_id=:id"), {"id": request_id}) == 1
        assert connection.scalar(text("SELECT count(*) FROM events WHERE request_id=:id"), {"id": request_id}) == before

    teacher = {"Authorization": "Bearer " + issue_token(users.get_user(seed.TEACHER))}
    decision = db_client.post(f"/api/v1/cards/{card['id']}/decisions", headers=teacher,
                              json={"version": 1, "decision": "approve"})
    assert decision.status_code == 200, decision.text
    assert graph_agent.resume_request(card["id"]) is None  # API 커밋 뒤 이미 재개했다
    graph_agent.sweep_approval_resumes()
    with seeded_db.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM approvals WHERE card_id=:id"), {"id": card["id"]}) == 1
        assert connection.scalar(text("SELECT count(*) FROM request_messages WHERE request_id=:id"),
                                 {"id": request_id}) == 2


def graph_request(db_client, monkeypatch, kind="inquiry"):
    monkeypatch.setattr(runner, "settings", replace(runner.settings,
        request_agent="app.modules.requests.graph_agent:run_request"))
    parent = {"Authorization": "Bearer " + issue_token(users.get_user(seed.PARENT))}
    response = db_client.post("/api/v1/requests", headers=parent, json={
        "client_request_id": str(uuid4()), "type": kind, "body": "[TEST] 일반 요청",
        "child_id": str(seed.CHILD)})
    assert response.status_code == 202, response.text
    request_id = response.json()["request"]["id"]
    return request_id, parent


def card_for(seeded_db, request_id, kind):
    with seeded_db.connect() as connection:
        return connection.execute(text("""
            SELECT * FROM cards WHERE request_id=:id AND kind=:kind ORDER BY created_at DESC,id DESC LIMIT 1
        """), {"id": request_id, "kind": kind}).mappings().one()


def teacher_auth():
    return {"Authorization": "Bearer " + issue_token(users.get_user(seed.TEACHER))}


def test_resume_failure_keeps_approval_and_sweeper_recovers(db_client, seeded_db, monkeypatch):
    request_id, _ = graph_request(db_client, monkeypatch)
    card = card_for(seeded_db, request_id, "reply_draft")
    with seeded_db.connect() as connection:
        before = connection.scalar(text("SELECT count(*) FROM checkpoints WHERE thread_id=:thread"),
                                   {"thread": card["graph_thread_id"]})

    def unavailable(card_id):
        raise RuntimeError("[TEST] 재개 전달 실패")

    original = graph_agent.try_resume
    monkeypatch.setattr(graph_agent, "try_resume", unavailable)
    response = db_client.post(f"/api/v1/cards/{card['id']}/decisions", headers=teacher_auth(),
                              json={"version": 1, "decision": "approve"})
    assert response.status_code == 200, response.text
    monkeypatch.setattr(graph_agent, "try_resume", original)
    runner.sweep_missing_cards(datetime.now(KST))  # 워커가 부르는 실제 재전달 입구
    assert graph_agent.resume_request(card["id"]) is None
    with seeded_db.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM checkpoints WHERE thread_id=:thread"),
                                 {"thread": card["graph_thread_id"]}) > before
        assert connection.scalar(text("SELECT count(*) FROM approvals WHERE card_id=:id"), {"id": card["id"]}) == 1


def test_reject_attaches_next_card_without_duplicate(db_client, seeded_db, monkeypatch):
    request_id, _ = graph_request(db_client, monkeypatch)
    first = card_for(seeded_db, request_id, "reply_draft")
    response = db_client.post(f"/api/v1/cards/{first['id']}/decisions", headers=teacher_auth(),
                              json={"version": 1, "decision": "reject", "reason_code": "wrong_fact"})
    assert response.status_code == 200, response.text
    second = card_for(seeded_db, request_id, "reply_draft")
    assert second["id"] != first["id"] and second["graph_thread_id"] == first["graph_thread_id"]
    graph_agent.sweep_approval_resumes()
    with seeded_db.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM cards WHERE request_id=:id"), {"id": request_id}) == 2
        assert connection.scalar(text("SELECT count(*) FROM approvals WHERE card_id=:id"), {"id": first["id"]}) == 1


def test_hold_and_resume_keep_graph_waiting(db_client, seeded_db, monkeypatch):
    from datetime import date, timedelta

    request_id, _ = graph_request(db_client, monkeypatch)
    card = card_for(seeded_db, request_id, "reply_draft")
    hold = db_client.post(f"/api/v1/cards/{card['id']}/decisions", headers=teacher_auth(), json={
        "version": 1, "decision": "hold", "reason_text": "[TEST] 확인 중",
        "hold_until": (date.today() + timedelta(days=2)).isoformat()})
    assert hold.status_code == 200, hold.text
    resume = db_client.post(f"/api/v1/cards/{card['id']}/decisions", headers=teacher_auth(),
                            json={"version": 2, "decision": "resume"})
    assert resume.status_code == 200, resume.text
    assert card_for(seeded_db, request_id, "reply_draft")["graph_thread_id"] == card["graph_thread_id"]
    approve = db_client.post(f"/api/v1/cards/{card['id']}/decisions", headers=teacher_auth(),
                             json={"version": 3, "decision": "approve"})
    assert approve.status_code == 200, approve.text
    assert graph_agent.resume_request(card["id"]) is None


def test_consultation_booking_resumes_graph(db_client, seeded_db, monkeypatch):
    request_id, parent = graph_request(db_client, monkeypatch, "consultation")
    card = card_for(seeded_db, request_id, "consult_slots")
    view = db_client.get(f"/api/v1/requests/{request_id}", headers=parent)
    slot_id = view.json()["consultation"]["slots"][0]["id"]
    choice = db_client.post(f"/api/v1/requests/{request_id}/slot-choices", headers=parent,
                            json={"slot_ids": [slot_id]})
    assert choice.status_code == 200, choice.text
    booking = db_client.post(f"/api/v1/cards/{card['id']}/bookings", headers=teacher_auth(),
                             json={"version": 1, "slot_id": slot_id})
    assert booking.status_code == 200, booking.text
    assert graph_agent.resume_request(card["id"]) is None


def test_escalation_does_not_finish_waiting_graph(db_client, seeded_db, monkeypatch):
    request_id, _ = graph_request(db_client, monkeypatch, "complaint")
    card = card_for(seeded_db, request_id, "reply_draft")
    with seeded_db.connect() as connection:
        before = connection.scalar(text("SELECT count(*) FROM checkpoints WHERE thread_id=:thread"),
                                   {"thread": card["graph_thread_id"]})
    response = db_client.post(f"/api/v1/cards/{card['id']}/decisions", headers=teacher_auth(),
                              json={"version": 1, "decision": "escalate"})
    assert response.status_code == 200, response.text
    graph_agent.sweep_approval_resumes()
    with seeded_db.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM checkpoints WHERE thread_id=:thread"),
                                 {"thread": card["graph_thread_id"]}) == before
        assert connection.scalar(text("SELECT status FROM cards WHERE id=:id"), {"id": card["id"]}) == "pending"


def slow_prepare(monkeypatch, seen, delay=0.4):
    """카드를 만드는 느린 모의 모델 자리. 이때 풀에서 빌려 간 연결 수와 호출 수를 센다."""
    import time
    from app.core.db import get_engine

    original = graph_agent.prepare_request

    def slow(request_id):
        seen.append(get_engine().pool.checkedout())
        time.sleep(delay)
        return original(request_id)

    monkeypatch.setattr(graph_agent, "prepare_request", slow)


def advisory_locks(seeded_db):
    with seeded_db.connect() as connection:
        return connection.scalar(text("""
            SELECT count(*) FROM pg_locks WHERE locktype='advisory'
              AND database=(SELECT oid FROM pg_database WHERE datname=current_database())
        """))


def test_graph_run_does_not_hold_pool_connection_while_slow(db_client, seeded_db, monkeypatch):
    from app.core.db import get_engine

    seen = []
    slow_prepare(monkeypatch, seen)
    request_id, _ = graph_request(db_client, monkeypatch)
    assert seen == [0]  # 느린 처리 중 풀 연결 0개. 예전에는 잠금 트랜잭션이 1개를 쥐고 있었다
    assert get_engine().pool.checkedout() == 0
    assert advisory_locks(seeded_db) == 0
    assert card_for(seeded_db, request_id, "reply_draft")["graph_thread_id"] == graph_agent.thread_id(request_id)


def test_slow_duplicate_runs_are_serialized_by_session_lock(db_client, seeded_db, monkeypatch):
    import threading
    import time

    request_id, _ = graph_request(db_client, monkeypatch)
    state = {"active": 0, "peak": 0}
    guard = threading.Lock()

    def slow(_request_id):  # 잠금이 없으면 세 실행이 겹쳐서 peak가 2 이상이 된다
        with guard:
            state["active"] += 1
            state["peak"] = max(state["peak"], state["active"])
        time.sleep(0.4)
        with guard:
            state["active"] -= 1

    monkeypatch.setattr(graph_agent, "prepare_request", slow)
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(graph_agent.run_request, [request_id] * 3))
    assert state["peak"] == 1 and state["active"] == 0
    with seeded_db.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM cards WHERE request_id=:id"), {"id": request_id}) == 1
    assert advisory_locks(seeded_db) == 0


def test_session_lock_is_released_after_error(db_client, seeded_db, monkeypatch):
    import pytest
    from app.core.db import get_engine

    request_id, _ = graph_request(db_client, monkeypatch)
    card = card_for(seeded_db, request_id, "reply_draft")

    def broken(*args):
        raise RuntimeError("[TEST] 그래프 오류")

    original = graph_agent.build_graph
    monkeypatch.setattr(graph_agent, "build_graph", broken)
    with pytest.raises(RuntimeError):
        graph_agent.run_request(request_id)
    with pytest.raises(RuntimeError):
        graph_agent.resume_request(card["id"])
    assert advisory_locks(seeded_db) == 0
    assert get_engine().pool.checkedout() == 0
    monkeypatch.setattr(graph_agent, "build_graph", original)
    assert graph_agent.run_request(request_id) is not None  # 잠금이 남았다면 여기서 멈춘다


def test_concurrent_double_approval_sends_once_and_resumes_after_commit(db_client, seeded_db, monkeypatch):
    request_id, _ = graph_request(db_client, monkeypatch)
    card = card_for(seeded_db, request_id, "reply_draft")
    committed_at_resume = []
    original = graph_agent.resume_request

    def spy(card_id):
        with seeded_db.connect() as connection:  # 재개 시점에 승인이 이미 커밋돼 보여야 한다
            committed_at_resume.append(connection.scalar(
                text("SELECT status FROM cards WHERE id=:id"), {"id": card_id}))
        return original(card_id)

    monkeypatch.setattr(graph_agent, "resume_request", spy)

    def approve(_):
        return db_client.post(f"/api/v1/cards/{card['id']}/decisions", headers=teacher_auth(),
                              json={"version": 1, "decision": "approve"})

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(approve, range(2)))
    assert sorted(response.status_code for response in responses) == [200, 409], [r.text for r in responses]
    assert next(r for r in responses if r.status_code == 409).json()["error"]["code"] == "ALREADY_DECIDED"
    assert committed_at_resume == ["done"]  # 재개는 성공한 한 번만, 커밋 뒤에만
    with seeded_db.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM approvals WHERE card_id=:id"), {"id": card["id"]}) == 1
        assert connection.scalar(text("SELECT count(*) FROM request_messages WHERE request_id=:id"),
                                 {"id": request_id}) == 2  # 접수 + 발송 1번
    assert advisory_locks(seeded_db) == 0
