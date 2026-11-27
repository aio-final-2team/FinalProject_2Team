"""민원 일반의 자료·검사 인계와 고위험 우회를 실제 DB에서 확인한다."""

from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.mock import seed
from app.modules.requests import runner
from db.seeds.documents import seed_documents
from tests import fake_supervisor

BODY = "[TEST] 원비 환불 안내가 부족해요"


class FakeModel:
    chunk_id = None
    checker_results = []
    calls = []
    no_evidence = False

    def __init__(self, role):
        self.role = role

    def json(self, system, user):
        self.calls.append(self.role)
        if self.role == "CHECKER":
            return self.checker_results.pop(0) if self.checker_results else {"passed": True, "issues": []}
        return {"text": "[TEST] 행정실 안내를 확인해 주세요.",
                "evidence": [] if self.no_evidence else [{"chunk_id": self.chunk_id, "quote": "행정실에서 안내합니다"}],
                "no_evidence": self.no_evidence, "conflict": False}


def setup(seeded_db, monkeypatch, *, enabled=True, no_evidence=False, checker_results=None):
    with seeded_db.begin() as connection:
        seed_documents(connection)
        FakeModel.chunk_id = connection.scalar(text("""
            SELECT ch.id FROM document_chunks ch JOIN documents d ON d.id=ch.document_id
            WHERE d.title='운영 규정 — 원비 및 납부' AND ch.content LIKE '%행정실에서 안내합니다%' LIMIT 1
        """))
    assert FakeModel.chunk_id is not None
    FakeModel.calls = []
    FakeModel.no_evidence = no_evidence
    FakeModel.checker_results = list(checker_results or [])
    from agents.graphs import answer
    monkeypatch.setattr(answer, "OpenAIModel", FakeModel)
    monkeypatch.setattr(runner, "settings", replace(runner.settings,
        request_agent="app.modules.requests.graph_agent:run_request"))
    if enabled:
        monkeypatch.setenv("REQUEST_COLLAB_GRAPH", "1")
    else:
        monkeypatch.delenv("REQUEST_COLLAB_GRAPH", raising=False)


def submit(db_client, seeded_db, body=BODY):
    login = db_client.post("/api/v1/auth/login", json={"login_id": "parent01", "password": "demo1234"})
    headers = {"Authorization": "Bearer " + login.json()["access_token"]}
    response = db_client.post("/api/v1/requests", headers=headers, json={
        "client_request_id": str(uuid4()), "type": "complaint", "body": body,
        "child_id": str(seed.CHILD)})
    assert response.status_code == 202, response.text
    request_id = response.json()["request"]["id"]
    with seeded_db.connect() as connection:
        cards = connection.execute(text("SELECT * FROM cards WHERE request_id=:id ORDER BY kind,id"),
                                   {"id": request_id}).mappings().all()
        status = connection.scalar(text("SELECT status FROM requests WHERE id=:id"), {"id": request_id})
        evidence = connection.scalars(text("""
            SELECT chunk_id FROM card_evidence WHERE card_id=:card ORDER BY rank
        """), {"card": next(c["id"] for c in cards if c["kind"] == "reply_draft")}).all()
    return cards, status, evidence


def test_normal_complaint_uses_writer_checker_and_evidence(db_client, seeded_db, monkeypatch):
    setup(seeded_db, monkeypatch)
    cards, status, evidence = submit(db_client, seeded_db)
    assert [c["kind"] for c in cards] == ["reply_draft"]
    assert status == "awaiting_review"
    assert cards[0]["draft"]["text"] == "[TEST] 행정실 안내를 확인해 주세요."
    assert evidence == [FakeModel.chunk_id]
    assert FakeModel.calls == ["DOCUMENT", "CHECKER"]


def test_normal_complaint_without_evidence_hands_off(db_client, seeded_db, monkeypatch):
    setup(seeded_db, monkeypatch, no_evidence=True)
    cards, status, evidence = submit(db_client, seeded_db)
    assert status == "awaiting_review" and not evidence
    assert cards[0]["draft"]["text"] == "" and cards[0]["check_result"]["passed"] is False
    assert FakeModel.calls == ["DOCUMENT"]


def test_checker_returns_twice_then_hands_off(db_client, seeded_db, monkeypatch):
    issue = {"passed": False, "issues": [{"field": "출처", "problem": "다시 확인해 주세요."}]}
    setup(seeded_db, monkeypatch, checker_results=[issue, issue, issue])
    cards, status, _ = submit(db_client, seeded_db)
    assert status == "awaiting_review"
    assert cards[0]["draft"]["text"] == "" and cards[0]["check_result"]["attempt"] == 3
    assert FakeModel.calls == ["DOCUMENT", "CHECKER"] * 3


@pytest.mark.parametrize("body", ["[TEST] 아이가 다쳤어요. 처리해 주세요.", "[TEST] 판단 필요: 원비를 확인해 주세요."])
def test_high_risk_keeps_director_report_and_only_urgent_skips_model(db_client, seeded_db, monkeypatch, body):
    setup(seeded_db, monkeypatch)
    fake_supervisor.install(monkeypatch)  # 판단 필요는 가짜 감독 AI가 정해요
    uncertain = fake_supervisor.MARK in body
    cards, status, _ = submit(db_client, seeded_db, body)
    assert status == "escalated" and {c["kind"] for c in cards} == {"reply_draft", "director_report"}
    reply = next(c for c in cards if c["kind"] == "reply_draft")
    # 긴급은 자료·검사 AI를 건너뛰어요. 판단 필요는 초안을 써 두고 이유 한 줄을 남겨요(승인은 재분류 전까지 막혀요).
    assert bool(reply["draft"].get("text")) == uncertain
    assert FakeModel.calls == (["DOCUMENT", "CHECKER"] if uncertain else [])
    assert all(c["draft"].get("risk_reason") == (fake_supervisor.REASON if uncertain else None) for c in cards)


def test_old_and_new_complaint_keep_card_kind_and_status(db_client, seeded_db, monkeypatch):
    setup(seeded_db, monkeypatch, enabled=False)
    old_cards, old_status, _ = submit(db_client, seeded_db)
    setup(seeded_db, monkeypatch, enabled=True)
    new_cards, new_status, _ = submit(db_client, seeded_db)
    assert old_status == new_status
    assert [c["kind"] for c in old_cards] == [c["kind"] for c in new_cards]
