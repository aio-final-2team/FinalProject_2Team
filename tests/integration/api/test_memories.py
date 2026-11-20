"""T39 거절 기억·규칙 제안·주인 결정을 두 백엔드의 HTTP로 확인해요."""

from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from app import backend
from app.core.db import transaction
from app.mock import seed, store
from tests.integration.api.helpers import BASE, decision, err
from tests.integration.api.test_cards import create, detail


@pytest.fixture(autouse=True, params=["mock", "db"])
def memory_backend(request, monkeypatch):
    if request.param == "db":
        request.getfixturevalue("seeded_db")
        from app.core import users
        from app.modules.cards import cards, card_views
        from app.modules.memories import memories
        from app.modules.requests import requests
    else:
        from app.mock import cards, card_views, memories, request_actions as requests
        users = store
    for name, module in dict(users=users, cards=cards, card_views=card_views,
                             memories=memories, request_actions=requests).items():
        monkeypatch.setattr(backend, name, module)
    return request.param


def reject(client, parent, teacher, code="tone", choice="reject", **extra):
    rid, cid = create(client, parent, teacher, type="inquiry", body="[TEST] 준비물을 알려 주세요")
    response = decision(client, teacher, cid, choice, reason_code=code, **extra)
    assert response.status_code == 200, response.text
    return rid, cid, response


def memories(client, teacher):
    response = client.get(BASE + "/memories?kind=rejection_reason&size=100", headers=teacher)
    assert response.status_code == 200, response.text
    return response.json()["items"]


def proposals(client, teacher, code="tone"):
    response = client.get(BASE + "/cards?kind=rule_proposal&size=100", headers=teacher)
    assert response.status_code == 200, response.text
    cards = [detail(client, teacher, c["id"]) for c in response.json()["items"]]
    return [c for c in cards if c["rule"]["reason_code"] == code]


def decide_rule(client, teacher, rule_id, choice):
    return client.post(f"{BASE}/memory-rules/{rule_id}/decision", headers=teacher, json={"decision": choice})


def test_third_rejection_proposes_one_card_and_retry_does_not_duplicate(client, parent, teacher, memory_backend):
    source_cards = []
    for index in range(3):
        _, cid, response = reject(client, parent, teacher, reason_text="[TEST] 짧게 안내해 주세요")
        source_cards.append(cid)
        saved = memories(client, teacher)
        assert len(saved) == index + 1
        assert all(m["content"] == "[TEST] 짧게 안내해 주세요" and m["reason_code"] == "tone" for m in saved)
        assert all(m["structured"] == {"decision": "reject", "card_version": 1} for m in saved)
        assert len(proposals(client, teacher)) == (1 if index == 2 else 0)
        assert response.json()["next_card_id"] is not None
    proposed = proposals(client, teacher)[0]
    rule_id, proposal_id = proposed["rule"]["id"], proposed["card"]["id"]
    assert proposed["rule"]["status"] == "proposed" and proposed["request"] is None
    assert proposed["timeline"][0]["action"] == "created"
    assert proposed["timeline"][0]["agent_name"] == "memory"
    assert "짧게" not in proposed["rule"]["rule_text"]  # 자유 글에서 새 조건을 추론하지 않아요.
    err(decision(client, teacher, source_cards[-1], "reject", reason_code="tone"), 409, "ALREADY_DECIDED")
    reject(client, parent, teacher)
    assert len(memories(client, teacher)) == 4 and len(proposals(client, teacher)) == 1
    if memory_backend == "mock":
        saved_sources = [str(m.source_card_id) for m in store.state().memories.values()]
        rule = store.state().rules[UUID(rule_id)]
        assert rule.rule_json == {"reason_code": "tone"}
        assert store.state().cards[UUID(proposal_id)].due_at is None
    else:
        with transaction() as connection:
            saved_sources = [str(cid) for cid in connection.scalars(text("SELECT source_card_id FROM memories"))]
            assert connection.scalar(text("SELECT rule_json FROM memory_rules WHERE id=:id"),
                                     {"id": rule_id}) == {"reason_code": "tone"}
            assert connection.scalar(text("SELECT due_at FROM cards WHERE id=:id"), {"id": proposal_id}) is None
    assert set(source_cards) <= set(saved_sources)


def test_codes_and_owners_are_separate_and_deleted_memories_do_not_count(
    client, parent, parent_other, teacher, teacher_other
):
    reject(client, parent, teacher)
    reject(client, parent, teacher, code="policy")
    reject(client, parent, teacher)
    assert proposals(client, teacher) == []
    response = client.post(BASE + "/requests", headers=parent_other,
                           json={"client_request_id": str(uuid4()), "child_id": str(seed.CHILD_OTHER),
                                 "type": "inquiry", "body": "[TEST] 다른 담임 요청"})
    assert response.status_code == 202, response.text
    rid = response.json()["request"]["id"]
    cards = client.get(BASE + "/cards?size=100", headers=teacher_other).json()["items"]
    cid = next(c["id"] for c in cards if c["request_id"] == rid)
    assert decision(client, teacher_other, cid, "reject", reason_code="tone").status_code == 200
    assert len(memories(client, teacher_other)) == 1 and proposals(client, teacher_other) == []
    assert proposals(client, teacher) == []
    first = next(m for m in memories(client, teacher) if m["reason_code"] == "tone")
    assert client.delete(f"{BASE}/memories/{first['id']}", headers=teacher).status_code == 204
    reject(client, parent, teacher)
    assert proposals(client, teacher) == []
    assert len(memories(client, teacher_other)) == 1
    reject(client, parent, teacher)
    assert len(proposals(client, teacher)) == 1
    assert len([m for m in memories(client, teacher) if m["reason_code"] == "tone"]) == 3


@pytest.mark.parametrize("choice,status,action", [("activate", "active", "approved"), ("decline", "declined", "rejected")])
def test_only_owner_decides_and_closes_card_once(client, parent, teacher, teacher_other, director,
                                                memory_backend, choice, status, action):
    for _ in range(3):
        reject(client, parent, teacher)
    proposal = proposals(client, teacher)[0]
    rid, cid = proposal["rule"]["id"], proposal["card"]["id"]
    for actor in (parent, teacher_other, director):
        err(decide_rule(client, actor, rid, choice), 404, "NOT_FOUND")
    err(decide_rule(client, teacher, str(uuid4()), choice), 404, "NOT_FOUND")
    assert detail(client, teacher, cid)["rule"]["status"] == "proposed"
    response = decide_rule(client, {**teacher, "X-Request-ID": "[TEST]-memory-decision"}, rid, choice)
    assert response.status_code == 200, response.text
    assert response.json() == {"rule": {"id": rid, "status": status}}
    saved = detail(client, teacher, cid)
    assert saved["card"]["status"] == "done" and saved["card"]["version"] == 2
    assert saved["timeline"][-1]["action"] == action and saved["timeline"][-1]["request_id"] is None
    assert saved["timeline"][-1]["actor_id"] == str(seed.TEACHER)
    assert saved["timeline"][-1]["detail"]["trace_id"] == "[TEST]-memory-decision"
    err(decide_rule(client, teacher, rid, choice), 409, "INVALID_TRANSITION")
    if memory_backend == "mock":
        approvals = [a for a in store.state().approvals if str(a.card_id) == cid]
        assert store.state().rules[UUID(rid)].decided_at is not None
        assert len(approvals) == 1 and approvals[0].card_version == 1
    else:
        with transaction() as connection:
            assert connection.scalar(text("SELECT decided_at FROM memory_rules WHERE id=:id"), {"id": rid})
            assert connection.execute(text("SELECT decision,card_version FROM approvals WHERE card_id=:id"),
                                      {"id": cid}).all() == [("approve" if choice == "activate" else "reject", 1)]
    # 규칙 거절은 카드 거절 기억을 다시 쌓지 않아요.
    assert len(memories(client, teacher)) == 3
    reject(client, parent, teacher)
    assert len(proposals(client, teacher)) == (0 if choice == "activate" else 1)


def test_concurrent_opposite_decisions_commit_only_one(client, parent, teacher):
    for _ in range(3):
        reject(client, parent, teacher)
    proposal = proposals(client, teacher)[0]
    rid, cid = proposal["rule"]["id"], proposal["card"]["id"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda choice: decide_rule(client, teacher, rid, choice), ("activate", "decline")))
    assert sorted(r.status_code for r in responses) == [200, 409]
    err(next(r for r in responses if r.status_code == 409), 409, "INVALID_TRANSITION")
    saved = detail(client, teacher, cid)
    assert saved["card"]["version"] == 2
    assert len([e for e in saved["timeline"] if e["action"] in ("approved", "rejected")]) == 1


def test_dismiss_saves_reason_but_approve_and_director_do_not_train_teacher(client, parent, teacher, director):
    _, cid = create(client, parent, teacher, type="inquiry")
    assert decision(client, teacher, cid).status_code == 200
    assert memories(client, teacher) == []
    reject(client, parent, teacher, choice="dismiss", code="wrong_fact")
    assert memories(client, teacher)[0]["structured"]["decision"] == "dismiss"
    assert memories(client, teacher)[0]["content"] == "거절 이유: wrong_fact"
    reject(client, parent, director, code="tone")
    assert len(memories(client, teacher)) == 1


def test_other_text_is_saved_verbatim_but_not_copied_to_automatic_rule(client, parent, teacher):
    for _ in range(3):
        reject(client, parent, teacher, code="other", reason_text="[TEST] 일회성 사정")
    assert len(memories(client, teacher)) == 3
    assert proposals(client, teacher, "other") == []


def test_rule_input_validation_and_authentication(client, teacher):
    path = f"{BASE}/memory-rules/{uuid4()}/decision"
    err(client.post(path, json={"decision": "activate"}), 401, "UNAUTHENTICATED")
    for body in ({}, {"decision": "active"}, {"decision": None}):
        err(client.post(path, headers=teacher, json=body), 422, "VALIDATION_FAILED")
    err(decide_rule(client, teacher, "bad-uuid", "activate"), 422, "VALIDATION_FAILED")
