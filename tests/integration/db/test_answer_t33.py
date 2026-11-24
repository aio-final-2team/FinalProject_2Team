"""자료 AI 문의 카드와 벡터 검색을 실제 DB에서 확인한다."""

from uuid import uuid4

from sqlalchemy import text

from agents.llm import ModelError
from app.core import users
from app.core.auth import issue_token
from app.core.db import transaction
from app.mock import seed
from app.modules.documents import embedding
from app.modules.documents.search import search_documents
from db.seeds.documents import seed_documents


class Writer:
    answer = None
    checker_answer = None
    calls = []

    def __init__(self, role):
        self.role = role

    def json(self, system, user):
        self.calls.append((self.role, user))
        if self.role == "CHECKER":
            return self.checker_answer or {"passed": True, "issues": []}
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def setup_graph(seeded_db, monkeypatch, answer):
    with seeded_db.begin() as connection:
        seed_documents(connection)
    monkeypatch.setenv("ANSWER_WRITER", "graph")
    from agents.graphs import answer as graph
    Writer.answer = answer
    Writer.checker_answer = {"passed": True, "issues": []}
    Writer.calls = []
    monkeypatch.setattr(graph, "OpenAIModel", Writer)


def create_card(db_client, body):
    login = db_client.post("/api/v1/auth/login", json={"login_id": "parent01", "password": "demo1234"})
    headers = {"Authorization": "Bearer " + login.json()["access_token"]}
    response = db_client.post("/api/v1/requests", headers=headers, json={
        "client_request_id": str(uuid4()), "type": "inquiry", "body": body, "child_id": str(seed.CHILD)})
    assert response.status_code in (200, 201, 202), response.text
    request_id = response.json()["request"]["id"] if "request" in response.json() else response.json()["id"]
    with transaction() as connection:
        card = connection.execute(text("SELECT * FROM cards WHERE request_id=:id AND kind='reply_draft'"),
                                  {"id": request_id}).mappings().one()
        evidence = connection.execute(text("""
            SELECT e.quote, e.score, ch.location FROM card_evidence e JOIN document_chunks ch ON ch.id=e.chunk_id
            WHERE e.card_id=:id
        """), {"id": card["id"]}).mappings().all()
        messages = connection.scalar(text("SELECT count(*) FROM request_messages WHERE request_id=:id"),
                                     {"id": request_id})
    return card, evidence, messages


def test_answer_evidence_card(db_client, seeded_db, monkeypatch):
    with seeded_db.begin() as connection:
        seed_documents(connection)
        chunk = connection.execute(text("""
            SELECT ch.id, ch.content FROM document_chunks ch JOIN documents d ON d.id=ch.document_id
            WHERE d.title='겨울방학 안내' AND ch.location='1쪽 겨울방학 기간'
        """)).mappings().one()
    quote = "12월 24일"
    assert quote in chunk["content"]
    setup_graph(seeded_db, monkeypatch, {"text": "겨울방학은 12월 24일부터예요.",
        "evidence": [{"chunk_id": chunk["id"], "quote": quote}], "no_evidence": False, "conflict": False})
    card, evidence, messages = create_card(db_client, "겨울방학 언제부터인가요?")
    assert card["assignee_id"] == seed.TEACHER
    assert card["draft"]["text"] == "겨울방학은 12월 24일부터예요."
    assert not card["draft"]["no_evidence"]
    assert evidence[0]["location"] == "1쪽 겨울방학 기간"
    assert evidence[0]["score"] is not None
    assert card["check_result"]["passed"] is True
    assert messages == 1  # 접수 메시지만 있고 초안은 승인 전 발송되지 않음
    assert [role for role, _ in Writer.calls] == ["DOCUMENT", "CHECKER"]


def test_parent_original_is_stored_but_model_question_is_masked(db_client, seeded_db, monkeypatch):
    setup_graph(seeded_db, monkeypatch, {"text": "확인 필요", "evidence": [], "no_evidence": True, "conflict": False})
    body = "겨울방학 언제부터인가요? 연락처 010-1234-5678"
    card, _, _ = create_card(db_client, body)
    with transaction() as connection:
        stored = connection.scalar(text("SELECT body FROM requests WHERE id=:id"), {"id": card["request_id"]})
    assert stored == body
    assert Writer.calls
    assert all("010-1234-5678" not in sent for _, sent in Writer.calls)
    assert any("[전화번호]" in sent for _, sent in Writer.calls)


def test_duplicate_citation_saves_one_evidence_row(db_client, seeded_db, monkeypatch):
    with seeded_db.begin() as connection:
        seed_documents(connection)
        chunk = connection.execute(text("""
            SELECT ch.id FROM document_chunks ch JOIN documents d ON d.id=ch.document_id
            WHERE d.title='겨울방학 안내' AND ch.location='1쪽 겨울방학 기간'
        """)).mappings().one()
    setup_graph(seeded_db, monkeypatch, {"text": "겨울방학은 12월 24일부터예요.",
        "evidence": [{"chunk_id": chunk["id"], "quote": "12월 24일"},
                     {"chunk_id": chunk["id"], "quote": "12월 24일"}], "no_evidence": False, "conflict": False})
    card, evidence, _ = create_card(db_client, "겨울방학 언제부터인가요?")
    assert card["draft"]["text"] == "겨울방학은 12월 24일부터예요."  # 실행 전체가 롤백되지 않는다
    assert len(evidence) == 1


def teacher_headers():
    return {"Authorization": "Bearer " + issue_token(users.get_user(seed.TEACHER))}


def assert_empty_draft_card(db_client, card):
    """근거 없음·충돌 카드는 초안이 비어 있고, 일반 승인은 막히고, 직접 쓴 글만 발송된다."""
    assert card["draft"]["text"] == ""
    assert [issue["field"] for issue in card["check_result"]["issues"]] == ["출처"]
    url = f"/api/v1/cards/{card['id']}/decisions"
    blocked = db_client.post(url, headers=teacher_headers(), json={"version": card["version"], "decision": "approve"})
    assert blocked.status_code == 409, blocked.text
    sent = db_client.post(url, headers=teacher_headers(), json={
        "version": card["version"], "decision": "edit_approve",
        "edited_content": {"text": "선생님이 직접 확인해서 안내드려요."}})
    assert sent.status_code == 200, sent.text
    with transaction() as connection:
        bodies = connection.scalars(text("SELECT body FROM request_messages WHERE request_id=:id ORDER BY created_at,id"),
                                    {"id": card["request_id"]}).all()
    assert bodies[-1] == "선생님이 직접 확인해서 안내드려요."
    assert not any("자료에서 확인되지 않아" in body for body in bodies)


def test_no_evidence_still_goes_to_teacher(db_client, seeded_db, monkeypatch):
    setup_graph(seeded_db, monkeypatch, {"text": "추측", "evidence": [], "no_evidence": True, "conflict": False})
    card, evidence, messages = create_card(db_client, "겨울방학 방과후 운영하나요?")
    assert card["assignee_id"] == seed.TEACHER and card["draft"]["no_evidence"] and not evidence
    assert messages == 1
    assert_empty_draft_card(db_client, card)


def test_conflict_card_has_no_draft_text(db_client, seeded_db, monkeypatch):
    with seeded_db.begin() as connection:
        seed_documents(connection)
        chunk = connection.execute(text("""
            SELECT ch.id FROM document_chunks ch JOIN documents d ON d.id=ch.document_id
            WHERE d.title='겨울방학 안내' AND ch.location='1쪽 겨울방학 기간'
        """)).mappings().one()
    setup_graph(seeded_db, monkeypatch, {"text": "12월 24일 또는 26일", "no_evidence": False, "conflict": True,
        "evidence": [{"chunk_id": chunk["id"], "quote": "12월 24일"}]})
    card, _, messages = create_card(db_client, "겨울방학 언제부터인가요?")
    assert card["draft"]["conflict"] and messages == 1
    assert_empty_draft_card(db_client, card)


def test_model_error_still_creates_card(db_client, seeded_db, monkeypatch):
    setup_graph(seeded_db, monkeypatch, ModelError("모델 오류"))
    card, evidence, messages = create_card(db_client, "겨울방학 언제부터인가요?")
    assert card["assignee_id"] == seed.TEACHER and card["draft"]["no_evidence"] and not evidence
    assert messages == 1
    assert card["check_result"]["passed"] is False
    assert card["draft"]["text"] == ""
    assert card["check_result"]["issues"]


def test_hybrid_score_uses_matching_vector(seeded_db, monkeypatch):
    from types import SimpleNamespace
    with seeded_db.begin() as connection:
        seed_documents(connection)
    monkeypatch.setattr(embedding, "enabled", lambda: True)
    monkeypatch.setattr(embedding, "embed", lambda texts: [[1.0] + [0.0] * 1023])
    with seeded_db.begin() as connection:
        connection.execute(text("""
            UPDATE document_chunks SET embedding=CAST(:vector AS vector), embedding_version=:version
            WHERE id=(SELECT ch.id FROM document_chunks ch JOIN documents d ON d.id=ch.document_id
                      WHERE d.title='겨울방학 안내' AND ch.location='1쪽 겨울방학 기간' LIMIT 1)
        """), {"vector": "[" + ",".join(["1"] + ["0"] * 1023) + "]", "version": embedding.VERSION})
    user = SimpleNamespace(id=seed.PARENT, org_id=seed.ORG, role="parent")
    result = search_documents(user, str(seed.ORG), "notice", "겨울방학", classroom_id=seed.CLASS_STAR)["chunks"]
    assert result and result[0]["score"] > 0.5
