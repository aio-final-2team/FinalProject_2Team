"""[TEST] 가짜 모델만 써서 커밋 뒤 학습과 다음 작성 입력을 확인해요."""

import json
from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from agents.graphs import answer, daily_note
from app.core import users
from app.core.auth import issue_token
from app.core.db import transaction
from app.core.schedule import KST
from app.mock import seed
from app.modules.memories import memories
from app.modules.requests import graph_agent
from app.modules.daily_notes.runner import _payload
from tests.integration.db.test_answer_t33 import create_card, setup_graph


TONE = {"kind": "tone", "content": "해요체로 짧게 안내해요."}


def approve(client, card, decision="edit_approve"):
    headers = {"Authorization": "Bearer " + issue_token(users.get_user(seed.TEACHER))}
    data = {"version": card["version"], "decision": decision}
    if decision == "edit_approve":
        data["edited_content"] = {"text": "[TEST] 알려 주셔서 고마워요."}
    response = client.post(f"/api/v1/cards/{card['id']}/decisions", headers=headers, json=data)
    assert response.status_code == 200, response.text
    return response


def install_memory(monkeypatch, result):
    monkeypatch.setenv("LLM_MODEL_MEMORY", "fake-memory")
    class Model:
        def __init__(self, role):
            assert role == "MEMORY"
        def json(self, system, user):
            value = json.loads(user)
            # 새 연결로 봐도 이미 승인과 발송이 커밋돼 있어야 해요.
            with transaction() as connection:
                assert connection.scalar(text("SELECT count(*) FROM approvals")) >= 1
                assert connection.scalar(text("SELECT count(*) FROM request_messages WHERE body=:body"),
                                         {"body": value["edited"]}) >= 1
            if isinstance(result, Exception):
                raise result
            return result
    monkeypatch.setattr(memories, "OpenAIModel", Model)


def test_edit_approve_learns_then_next_inquiry_writer_reads(db_client, seeded_db, monkeypatch):
    monkeypatch.delenv("EMBEDDING_MODEL", raising=False)
    install_memory(monkeypatch, {"tones": [TONE]})
    card, _, _ = create_card(db_client, "[TEST] 준비물 알려 주세요")
    original = card["draft"]["text"]
    assert original
    approve(db_client, card)
    loaded = graph_agent._load_request_memory(card["request_id"])
    assert loaded == [TONE]
    setup_graph(seeded_db, monkeypatch, {"text": "", "evidence": [], "no_evidence": True})
    card, _, _ = create_card(db_client, "겨울방학 언제부터인가요?")
    from tests.integration.db.test_answer_t33 import Writer
    assert json.loads(Writer.calls[0][1])["memories"] == [TONE]
    seen = []
    class WriterModel:
        def __init__(self, role):
            pass
        def json(self, system, user):
            seen.append(json.loads(user))
            return {"text": "", "evidence": []}
    monkeypatch.setattr(answer, "OpenAIModel", WriterModel)
    graph_agent._write_request({"request_id": card["request_id"], "parallel": {"chunks": [], "memories": loaded}})
    assert seen[0]["memories"] == [TONE]


def test_memory_disabled_does_not_fall_back_to_default(db_client, monkeypatch):
    monkeypatch.setenv("LLM_MODEL_MEMORY", "")
    monkeypatch.setenv("LLM_MODEL_DEFAULT", "must-not-call")
    monkeypatch.setattr(memories, "OpenAIModel", lambda *args: pytest.fail("[TEST] disabled model called"))
    card, _, _ = create_card(db_client, "[TEST] 준비물 알려 주세요")
    approve(db_client, card)
    assert graph_agent._load_request_memory(card["request_id"]) == []


@pytest.mark.parametrize("result", [RuntimeError("[TEST] 모델 오류"), {"tones": "오류"}, {"tones": [TONE] * 3}])
def test_model_or_format_error_keeps_approval_200(db_client, monkeypatch, result):
    install_memory(monkeypatch, result)
    card, _, _ = create_card(db_client, "[TEST] 준비물 알려 주세요")
    approve(db_client, card)
    with transaction() as connection:
        assert connection.scalar(text("SELECT count(*) FROM memories WHERE kind='tone'")) == 0
        assert connection.scalar(text("SELECT count(*) FROM events WHERE agent_name='memory' AND action='tool_failed'")) == 1
        assert connection.scalar(text("SELECT status FROM cards WHERE id=:id"), {"id": card["id"]}) == "done"


def test_daily_note_payload_and_owner_scope(db_client, monkeypatch):
    user = users.get_user(seed.TEACHER)
    other = users.get_user(seed.TEACHER_OTHER)
    with transaction() as connection:
        memories.save_tones(connection, user, {"id": None, "version": 1}, [TONE], [])
        memories.save_tones(connection, other, {"id": None, "version": 1},
                            [{"kind": "tone", "content": "[TEST] 다른 담임 말투"}], [])
        org = connection.scalar(text("INSERT INTO organizations(name) VALUES ('[TEST] 다른 원') RETURNING id"))
        foreign = connection.scalar(text("""INSERT INTO users(org_id,role,login_id,password_hash,display_name)
            VALUES (:org,'teacher','[TEST]foreign','unused','[TEST]담임') RETURNING id"""), {"org": org})
        memories.save_tones(connection, SimpleNamespace(org_id=org, id=foreign), {"id": None, "version": 1},
                            [{"kind": "tone", "content": "[TEST] 다른 원 말투"}], [])
        entry = {"id": "[TEST]", "org_id": seed.ORG, "classroom_id": seed.CLASS_STAR, "author_id": seed.TEACHER,
                 "note_date": datetime.now(KST).date(), "child_memos": [], "activities": "[TEST] 놀이", "supplies": ""}
        payload = _payload(connection, entry)
    assert payload["memories"] == [TONE]
    seen = []
    model = SimpleNamespace(json=lambda system, user: seen.append(json.loads(user)) or {"child": "", "checks": []})
    daily_note.write(model, payload, payload["children"][0], [])
    daily_note.review(model, payload, payload["children"][0], [])
    assert seen[0]["memories"] == [TONE] and "memories" not in seen[1]
