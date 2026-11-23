"""자료 AI 문의 카드와 벡터 검색을 실제 DB에서 확인한다."""

from uuid import uuid4

from sqlalchemy import text

from agents.llm import ModelError
from app.core.db import transaction
from app.mock import seed
from app.modules.documents import embedding
from app.modules.documents.search import search_documents
from db.seeds.documents import seed_documents


class Writer:
    answer = None

    def __init__(self, role):
        pass

    def json(self, system, user):
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def setup_graph(seeded_db, monkeypatch, answer):
    with seeded_db.begin() as connection:
        seed_documents(connection)
    monkeypatch.setenv("ANSWER_WRITER", "graph")
    from agents.graphs import answer as graph
    Writer.answer = answer
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
    return card, evidence


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
    card, evidence = create_card(db_client, "겨울방학 언제부터인가요?")
    assert card["assignee_id"] == seed.TEACHER
    assert card["draft"]["text"] == "겨울방학은 12월 24일부터예요."
    assert not card["draft"]["no_evidence"]
    assert evidence[0]["location"] == "1쪽 겨울방학 기간"
    assert evidence[0]["score"] is not None


def test_no_evidence_still_goes_to_teacher(db_client, seeded_db, monkeypatch):
    setup_graph(seeded_db, monkeypatch, {"text": "추측", "evidence": [], "no_evidence": True, "conflict": False})
    card, evidence = create_card(db_client, "겨울방학 방과후 운영하나요?")
    assert card["assignee_id"] == seed.TEACHER and card["draft"]["no_evidence"] and not evidence


def test_model_error_still_creates_card(db_client, seeded_db, monkeypatch):
    setup_graph(seeded_db, monkeypatch, ModelError("모델 오류"))
    card, evidence = create_card(db_client, "겨울방학 언제부터인가요?")
    assert card["assignee_id"] == seed.TEACHER and card["draft"]["no_evidence"] and not evidence


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
    user = SimpleNamespace(org_id=seed.ORG, role="parent")
    result = search_documents(user, str(seed.ORG), "notice", "겨울방학", classroom_id=seed.CLASS_STAR)["chunks"]
    assert result and result[0]["score"] > 0.5
