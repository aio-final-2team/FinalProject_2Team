"""T29 그래프의 체크포인트와 중복 요청 처리 경계를 실제 DB에서 확인한다."""

from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from sqlalchemy import text

from app.modules.requests import graph_agent, runner
from app.mock import seed
from app.core.auth import issue_token
from app.core import users


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
    resumed = graph_agent.resume_request(card["id"])
    assert resumed["outcome"] == "done"
    graph_agent.resume_request(card["id"])
    with seeded_db.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM approvals WHERE card_id=:id"), {"id": card["id"]}) == 1
        assert connection.scalar(text("SELECT count(*) FROM request_messages WHERE request_id=:id"),
                                 {"id": request_id}) == 2
