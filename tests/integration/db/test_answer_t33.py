"""자료 AI 문의 카드와 벡터 검색을 실제 DB에서 확인한다."""

from uuid import uuid4

import pytest
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
    monkeypatch.setenv("ANSWER_GATHER", "fixed")  # 고정 검색과 자료·검사 두 모델 순서를 보는 시험이에요(자료 찾는 AI는 tests/unit/test_gather.py)
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


@pytest.mark.parametrize("request_type", ["inquiry", "complaint"])
@pytest.mark.parametrize("result_kind", ["passed", "failed", "handoff"])
def test_graph_card_adapter_preserves_check_and_merges_duplicate_chunks(
        db_client, seeded_db, monkeypatch, request_type, result_kind):
    from app.core.request_rules import classify
    from app.modules.requests.graph_agent import _prepare_card

    monkeypatch.setenv("ANSWER_WRITER", "graph")
    with seeded_db.begin() as connection:
        chunks = connection.scalars(text("SELECT id FROM document_chunks ORDER BY id LIMIT 2")).all()
        assert len(chunks) == 2
        request_id = connection.scalar(text("""
            INSERT INTO requests(org_id,classroom_id,child_id,requester_id,client_request_id,type,body,title)
            VALUES (:org,:class,:child,:parent,:key,:type,:body,:body) RETURNING id
        """), {"org": seed.ORG, "class": seed.CLASS_STAR, "child": seed.CHILD,
               "parent": seed.PARENT, "key": str(uuid4()), "type": request_type,
               "body": "[TEST] 준비물 안내를 확인해 주세요."})
    check = {"passed": result_kind == "passed", "attempt": 3, "memory_unavailable": True,
             "issues": [] if result_kind == "passed" else [{"field": "출처", "problem": "[TEST] 출처 확인 필요"}]}
    answer = {"text": "[TEST] 그래프 초안", "no_evidence": False, "conflict": False, "check_result": check,
              "evidence": [{"chunk_id": chunks[0], "score": 0.8, "quote": "[TEST] 첫 근거"},
                           {"chunk_id": str(chunks[0]), "score": 0.9, "quote": "[TEST] 중복 근거"},
                           {"chunk_id": chunks[1], "score": 0.7, "quote": "[TEST] 둘째 근거"}]}
    if result_kind == "handoff":
        answer.update(handoff=True, text="", evidence=[], no_evidence=True)
    card_id = _prepare_card(str(request_id), request_type, answer,
                            classify(request_type, "[TEST] 준비물 안내를 확인해 주세요."))
    with seeded_db.connect() as connection:
        card = connection.execute(text("SELECT * FROM cards WHERE id=:id"), {"id": card_id}).mappings().one()
        evidence = connection.execute(text("""
            SELECT chunk_id,rank,quote,score FROM card_evidence WHERE card_id=:id ORDER BY rank
        """), {"id": card_id}).mappings().all()
        assert connection.scalar(text("SELECT status FROM requests WHERE id=:id"),
                                 {"id": request_id}) == "awaiting_review"
    assert card["graph_thread_id"] == f"request:{request_id}"
    assert card["check_result"] == check
    assert card["draft"]["text"] == answer["text"]
    assert [dict(e) for e in evidence] == ([] if result_kind == "handoff" else [
        {"chunk_id": chunks[0], "rank": 1, "quote": "[TEST] 첫 근거", "score": 0.8},
        {"chunk_id": chunks[1], "rank": 2, "quote": "[TEST] 둘째 근거", "score": 0.7}])
    response = db_client.get(f"/api/v1/cards/{card_id}", headers=teacher_headers())
    assert response.status_code == 200, response.text
    assert response.json()["card"]["check_result"] == check


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


def test_next_day_processing_reads_today_as_the_day_asked(seeded_db, monkeypatch):
    """[TEST] 접수 다음 날 처리돼도 답변 AI의 오늘·내일은 접수한 날 기준이에요(기본 요청 처리 경로)."""
    import json
    from datetime import datetime, timedelta
    from agents.graphs.answer import day_label
    from app.core.schedule import KST
    from app.modules.requests import agent_stub
    setup_graph(seeded_db, monkeypatch, {"text": "추측", "evidence": [], "no_evidence": True, "conflict": False})
    asked = datetime.now(KST) - timedelta(days=1)
    with seeded_db.begin() as connection:
        request_id = connection.scalar(text("""
            INSERT INTO requests (org_id,classroom_id,child_id,requester_id,client_request_id,type,body,title,created_at)
            VALUES (:org,:class,:child,:parent,:key,'inquiry',:body,:body,:at) RETURNING id
        """), {"org": seed.ORG, "class": seed.CLASS_STAR, "child": seed.CHILD, "parent": seed.PARENT,
               "key": str(uuid4()), "body": "[TEST] 내일 준비물 있나요?", "at": asked})
    agent_stub.run_request(request_id)
    payloads = [json.loads(user) for role, user in Writer.calls if role != "CHECKER"]
    assert payloads and all(p.get("today") == day_label(asked.date()) for p in payloads if "today" in p)
    assert any("today" in p for p in payloads)
