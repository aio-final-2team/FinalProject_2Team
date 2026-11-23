"""요청 처리의 모델 호출이 요청 행 잠금 밖에서 돌고, 3분을 넘기면 초안 없는 카드로 넘기는지 실제 DB에서 확인한다."""

import threading
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.mock import seed
from app.modules.requests import agent_stub, runner
from db.seeds.documents import seed_documents

BODY = "[TEST] 겨울방학 언제부터인가요?"


class SlowModel:
    """자료·검사 AI 대역. 부를 때마다 hook을 먼저 부른다."""
    hook = None
    chunk_id = None

    def __init__(self, role):
        self.role = role

    def json(self, system, user):
        SlowModel.hook(self.role)
        if self.role == "CHECKER":
            return {"passed": True, "issues": []}
        return {"text": "[TEST] 자료 확인 답", "evidence": [{"chunk_id": SlowModel.chunk_id, "quote": "12월 24일"}],
                "no_evidence": False, "conflict": False}


def use_model(seeded_db, monkeypatch, hook):
    with seeded_db.begin() as connection:
        seed_documents(connection)
        SlowModel.chunk_id = connection.scalar(text("""
            SELECT ch.id FROM document_chunks ch JOIN documents d ON d.id=ch.document_id
            WHERE d.title='겨울방학 안내' AND ch.location='1쪽 겨울방학 기간'
        """))
    monkeypatch.setenv("ANSWER_WRITER", "graph")
    from agents.graphs import answer as graph
    SlowModel.hook = staticmethod(hook)
    monkeypatch.setattr(graph, "OpenAIModel", SlowModel)


def submit(db_client):
    login = db_client.post("/api/v1/auth/login", json={"login_id": "parent01", "password": "demo1234"})
    response = db_client.post("/api/v1/requests", headers={"Authorization": "Bearer " + login.json()["access_token"]},
                              json={"client_request_id": str(uuid4()), "type": "inquiry", "body": BODY,
                                    "child_id": str(seed.CHILD)})
    assert response.status_code == 202, response.text
    return response.json()["request"]["id"]


def cards_of(seeded_db, request_id):
    with seeded_db.connect() as connection:
        return connection.execute(text("SELECT * FROM cards WHERE request_id=:id ORDER BY created_at,id"),
                                  {"id": request_id}).mappings().all()


def handoff_reasons(seeded_db, request_id):
    with seeded_db.connect() as connection:
        return connection.scalars(text("""
            SELECT detail->>'handoff_reason' FROM events WHERE request_id=:id AND detail ? 'handoff_reason' ORDER BY id
        """), {"id": request_id}).all()


def test_answer_models_run_outside_request_row_lock(db_client, seeded_db, monkeypatch):
    from app.core.db import get_engine

    seen = []

    def probe(role):
        checked_out = get_engine().pool.checkedout()  # 아래 탐침 연결보다 먼저 잰다
        with seeded_db.connect() as connection:
            try:
                connection.execute(text("SELECT id FROM requests WHERE body=:body FOR UPDATE NOWAIT"), {"body": BODY})
                lockable = True
            except OperationalError:  # 예전에는 모델 호출 동안 실행이 이 행을 잠가 두었다
                lockable = False
        seen.append((role, checked_out, lockable))

    use_model(seeded_db, monkeypatch, probe)
    request_id = submit(db_client)
    assert seen == [("DOCUMENT", 0, True), ("CHECKER", 0, True)]
    [card] = cards_of(seeded_db, request_id)
    assert card["draft"]["text"] == "[TEST] 자료 확인 답" and card["check_result"]["passed"] is True


def test_ai_timeout_hands_off_empty_card_and_drops_late_draft(db_client, seeded_db, monkeypatch):
    release, finished = threading.Event(), threading.Event()
    use_model(seeded_db, monkeypatch, lambda role: role == "DOCUMENT" and release.wait(10))
    original = agent_stub.run_request

    def tracked(request_id):
        try:
            return original(request_id)
        finally:
            finished.set()

    monkeypatch.setattr(agent_stub, "run_request", tracked)
    monkeypatch.setattr(runner, "AI_TIMEOUT_SECONDS", 0.3)
    request_id = submit(db_client)  # 실행기는 0.3초 뒤 기다리기를 멈추고 넘긴다. 모델은 아직 도는 중
    [card] = cards_of(seeded_db, request_id)
    assert card["kind"] == "reply_draft" and card["assignee_id"] is None
    assert not card["draft"].get("text") and card["check_result"] is None
    assert handoff_reasons(seeded_db, request_id) == ["ai_timeout"]

    release.set()
    assert finished.wait(10)  # 늦게 끝난 실행은 저장 전 재확인에서 버려진다
    [late] = cards_of(seeded_db, request_id)
    assert late["id"] == card["id"] and not late["draft"].get("text")
    with seeded_db.connect() as connection:
        assert connection.scalar(text("SELECT status FROM requests WHERE id=:id"), {"id": request_id}) == "awaiting_review"


def test_timeout_error_raised_by_agent_is_ai_failed(db_client, seeded_db, monkeypatch):
    def broken(request_id):
        raise TimeoutError("[TEST] 도구 시간 초과")

    monkeypatch.setattr(agent_stub, "run_request", broken)
    request_id = submit(db_client)
    assert handoff_reasons(seeded_db, request_id) == ["ai_failed", "ai_failed"]  # tool_failed 이력 + 인계
    assert len(cards_of(seeded_db, request_id)) == 1
