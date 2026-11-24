"""#325 리뷰: 위험 우회, 예보 한 번, 담임 선택 조건을 확인한다."""

from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.mock import seed
from app.modules.requests import graph_agent, runner
from db.seeds.documents import seed_documents
from tests.integration.db.test_public_sources_t52 import FakeWeather


def enable(monkeypatch):
    monkeypatch.setenv("REQUEST_COLLAB_GRAPH", "1")
    monkeypatch.delenv("LLM_MODEL_SUPERVISOR", raising=False)
    monkeypatch.setattr(runner, "settings", replace(runner.settings,
        request_agent="app.modules.requests.graph_agent:run_request"))


def post_request(db_client, request_type, body):
    login = db_client.post("/api/v1/auth/login", json={"login_id": "parent01", "password": "demo1234"})
    headers = {"Authorization": "Bearer " + login.json()["access_token"]}
    response = db_client.post("/api/v1/requests", headers=headers, json={
        "client_request_id": str(uuid4()), "type": request_type, "body": body,
        "child_id": str(seed.CHILD)})
    assert response.status_code == 202, response.text
    return response.json()["request"]["id"]


@pytest.mark.parametrize("request_type", ["inquiry", "complaint"])
def test_risk_goes_to_two_cards_without_send(db_client, seeded_db, monkeypatch, request_type):
    enable(monkeypatch)
    seen = []
    monkeypatch.setattr(graph_agent, "_search_request", lambda _: seen.append("search"))
    monkeypatch.setattr(graph_agent, "_load_request_memory", lambda _: seen.append("memory"))
    from agents.graphs import answer
    monkeypatch.setattr(answer, "OpenAIModel", lambda role: seen.append(role))
    from app.modules.documents import public_sources
    monkeypatch.setattr(public_sources, "fetch_law", lambda _: {"unchecked": True})
    request_id = post_request(db_client, request_type, "[TEST] 아이가 다쳤어요. 확인해 주세요.")
    with seeded_db.connect() as connection:
        cards = connection.execute(text("SELECT kind,draft FROM cards WHERE request_id=:id"),
                                   {"id": request_id}).mappings().all()
    assert {card["kind"] for card in cards} == {"reply_draft", "director_report"}
    assert not next(card for card in cards if card["kind"] == "reply_draft")["draft"].get("text")
    assert seen == []


class ForecastModel:
    calls = []

    def __init__(self, role):
        self.role = role

    def json(self, system, user):
        import json
        self.calls.append(self.role)
        payload = json.loads(user)
        if self.role == "CHECKER":
            return {"passed": True, "issues": []}
        forecast = next(chunk for chunk in payload["chunks"]
                        if chunk["document_title"].startswith("기상청 단기예보"))
        return {"text": "[TEST] 예보를 확인해 주세요.",
                "evidence": [{"chunk_id": forecast["chunk_id"], "quote": forecast["content"][:20]}],
                "no_evidence": False, "conflict": False}


def test_forecast_is_cited_and_fetched_once(db_client, seeded_db, monkeypatch):
    enable(monkeypatch)
    monkeypatch.setenv("ANSWER_WRITER", "graph")
    with seeded_db.begin() as connection:
        seed_documents(connection)
    from app.modules.documents import public_sources
    from agents.graphs import answer
    FakeWeather.calls, FakeWeather.held, FakeWeather.fail = 0, [], False
    ForecastModel.calls = []
    monkeypatch.setattr(public_sources, "WeatherClient", FakeWeather)
    monkeypatch.setattr(answer, "OpenAIModel", ForecastModel)
    request_id = post_request(db_client, "inquiry", "[TEST] 내일 비 오면 바깥 놀이 하나요?")
    with seeded_db.connect() as connection:
        card = connection.execute(text("SELECT * FROM cards WHERE request_id=:id"),
                                  {"id": request_id}).mappings().one()
        titles = connection.scalars(text("""
            SELECT d.title FROM card_evidence e JOIN document_chunks ch ON ch.id=e.chunk_id
            JOIN documents d ON d.id=ch.document_id WHERE e.card_id=:card
        """), {"card": card["id"]}).all()
    assert card["draft"]["text"] == "[TEST] 예보를 확인해 주세요."
    assert any(title.startswith("기상청 단기예보") for title in titles)
    assert FakeWeather.calls == 1 and ForecastModel.calls == ["DOCUMENT", "CHECKER"]


def test_memory_failure_keeps_inquiry_draft(db_client, seeded_db, monkeypatch):
    from tests.integration.db.test_request_lock_timeout import use_model

    enable(monkeypatch)
    use_model(seeded_db, monkeypatch, lambda _: None)

    def broken(_):
        raise RuntimeError("[TEST] 기억 읽기 실패")

    monkeypatch.setattr(graph_agent, "_load_request_memory", broken)
    request_id = post_request(db_client, "inquiry", "[TEST] 겨울방학 언제부터인가요?")
    with seeded_db.connect() as connection:
        card = connection.execute(text("SELECT * FROM cards WHERE request_id=:id"),
                                  {"id": request_id}).mappings().one()
    assert card["draft"]["text"] == "[TEST] 자료 확인 답"
    assert card["check_result"]["memory_unavailable"] is True


def test_context_excludes_inactive_and_out_of_period_teacher(seeded_db):
    with seeded_db.begin() as connection:
        request_id = connection.scalar(text("""
            INSERT INTO requests(org_id,classroom_id,child_id,requester_id,client_request_id,type,body,title)
            VALUES (:org,:class,:child,:parent,:key,'inquiry','[TEST] 담임','[TEST] 담임') RETURNING id
        """), {"org": seed.ORG, "class": seed.CLASS_STAR, "child": seed.CHILD,
               "parent": seed.PARENT, "key": str(uuid4())})
        connection.execute(text("UPDATE classroom_staff SET valid_to=CURRENT_DATE-1 WHERE user_id=:teacher"),
                           {"teacher": seed.TEACHER})
        connection.execute(text("""
            INSERT INTO classroom_staff(org_id,classroom_id,user_id,is_homeroom,valid_from)
            VALUES (:org,:class,:other,true,CURRENT_DATE+1)
            ON CONFLICT (classroom_id,user_id) DO UPDATE SET valid_from=CURRENT_DATE+1,is_homeroom=true
        """), {"org": seed.ORG, "class": seed.CLASS_STAR, "other": seed.TEACHER_OTHER})
    assert graph_agent._request_context(request_id)["teacher_id"] is None
    with seeded_db.begin() as connection:
        connection.execute(text("UPDATE classroom_staff SET valid_from=CURRENT_DATE WHERE user_id=:other"),
                           {"other": seed.TEACHER_OTHER})
        connection.execute(text("UPDATE users SET is_active=false WHERE id=:other"),
                           {"other": seed.TEACHER_OTHER})
    assert graph_agent._request_context(request_id)["teacher_id"] is None
