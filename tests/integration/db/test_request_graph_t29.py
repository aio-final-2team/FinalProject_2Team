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
