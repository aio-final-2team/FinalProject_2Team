"""T52: 민원 답변에 법령 근거, 행사 문의에 예보가 붙는지 실제 DB로 확인한다."""

from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import text

from app.core.db import transaction
from app.core.schedule import KST
from app.mock import seed
from app.modules.documents import public_sources
from app.modules.requests import agent_stub
from tools.public_apis.common import upstream
from tests.integration.db.test_answer_t33 import Writer, create_card, setup_graph

LAW_TEXT = "학교의 장은 감염병에 걸렸거나 걸릴 우려가 있는 학생에게 등교 중지를 명할 수 있다."


class FakeLaw:
    fail = False
    calls = 0

    def get_article(self, law_name, article):
        FakeLaw.calls += 1
        if FakeLaw.fail:
            raise upstream("법령 API 점검 중")
        return {"text": f"{law_name} {article}\n{LAW_TEXT}", "source_url": "https://www.law.go.kr/test",
                "fetched_at": "2026-11-23T10:00:00+09:00"}


class FakeWeather:
    def get_daily_forecast(self, day=None, **_):
        return {"date": day.isoformat(), "temp_min": 3.0, "temp_max": 11.0, "pop_max": 60,
                "precipitation": [{"time": "1500", "type": "비"}],
                "source_url": "https://apis.data.go.kr/test", "fetched_at": "2026-11-23T10:00:00+09:00"}


def complaint(connection, topic, monkeypatch):
    monkeypatch.setattr(agent_stub, "classify_request", lambda *_: {"topic_key": topic})
    FakeLaw.fail, FakeLaw.calls = False, 0
    monkeypatch.setattr("tools.public_apis.law.LawClient", FakeLaw)
    return connection.scalar(text("""
        INSERT INTO requests (org_id,classroom_id,child_id,requester_id,client_request_id,type,body,title)
        VALUES (:org,:class,:child,:parent,:key,'complaint','[TEST] 민원','[TEST] 민원') RETURNING id
    """), {"org": seed.ORG, "class": seed.CLASS_STAR, "child": seed.CHILD, "parent": seed.PARENT,
           "key": str(uuid4())})


def run(seeded_db, topic, monkeypatch, fail=False):
    with seeded_db.begin() as connection:
        request_id = complaint(connection, topic, monkeypatch)
    FakeLaw.fail = fail
    agent_stub.run_request(request_id)
    with seeded_db.begin() as connection:
        card = connection.execute(text("SELECT * FROM cards WHERE request_id=:id AND kind='reply_draft'"),
                                  {"id": request_id}).mappings().one()
        evidence = connection.execute(text("""
            SELECT d.title, ch.location, e.quote, e.rank FROM card_evidence e
            JOIN document_chunks ch ON ch.id=e.chunk_id JOIN documents d ON d.id=ch.document_id
            WHERE e.card_id=:id ORDER BY e.rank
        """), {"id": card["id"]}).mappings().all()
        status = connection.scalar(text("SELECT status FROM requests WHERE id=:id"), {"id": request_id})
    return card, evidence, status


def warnings(db_client, card):
    from app.core.auth import issue_token
    from app.core import users
    headers = {"Authorization": "Bearer " + issue_token(users.get_user(seed.TEACHER))}
    response = db_client.get(f"/api/v1/cards/{card['id']}", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    return body, body.get("warnings", body.get("card", {}).get("warnings", []))


def test_health_complaint_gets_law_evidence(db_client, seeded_db, monkeypatch):
    card, evidence, status = run(seeded_db, "health_hygiene", monkeypatch)
    assert [e["title"] for e in evidence] == ["학교보건법 제8조"]
    assert evidence[0]["location"] == "제8조" and LAW_TEXT in evidence[0]["quote"]
    assert "law_unchecked" not in card["draft"] and status == "awaiting_review"
    body, found = warnings(db_client, card)
    assert "학교보건법 제8조" in str(body) and "law_unchecked" not in found


def test_law_failure_still_creates_card_with_warning(db_client, seeded_db, monkeypatch):
    card, evidence, status = run(seeded_db, "health_hygiene", monkeypatch, fail=True)
    assert not evidence and card["draft"]["law_unchecked"] is True
    assert status == "awaiting_review"
    _, found = warnings(db_client, card)
    assert "law_unchecked" in found


def test_unlisted_topic_has_no_law_evidence(db_client, seeded_db, monkeypatch):
    card, evidence, _ = run(seeded_db, "fee", monkeypatch)
    assert not evidence and "law_unchecked" not in card["draft"]
    assert FakeLaw.calls == 0
    _, found = warnings(db_client, card)
    assert "law_unchecked" not in found


def test_same_law_stored_once(seeded_db, monkeypatch):
    monkeypatch.setattr("tools.public_apis.law.LawClient", FakeLaw)
    with seeded_db.begin() as connection:
        first = public_sources.law_evidence(connection, seed.ORG, "health_hygiene")
        second = public_sources.law_evidence(connection, seed.ORG, "health_hygiene")
        assert first["chunk_id"] == second["chunk_id"]
        row = connection.execute(text("""
            SELECT count(*) AS n, min(source) AS source, bool_and(visibility='all') AS visible,
                   min(doc_type) AS doc_type, bool_and(api_called_at IS NOT NULL) AS called
            FROM documents WHERE title='학교보건법 제8조'
        """)).mappings().one()
        assert (row["n"], row["source"], row["doc_type"]) == (1, "public_api", "law")
        assert row["visible"] and row["called"]
        assert connection.scalar(text("SELECT count(*) FROM document_chunks WHERE id=:id"), {"id": first["chunk_id"]}) == 1


def test_event_inquiry_cites_forecast(db_client, seeded_db, monkeypatch):
    setup_graph(seeded_db, monkeypatch, None)
    monkeypatch.setattr(public_sources, "WeatherClient", FakeWeather)
    tomorrow = datetime.now(KST).date() + timedelta(days=1)
    line = f"{tomorrow.month}월 {tomorrow.day}일 예보: 최저 3도·최고 11도, 강수확률 최대 60%, 비 15시"
    chunk_quote = "강수확률 최대 60%"

    class ForecastWriter(Writer):
        def json(self, system, user):
            import json
            self.calls.append((self.role, user))
            if self.role == "CHECKER":
                return {"passed": True, "issues": []}
            chunk = next(c for c in json.loads(user)["chunks"] if "예보" in c["content"])
            assert chunk["score"] == 1.0
            return {"text": "내일은 비가 올 수 있다는 예보예요.", "no_evidence": False, "conflict": False,
                    "evidence": [{"chunk_id": chunk["chunk_id"], "quote": chunk_quote}]}

    from agents.graphs import answer as graph
    monkeypatch.setattr(graph, "OpenAIModel", ForecastWriter)
    card, evidence, _ = create_card(db_client, "내일 현장체험 때 비 오나요?")
    assert [e["quote"] for e in evidence] == [chunk_quote]
    assert evidence[0]["location"] == str(tomorrow)
    with transaction() as connection:
        doc = connection.execute(text("SELECT doc_type, source, effective_to FROM documents WHERE title=:t"),
                                 {"t": f"기상청 단기예보 {tomorrow}"}).mappings().one()
        assert (doc["doc_type"], doc["source"], doc["effective_to"]) == ("public_data", "public_api", tomorrow)
        assert connection.scalar(text("SELECT content FROM document_chunks ch JOIN documents d ON d.id=ch.document_id "
                                      "WHERE d.title=:t"), {"t": f"기상청 단기예보 {tomorrow}"}) == line


def test_forecast_failure_does_not_block_answer(db_client, seeded_db, monkeypatch):
    setup_graph(seeded_db, monkeypatch, {"text": "x", "evidence": [], "no_evidence": True, "conflict": False})
    card, evidence, messages = create_card(db_client, "내일 현장체험 때 비 오나요?")  # 키가 없어 예보 실패
    assert card["draft"]["no_evidence"] and not evidence
