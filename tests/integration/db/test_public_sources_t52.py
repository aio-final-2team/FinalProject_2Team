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

INFECTION = "[TEST] 아이가 수족구에 걸렸는데 등원해도 되나요"
LAW_TEXT = "학교의 장은 감염병에 걸렸거나 걸릴 우려가 있는 학생에게 등교 중지를 명할 수 있다."


def held_connections():
    """지금 풀에서 빌려 간 DB 연결 수. 공공 API를 부를 때 0이어야 한다(연결·잠금을 잡고 기다리지 않음)."""
    from app.core.db import get_engine
    return get_engine().pool.checkedout()


class FakeLaw:
    fail = False
    calls = 0
    held = []

    def get_article(self, law_name, article):
        FakeLaw.calls += 1
        FakeLaw.held.append(held_connections())
        if FakeLaw.fail:
            raise upstream("법령 API 점검 중")
        return {"text": f"{law_name} {article}\n{LAW_TEXT}", "source_url": "https://www.law.go.kr/test",
                "fetched_at": "2026-11-23T10:00:00+09:00"}


class FakeWeather:
    calls = 0
    held = []
    fail = False

    def get_daily_forecast(self, day=None, **_):
        FakeWeather.calls += 1
        FakeWeather.held.append(held_connections())
        if FakeWeather.fail:
            raise upstream("예보 API 점검 중")
        return {"date": day.isoformat(), "temp_min": 3.0, "temp_max": 11.0, "pop_max": 60,
                "precipitation": [{"time": "1500", "type": "비"}],
                "source_url": "https://apis.data.go.kr/test", "fetched_at": "2026-11-23T10:00:00+09:00"}


def complaint(connection, topic, monkeypatch, body="[TEST] 민원"):
    monkeypatch.setattr(agent_stub, "classify_request", lambda *_: {"topic_key": topic})
    FakeLaw.fail, FakeLaw.calls, FakeLaw.held = False, 0, []
    monkeypatch.setattr("tools.public_apis.law.LawClient", FakeLaw)
    return connection.scalar(text("""
        INSERT INTO requests (org_id,classroom_id,child_id,requester_id,client_request_id,type,body,title)
        VALUES (:org,:class,:child,:parent,:key,'complaint',:body,:body) RETURNING id
    """), {"org": seed.ORG, "class": seed.CLASS_STAR, "child": seed.CHILD, "parent": seed.PARENT,
           "key": str(uuid4()), "body": body})


def run(seeded_db, topic, monkeypatch, fail=False, body="[TEST] 민원"):
    with seeded_db.begin() as connection:
        request_id = complaint(connection, topic, monkeypatch, body)
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
    run.request_id = request_id
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
    card, evidence, status = run(seeded_db, "health_hygiene", monkeypatch, body=INFECTION)
    assert [e["title"] for e in evidence] == ["학교보건법 제8조"]
    assert evidence[0]["location"] == "제8조" and LAW_TEXT in evidence[0]["quote"]
    assert "law_unchecked" not in card["draft"] and status == "awaiting_review"
    body, found = warnings(db_client, card)
    assert "학교보건법 제8조" in str(body) and "law_unchecked" not in found


def test_teacher_tone_complaint_gets_no_law(db_client, seeded_db, monkeypatch):
    card, evidence, _ = run(seeded_db, "teacher", monkeypatch, body="선생님 말투가 너무 차가워요")
    assert not evidence and "law_unchecked" not in card["draft"] and FakeLaw.calls == 0


def test_medication_mistake_complaint_gets_no_infection_law(db_client, seeded_db, monkeypatch):
    card, evidence, _ = run(seeded_db, "health_hygiene", monkeypatch, body="약을 잘못 먹였어요. 투약 실수 같아요")
    assert not evidence and FakeLaw.calls == 0


def test_child_safety_complaint_gets_child_welfare_law(db_client, seeded_db, monkeypatch):
    _, evidence, _ = run(seeded_db, "teacher", monkeypatch, body="선생님이 아이를 때렸다고 해요")
    assert [e["title"] for e in evidence] == ["아동복지법 제17조"]


def approve_and_read_sources(db_client, seeded_db, card, text_for_parent=None):
    from tests.integration.db.test_cards import BASE, auth
    decision = {"version": card["version"], "decision": "approve"}
    if text_for_parent:
        decision |= {"decision": "edit_approve", "edited_content": {"text": text_for_parent}}
    response = db_client.post(f"{BASE}/cards/{card['id']}/decisions", headers=auth(seed.TEACHER), json=decision)
    assert response.status_code == 200, response.text
    response = db_client.get(f"{BASE}/requests/{run.request_id}", headers=auth(seed.PARENT))
    assert response.status_code == 200, response.text
    return [row["document_title"] for row in response.json()["data"]["sources"]] \
        if "data" in response.json() else [row["document_title"] for row in response.json()["sources"]]


def test_parent_sources_hide_law_the_teacher_did_not_use(db_client, seeded_db, monkeypatch):
    card, evidence, _ = run(seeded_db, "health_hygiene", monkeypatch, body=INFECTION)
    assert [e["title"] for e in evidence] == ["학교보건법 제8조"]  # 담임 카드에는 보인다
    assert approve_and_read_sources(db_client, seeded_db, card) == []


def test_parent_sources_show_law_the_teacher_cited(db_client, seeded_db, monkeypatch):
    card, _, _ = run(seeded_db, "health_hygiene", monkeypatch, body=INFECTION)
    sources = approve_and_read_sources(db_client, seeded_db, card, "학교보건법 제8조에 따라 등원을 쉬어 주세요.")
    assert sources == ["학교보건법 제8조"]


def test_law_failure_still_creates_card_with_warning(db_client, seeded_db, monkeypatch):
    card, evidence, status = run(seeded_db, "health_hygiene", monkeypatch, fail=True, body=INFECTION)
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
        first = public_sources.law_evidence(connection, seed.ORG, "infection")
        second = public_sources.law_evidence(connection, seed.ORG, "infection")
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


def inquiry(connection, body):
    return connection.scalar(text("""
        INSERT INTO requests (org_id,classroom_id,child_id,requester_id,client_request_id,type,body,title)
        VALUES (:org,:class,:child,:parent,:key,'inquiry',:body,:body) RETURNING id
    """), {"org": seed.ORG, "class": seed.CLASS_STAR, "child": seed.CHILD, "parent": seed.PARENT,
           "key": str(uuid4()), "body": body})


def test_law_api_called_without_holding_db_connection(db_client, seeded_db, monkeypatch):
    """법령 호출(최대 10초)이 카드 저장 트랜잭션·연결·잠금 밖에서 일어나고, 한 번만 부른다."""
    card, evidence, _ = run(seeded_db, "health_hygiene", monkeypatch, body=INFECTION)
    assert evidence and FakeLaw.calls == 1 and FakeLaw.held == [0]


def test_law_failure_is_fetched_once_outside_transaction(db_client, seeded_db, monkeypatch):
    card, evidence, _ = run(seeded_db, "health_hygiene", monkeypatch, fail=True, body=INFECTION)
    assert not evidence and card["draft"]["law_unchecked"] is True
    assert FakeLaw.calls == 1 and FakeLaw.held == [0]  # 실패해도 트랜잭션 안에서 다시 부르지 않음


def forecast_run(seeded_db, monkeypatch, fail):
    setup_graph(seeded_db, monkeypatch, None)
    monkeypatch.setattr(public_sources, "WeatherClient", FakeWeather)
    FakeWeather.calls, FakeWeather.held, FakeWeather.fail = 0, [], fail
    with seeded_db.begin() as connection:
        request_id = inquiry(connection, "내일 현장체험 때 비 오나요?")
    agent_stub.run_request(request_id)
    return request_id


def test_forecast_api_called_without_holding_db_connection(db_client, seeded_db, monkeypatch):
    from agents.graphs import answer as graph
    import json

    class ForecastWriter(Writer):
        def json(self, system, user):
            if self.role == "CHECKER":
                return {"passed": True, "issues": []}
            chunk = next(c for c in json.loads(user)["chunks"] if "예보" in c["content"])
            return {"text": "비 예보가 있어요.", "no_evidence": False, "conflict": False,
                    "evidence": [{"chunk_id": chunk["chunk_id"], "quote": "강수확률 최대 60%"}]}

    setup_graph(seeded_db, monkeypatch, None)
    monkeypatch.setattr(graph, "OpenAIModel", ForecastWriter)
    monkeypatch.setattr(public_sources, "WeatherClient", FakeWeather)
    FakeWeather.calls, FakeWeather.held, FakeWeather.fail = 0, [], False
    with seeded_db.begin() as connection:
        request_id = inquiry(connection, "내일 현장체험 때 비 오나요?")
    agent_stub.run_request(request_id)
    assert FakeWeather.calls == 1 and FakeWeather.held == [0]
    with seeded_db.begin() as connection:
        quotes = connection.scalars(text("""
            SELECT e.quote FROM card_evidence e JOIN cards c ON c.id=e.card_id WHERE c.request_id=:id
        """), {"id": request_id}).all()
    assert quotes == ["강수확률 최대 60%"]


def test_forecast_failure_is_fetched_once_and_card_still_made(db_client, seeded_db, monkeypatch):
    request_id = forecast_run(seeded_db, monkeypatch, fail=True)
    assert FakeWeather.calls == 1 and FakeWeather.held == [0]
    with seeded_db.begin() as connection:
        draft = connection.scalar(text("SELECT draft FROM cards WHERE request_id=:id AND kind='reply_draft'"),
                                  {"id": request_id})
        stored = connection.scalar(text("SELECT count(*) FROM documents WHERE title LIKE '기상청 단기예보%'"))
    assert draft["no_evidence"] is True and stored == 0


def attach_law_document(seeded_db, card, title, source):
    """카드 근거에 법령 자료 한 건을 더 붙인다(업로드 자료나 제목이 이상한 공공 법령을 흉내)."""
    with seeded_db.begin() as connection:
        doc = connection.scalar(text("""
            INSERT INTO documents (org_id,title,doc_type,visibility,source,status,ingest_status,content_sha256,is_virtual)
            VALUES (:org,:title,'law','all',:source,'active','succeeded',:sha,false) RETURNING id
        """), {"org": seed.ORG, "title": title, "source": source, "sha": uuid4().hex})
        chunk = connection.scalar(text("""
            INSERT INTO document_chunks (document_id,org_id,chunk_index,location,content)
            VALUES (:doc,:org,0,'1쪽','요약') RETURNING id
        """), {"doc": doc, "org": seed.ORG})
        connection.execute(text("""
            INSERT INTO card_evidence (card_id,org_id,chunk_id,quote,rank,score)
            VALUES (:card,:org,:chunk,'요약',9,1)
        """), {"card": card["id"], "org": seed.ORG, "chunk": chunk})


def test_parent_sources_show_uploaded_law_even_if_title_not_in_text(db_client, seeded_db, monkeypatch):
    card, _, _ = run(seeded_db, "health_hygiene", monkeypatch, body=INFECTION)
    attach_law_document(seeded_db, card, "학교안전법_요약.pdf", "uploaded")
    assert approve_and_read_sources(db_client, seeded_db, card) == ["학교안전법_요약.pdf"]  # 공공 법령은 빠지고 업로드는 남음


def test_parent_sources_public_law_needs_name_in_text(db_client, seeded_db, monkeypatch):
    card, _, _ = run(seeded_db, "health_hygiene", monkeypatch, body=INFECTION)
    attach_law_document(seeded_db, card, "아동복지법 제17조", "public_api")
    sources = approve_and_read_sources(db_client, seeded_db, card, "아동복지법 제17조를 확인했어요.")
    assert sources == ["아동복지법 제17조"]


def test_parent_sources_hide_public_law_with_empty_first_word(db_client, seeded_db, monkeypatch):
    card, _, _ = run(seeded_db, "health_hygiene", monkeypatch, body=INFECTION)
    attach_law_document(seeded_db, card, " 공백으로 시작", "public_api")  # 첫 낱말이 빈 문자열이면 항상 맞던 문제
    assert approve_and_read_sources(db_client, seeded_db, card) == []
