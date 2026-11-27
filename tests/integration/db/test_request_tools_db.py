"""[TEST] 예보·법령을 AI가 도구로 부르는 경로, 아동 안전 선, 새 글로 다시 쓰는 초안을 실제 DB로 확인한다."""

import json
from dataclasses import replace
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import text

from agents.llm import ModelError
from app.core.schedule import KST
from app.mock import seed
from app.modules.documents import public_sources
from app.modules.requests import agent_stub, runner
from db.seeds.documents import seed_documents
from tests.integration.db.test_answer_t33 import Writer, create_card, setup_graph
from tests.integration.db.test_cards import BASE, auth
from tests.integration.db.test_public_sources_t52 import FakeLaw, FakeWeather

RAIN = "내일 현장체험 때 비 오나요?"


class Agent:
    """GATHER는 정해 둔 도구를 한 번 부르고 끝내요. DOCUMENT는 찾을 조각을 인용하고, CHECKER는 통과시켜요."""
    calls, pick, quote, gather_error, seen = [], None, "", None, []

    def __init__(self, role):
        self.role = role

    def json(self, system, user):
        payload = json.loads(user)
        Agent.seen.append((self.role, system, payload))
        if self.role == "GATHER":
            if Agent.gather_error:
                raise Agent.gather_error
            return {"calls": [] if payload["found"] else Agent.calls, "done": bool(payload["found"])}
        if self.role == "CHECKER":
            return {"passed": True, "issues": []}
        chunk = next(c for c in payload["chunks"] if Agent.pick in c["content"])
        return {"text": "[TEST] 자료로 답해요.", "no_evidence": False, "conflict": False,
                "evidence": [{"chunk_id": chunk["chunk_id"], "quote": Agent.quote}]}


def use_agent(monkeypatch, calls, pick, quote, gather_error=None):
    from agents.graphs import answer
    Agent.calls, Agent.pick, Agent.quote, Agent.gather_error, Agent.seen = calls, pick, quote, gather_error, []
    monkeypatch.setenv("ANSWER_WRITER", "graph")
    monkeypatch.setenv("ANSWER_GATHER", "agent")
    monkeypatch.setattr(answer, "OpenAIModel", Agent)
    monkeypatch.setattr(public_sources, "WeatherClient", FakeWeather)
    FakeWeather.calls, FakeWeather.held, FakeWeather.fail = 0, [], False
    FakeLaw.fail, FakeLaw.calls, FakeLaw.held = False, 0, []
    monkeypatch.setattr("tools.public_apis.law.LawClient", FakeLaw)


def card_evidence(connection, request_id):
    return connection.execute(text("""
        SELECT d.title, e.quote FROM card_evidence e JOIN cards c ON c.id=e.card_id
        JOIN document_chunks ch ON ch.id=e.chunk_id JOIN documents d ON d.id=ch.document_id
        WHERE c.request_id=:id AND c.kind='reply_draft' ORDER BY e.rank
    """), {"id": request_id}).mappings().all()


def test_agent_forecast_tool_is_the_only_weather_call(db_client, seeded_db, monkeypatch):
    tomorrow = datetime.now(KST).date() + timedelta(days=1)
    use_agent(monkeypatch, [{"tool": "forecast", "args": {"date": str(tomorrow)}}], "예보", "강수확률 최대 60%")
    card, evidence, _ = create_card(db_client, RAIN)
    # 날씨 낱말이 있어도 미리 가져오지 않고, AI가 부른 한 번만 트랜잭션 밖에서 불러요.
    assert FakeWeather.calls == 1 and FakeWeather.held == [0]
    assert [e["quote"] for e in evidence] == ["강수확률 최대 60%"] and evidence[0]["location"] == str(tomorrow)
    assert card["draft"]["text"] == "[TEST] 자료로 답해요."
    # 자료 찾는 AI·작성 AI·검사 AI 모두 이 요청의 아이 이름을 알아요.
    child = next(c["display_name"] for c in seed.CHILDREN if c["id"] == seed.CHILD)
    assert {role for role, _, _ in Agent.seen} == {"GATHER", "DOCUMENT", "CHECKER"}
    assert all(f"- 이 요청의 아이: {child} " in system for _, system, _ in Agent.seen)


def test_agent_fallback_fetches_forecast_by_words_once(db_client, seeded_db, monkeypatch):
    use_agent(monkeypatch, [], "예보", "강수확률 최대 60%", gather_error=ModelError("[TEST] 자료 찾기 실패"))
    _, evidence, _ = create_card(db_client, RAIN)
    # 자료 찾는 AI가 실패해 고정 검색으로 돌아갈 때만 질문 낱말(event_day)로 예보를 가져와요.
    assert FakeWeather.calls == 1 and FakeWeather.held == [0]
    assert [e["quote"] for e in evidence] == ["강수확률 최대 60%"]


def collab_complaint(db_client, seeded_db, monkeypatch, body):
    with seeded_db.begin() as connection:
        seed_documents(connection)
    monkeypatch.setattr(runner, "settings", replace(runner.settings,
                                                    request_agent="app.modules.requests.graph_agent:run_request"))
    monkeypatch.setenv("REQUEST_COLLAB_GRAPH", "1")
    login = db_client.post("/api/v1/auth/login", json={"login_id": "parent01", "password": "demo1234"})
    response = db_client.post("/api/v1/requests", headers={"Authorization": "Bearer " + login.json()["access_token"]},
                              json={"client_request_id": str(uuid4()), "type": "complaint", "body": body,
                                    "child_id": str(seed.CHILD)})
    assert response.status_code == 202, response.text
    request_id = response.json()["request"]["id"]
    with seeded_db.connect() as connection:
        card = connection.execute(text("SELECT * FROM cards WHERE request_id=:id AND kind='reply_draft'"),
                                  {"id": request_id}).mappings().one()
        return card, card_evidence(connection, request_id)


def test_agent_complaint_cites_law_it_called_without_keywords(db_client, seeded_db, monkeypatch):
    body = "[TEST] 아이가 열이 나서 며칠 쉬었는데 언제 다시 보내도 되나요"
    assert public_sources.law_rule_key("health_hygiene", None, body) is None
    use_agent(monkeypatch, [{"tool": "law_article", "args": {"key": "infection"}}], "등교 중지", "등교 중지를 명할 수 있다")
    card, evidence = collab_complaint(db_client, seeded_db, monkeypatch, body)
    # AI가 받은 조문을 인용했고, 그 조문이 보통 근거처럼 카드에 한 번 들어가요(외부 API는 트랜잭션 밖).
    assert [(e["title"], e["quote"]) for e in evidence] == [("학교보건법 제8조", "등교 중지를 명할 수 있다")]
    assert card["draft"]["text"] == "[TEST] 자료로 답해요." and "law_unchecked" not in card["draft"]
    assert FakeLaw.calls == 1  # 낱말로 미리 가져오지 않고 AI가 부른 한 번만
    # 그래프에선 기억 읽기 노드가 나란히 돌아 연결 수를 못 재니, 도구 하나만 불러 트랜잭션 밖 호출인지 봐요.
    from app.modules.documents.tools import RequestToolbox
    FakeLaw.held = []
    tools = RequestToolbox({"type": "complaint", "org_id": seed.ORG, "classroom_id": seed.CLASS_STAR,
                            "requester_id": seed.PARENT, "child_id": seed.CHILD, "created_at": datetime.now(KST)})
    assert tools.call("law_article", {"key": "child_safety"})[0]["document_title"] == "아동복지법 제17조"
    assert FakeLaw.held == [0]
    gather = next(payload for role, _, payload in Agent.seen if role == "GATHER")
    law_tool = next(t for t in gather["tools"] if t["name"] == "law_article")
    assert "학교보건법 제8조" in law_tool["description"] and "수족구" not in law_tool["description"]


def prepared_complaint(seeded_db, monkeypatch, body, fields, answer):
    FakeLaw.fail, FakeLaw.calls, FakeLaw.held = False, 0, []
    monkeypatch.setattr("tools.public_apis.law.LawClient", FakeLaw)
    with seeded_db.begin() as connection:
        request_id = connection.scalar(text("""
            INSERT INTO requests (org_id,classroom_id,child_id,requester_id,client_request_id,type,body,title)
            VALUES (:org,:class,:child,:parent,:key,'complaint',:body,:body) RETURNING id
        """), {"org": seed.ORG, "class": seed.CLASS_STAR, "child": seed.CHILD, "parent": seed.PARENT,
               "key": str(uuid4()), "body": body})
    check = {"passed": True, "issues": [], "attempt": 1}
    agent_stub.run_request(request_id, prepared_answer={"text": "[TEST] 확인할게요.", "evidence": [], "no_evidence": False,
                                                        "conflict": False, "check_result": check, **answer},
                           prepared_fields={"topic_key": "health_hygiene", "urgency": "normal", "risk_level": "normal",
                                            "risk_category": None, **fields})
    with seeded_db.connect() as connection:
        card = connection.execute(text("SELECT * FROM cards WHERE request_id=:id AND kind='reply_draft'"),
                                  {"id": request_id}).mappings().one()
        return card, [e["title"] for e in card_evidence(connection, request_id)]


def test_agent_draft_skips_keyword_law_but_keeps_child_safety_line(db_client, seeded_db, monkeypatch):
    infection = "[TEST] 수족구 걸린 친구가 등원했대요"
    # 자료 찾는 AI 초안이면 낱말 조건으로 법령을 덧붙이지 않아요(AI가 인용한 조문만 근거).
    _, titles = prepared_complaint(seeded_db, monkeypatch, infection, {}, {"gathered": True})
    assert titles == []
    # 모델 없음·실패 대역(gathered 없음)은 지금처럼 낱말 조건으로 붙여요.
    _, titles = prepared_complaint(seeded_db, monkeypatch, infection, {}, {})
    assert titles == ["학교보건법 제8조"]
    # 아동 안전 민원은 AI가 안 불러도 조문을 붙이는 선이에요.
    _, titles = prepared_complaint(seeded_db, monkeypatch, "[TEST] 선생님이 아이를 밀었대요",
                                   {"topic_key": "teacher", "risk_category": "child_safety"}, {"gathered": True})
    assert titles == ["아동복지법 제17조"]
    # AI가 부른 법령을 못 가져왔으면 미확인 표시가 남아요.
    card, titles = prepared_complaint(seeded_db, monkeypatch, "[TEST] 안내가 부족해요", {},
                                      {"gathered": True, "law_unchecked": True})
    assert titles == [] and card["draft"]["law_unchecked"] is True


def sent_inquiry(db_client, seeded_db, monkeypatch):
    with seeded_db.begin() as connection:
        seed_documents(connection)
        chunk = connection.scalar(text("""
            SELECT ch.id FROM document_chunks ch JOIN documents d ON d.id=ch.document_id
            WHERE d.title='겨울방학 안내' AND ch.location='1쪽 겨울방학 기간'
        """))
    setup_graph(seeded_db, monkeypatch, {"text": "[TEST] 겨울방학은 12월 24일부터예요.", "no_evidence": False,
                                         "conflict": False, "evidence": [{"chunk_id": chunk, "quote": "12월 24일"}]})
    card, _, _ = create_card(db_client, "겨울방학 언제부터인가요?")
    response = db_client.post(f"{BASE}/cards/{card['id']}/decisions", headers=auth(seed.TEACHER),
                              json={"version": card["version"], "decision": "edit_approve",
                                    "edited_content": {"text": "[TEST] 지난번 회신"}})
    assert response.status_code == 200, response.text
    data = db_client.get(f"{BASE}/cards/{card['id']}", headers=auth(seed.TEACHER)).json()
    return {**data["card"], "request_id": card["request_id"]}, chunk


def follow_up(db_client, card):
    response = db_client.post(f"{BASE}/requests/{card['request_id']}/messages", headers=auth(seed.PARENT),
                              json={"body": "[TEST] 방학 전날도 등원하나요?"})
    assert response.status_code == 201, response.text
    data = db_client.get(f"{BASE}/cards/{card['id']}", headers=auth(seed.TEACHER)).json()
    return data["card"], data["request"]


def test_follow_up_message_redrafts_with_whole_conversation(db_client, seeded_db, monkeypatch):
    card, chunk = sent_inquiry(db_client, seeded_db, monkeypatch)
    Writer.answer = {"text": "[TEST] 다시 쓴 답이에요.", "no_evidence": False, "conflict": False,
                     "evidence": [{"chunk_id": chunk, "quote": "12월 24일"}]}
    Writer.calls = []
    after, req = follow_up(db_client, card)
    assert req["status"] == "awaiting_review" and after["status"] == "pending"
    assert after["draft"]["text"] == "[TEST] 다시 쓴 답이에요." and after["draft"]["previous_text"] == "[TEST] 지난번 회신"
    assert after["check_result"]["passed"] is True and after["version"] == card["version"] + 2  # 다시 열기·다시 쓰기
    question = json.loads(next(user for role, user in Writer.calls if role == "DOCUMENT"))["question"]
    assert question.splitlines() == ["보호자: 겨울방학 언제부터인가요?", "선생님: [TEST] 지난번 회신",
                                     "보호자: [TEST] 방학 전날도 등원하나요?"]
    with seeded_db.connect() as connection:
        assert [e["quote"] for e in card_evidence(connection, card["request_id"])] == ["12월 24일"]
    # 다시 쓴 초안도 담임이 승인해야 나가요.
    response = db_client.post(f"{BASE}/cards/{card['id']}/decisions", headers=auth(seed.TEACHER),
                              json={"version": after["version"], "decision": "approve"})
    assert response.status_code == 200, response.text


def test_follow_up_redraft_failure_leaves_empty_card(db_client, seeded_db, monkeypatch):
    card, _ = sent_inquiry(db_client, seeded_db, monkeypatch)
    Writer.answer = ModelError("[TEST] 작성 실패")
    after, _ = follow_up(db_client, card)
    assert after["draft"]["text"] == "" and after["draft"]["previous_text"] == "[TEST] 지난번 회신"
    assert after["check_result"] is None and after["version"] == card["version"] + 1
