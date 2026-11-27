"""[TEST] 모의·DB의 말투와 승인 답 저장 계약을 확인해요."""

import json
from copy import copy
from datetime import timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from app import backend
from app.core.db import transaction
from app.mock import seed, store
from app.modules.documents import embedding
from app.modules.memories import saved_answers
from tests.integration.api import test_memories
from tests.integration.api.helpers import BASE, decision
from tests.integration.api.test_cards import create

memory_backend = test_memories.memory_backend


def test_tone_storage_contract(client, parent, teacher, memory_backend):
    _, cid = create(client, parent, teacher, type="inquiry")
    user = backend.users.get_user(seed.TEACHER)
    card = {"id": UUID(cid), "version": 1}
    def save(candidates):
        if memory_backend == "db":
            with transaction() as connection:
                backend.memories.save_tones(connection, user, card, candidates, ["하늘"])
        else:
            backend.memories.save_tones(user, card, candidates, ["하늘"])
    candidates = [{"kind": "tone", "content": value} for value in (
        "하늘에게 해요체로 안내해요.", "해요체로 안내해요.", "해요체로 안내해요.",
        "010-1234-5678로 끝내요.", "test@example.com을 붙여요.", "내일 3시에 안내해요.",
        "첫 문장. 둘째 문장.", "줄을\n나눠요", "가" * 81)]
    save(candidates + [{"kind": "preference", "content": "짧게 써요."}])
    items = client.get(BASE + "/memories?kind=tone&size=100", headers=teacher).json()["items"]
    assert {m["content"] for m in items} == {"○○에게 해요체로 안내해요.", "해요체로 안내해요."}
    assert all(m["structured"] == {"source": "edit_approve", "card_version": 1} for m in items)
    for suffix in "가나다라마바사아자차카타파하":
        save([{"kind": "tone", "content": f"마무리에는 {suffix} 표현을 써요."}])
    items = client.get(BASE + "/memories?kind=tone&size=100", headers=teacher).json()["items"]
    assert len(items) == 12
    assert not any(m["content"] == "해요체로 안내해요." for m in items)
    if memory_backend == "mock":
        assert len([m for m in store.state().memories.values() if m.deleted_at is not None]) == 4


VECTOR = [1.0] + [0.0] * 1023


@pytest.fixture
def saved_case(client, parent, teacher, memory_backend, monkeypatch):
    monkeypatch.setenv("LLM_MODEL_MEMORY", "")
    monkeypatch.setenv("EMBEDDING_MODEL", embedding.MODEL)
    monkeypatch.setattr(embedding, "enabled", lambda: True)
    embedding_inputs = []
    monkeypatch.setattr(embedding, "embed", lambda texts: embedding_inputs.append(texts) or [VECTOR])
    name = seed.CHILDREN[0]["display_name"]
    rid, cid = create(client, parent, teacher, type="inquiry", body=f"[TEST] {name} 행사 안내 010-1234-5678")
    if memory_backend == "db":
        with transaction() as connection:
            connection.execute(text("UPDATE cards SET draft=draft || CAST(:flags AS jsonb) WHERE id=:id"),
                               {"id": cid, "flags": json.dumps({"no_evidence": False, "conflict": False})})
            connection.execute(text("DELETE FROM card_evidence WHERE card_id=:id"), {"id": cid})
            connection.execute(text("""INSERT INTO card_evidence(card_id,org_id,chunk_id,rank,quote)
                SELECT :card,org_id,id,1,content FROM document_chunks WHERE document_id=:doc LIMIT 1"""),
                               {"card": cid, "doc": seed.NOTICE})
            connection.execute(text("UPDATE documents SET effective_from=current_date-10,effective_to=NULL WHERE id=:id"),
                               {"id": seed.NOTICE})
            req = dict(connection.execute(text("SELECT * FROM requests WHERE id=:id"), {"id": rid}).mappings().one())
    else:
        from app.mock.records import Evidence
        card = store.state().cards[UUID(cid)]
        card.draft.update(no_evidence=False, conflict=False)
        store.state().evidence = [e for e in store.state().evidence if e.card_id != card.id]
        chunk = next(c for c in store.state().chunks.values() if c.document_id == seed.NOTICE)
        store.state().evidence.append(Evidence(card.id, seed.ORG, chunk.id, 1, chunk.content))
        store.state().documents[seed.NOTICE].effective_from = store.now().date() - timedelta(days=10)
        req = copy(store.state().requests[UUID(rid)])
    return SimpleNamespace(rid=rid, cid=cid, req=req, mode=memory_backend, monkeypatch=monkeypatch, embedding_inputs=embedding_inputs)


def find(case, vector=VECTOR, **changes):
    if case.mode == "db":
        case.monkeypatch.setattr(embedding, "embed", lambda texts: [vector])
        return saved_answers.find_saved_answer({**case.req, **changes})
    from app.mock.memories import find_saved_answer
    req = copy(case.req)
    for key, value in changes.items():
        setattr(req, key, value)
    return find_saved_answer(req, vector)


def rows(case):
    if case.mode == "db":
        with transaction() as connection:
            return [dict(r) for r in connection.execute(text("SELECT * FROM saved_answers")).mappings()]
    return list(store.state().saved_answers.values())


def change(case, table, field, value):
    if case.mode == "db":
        with transaction() as connection:
            connection.execute(text(f"UPDATE {table} SET {field}=:value"), {"value": value})
    elif table == "saved_answers":
        for row in store.state().saved_answers.values():
            row[field] = value
    else:
        setattr(store.state().documents[seed.NOTICE], field, value)


@pytest.mark.parametrize("choice", ["approve", "edit_approve"])
def test_saved_answer_storage_and_scope(client, teacher, saved_case, choice):
    name = seed.CHILDREN[0]["display_name"]
    sent = f"[TEST] {name} 담임이 직접 확인한 행사 안내예요. 010-1234-5678"
    extra = {"edited_content": {"text": sent}} if choice == "edit_approve" else {}
    assert decision(client, teacher, saved_case.cid, choice, **extra).status_code == 200
    row, = rows(saved_case)
    assert bool(saved_case.embedding_inputs) == (saved_case.mode == "db")
    assert row["approved_by"] == seed.TEACHER and str(row["source_card_id"]) == saved_case.cid
    assert "010-1234-5678" not in row["question"] and "[전화번호]" in row["question"]
    assert seed.CHILDREN[0]["display_name"] not in row["question"] and "○○" in row["question"]
    assert row["embedding_model"] == embedding.MODEL and row["embedding_version"] == embedding.VERSION
    prior = find(saved_case)
    assert prior and prior["answer"] == row["answer"] and prior["approved_at"] == row["created_at"]
    if choice == "edit_approve":  # 다른 가정 초안의 참고가 되므로 답도 이름·전화번호를 가려 저장해요
        assert prior["answer"] == sent.replace(name, "○○").replace("010-1234-5678", "[전화번호]")
    assert find(saved_case, classroom_id=seed.CLASS_SUN) is None
    assert find(saved_case, org_id=uuid4()) is None
    change(saved_case, "saved_answers", "status", "off")
    assert find(saved_case) is None
    change(saved_case, "saved_answers", "status", "active")
    assert find(saved_case, [0.79, 0.6131068422] + [0.0] * 1022) is None
    assert find(saved_case, [0.80, 0.60] + [0.0] * 1022)  # 0.80 경계는 포함
    change(saved_case, "saved_answers", "classroom_id", None)
    assert find(saved_case, classroom_id=seed.CLASS_SUN)  # 원 전체 답
    change(saved_case, "documents", "effective_to", store.now().date() - timedelta(days=1))
    assert find(saved_case) is None
    change(saved_case, "documents", "effective_to", None)
    change(saved_case, "documents", "status", "superseded")
    assert find(saved_case) is None
    if saved_case.mode == "db":
        assert rows(saved_case)[0]["status"] == "invalidated"


@pytest.mark.parametrize("reason", ["disabled", "no_evidence", "conflict", "no_sources"])
def test_ineligible_answer_is_not_saved(client, teacher, saved_case, reason, monkeypatch):
    if reason == "disabled":
        monkeypatch.setenv("EMBEDDING_MODEL", "")
        monkeypatch.setattr(embedding, "enabled", lambda: False)
    elif saved_case.mode == "db":
        with transaction() as connection:
            if reason == "no_sources":
                connection.execute(text("DELETE FROM card_evidence WHERE card_id=:id"), {"id": saved_case.cid})
            else:
                connection.execute(text("UPDATE cards SET draft=draft || CAST(:flag AS jsonb) WHERE id=:id"),
                                   {"flag": json.dumps({reason: True}), "id": saved_case.cid})
    else:
        if reason == "no_sources":
            store.state().evidence.clear()
        else:
            store.state().cards[UUID(saved_case.cid)].draft[reason] = True
    assert decision(client, teacher, saved_case.cid, "edit_approve", edited_content={"text": "[TEST] 직접 확인한 답"}).status_code == 200
    assert rows(saved_case) == []


def test_saved_sources_visibility_period_and_model(client, teacher, saved_case):
    assert decision(client, teacher, saved_case.cid).status_code == 200
    assert find(saved_case)
    change(saved_case, "saved_answers", "embedding_version", "[TEST] old-model")
    assert find(saved_case) is None
    change(saved_case, "saved_answers", "embedding_version", embedding.VERSION)
    change(saved_case, "documents", "visibility", "staff")
    assert find(saved_case) is None
    change(saved_case, "documents", "visibility", "all")
    change(saved_case, "documents", "effective_from", store.now().date() + timedelta(days=1))
    assert find(saved_case) is None
    change(saved_case, "documents", "effective_from", store.now().date())
    if saved_case.mode == "db":
        with transaction() as connection:
            connection.execute(text("INSERT INTO document_classrooms(org_id,document_id,classroom_id) VALUES (:org,:doc,:class)"),
                               {"org": seed.ORG, "doc": seed.NOTICE, "class": seed.CLASS_SUN})
    else:
        store.state().document_classrooms[seed.NOTICE] = [seed.CLASS_SUN]
    assert find(saved_case) is None
