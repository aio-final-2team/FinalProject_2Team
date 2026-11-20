"""T39 거절 기억·규칙 제안·주인 결정을 두 백엔드의 HTTP로 확인해요."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
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
        from app.modules.notifications import notifications
        from app.modules.requests import requests
    else:
        from app.mock import cards, card_views, memories, notifications, request_actions as requests
        users = store
    for name, module in dict(users=users, cards=cards, card_views=card_views,
                             memories=memories, notifications=notifications, request_actions=requests).items():
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
    assert len(proposals(client, teacher)) == 0


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


def test_declined_rule_requires_three_new_rejections_after_latest_decision(client, parent, teacher):
    for _ in range(6):
        reject(client, parent, teacher)
    for _ in range(2):
        proposal = proposals(client, teacher)[0]
        assert decide_rule(client, teacher, proposal["rule"]["id"], "decline").status_code == 200
        for _ in range(2):
            reject(client, parent, teacher)
            assert proposals(client, teacher) == []
        reject(client, parent, teacher)
        assert len(proposals(client, teacher)) == 1


def test_personal_rule_cannot_be_reassigned_or_seen_by_same_class_teacher(
    client, parent, teacher, teacher_other, director, memory_backend
):
    for _ in range(3):
        reject(client, parent, teacher)
    proposal = proposals(client, teacher)[0]
    cid = proposal["card"]["id"]
    if memory_backend == "mock":
        store.state().classroom_staff.append(store.ClassroomStaff(seed.CLASS_STAR, seed.TEACHER_OTHER))
    else:
        with transaction() as connection:
            connection.execute(text("INSERT INTO classroom_staff (org_id,classroom_id,user_id) VALUES (:org,:class,:user)"),
                               {"org": seed.ORG, "class": seed.CLASS_STAR, "user": seed.TEACHER_OTHER})
    response = client.post(f"{BASE}/cards/{cid}/reassign", headers=director,
                           json={"assignee_id": str(seed.TEACHER_OTHER), "reason": "[TEST] 개인 규칙"})
    err(response, 409, "INVALID_TRANSITION")
    assert detail(client, teacher, cid)["card"]["version"] == 1
    assert proposals(client, teacher_other) == []
    err(client.get(f"{BASE}/cards/{cid}", headers=teacher_other), 404, "NOT_FOUND")


def test_personal_rule_inbox_uses_current_assignment_and_null_when_none(client, parent, teacher, memory_backend):
    for _ in range(3):
        reject(client, parent, teacher)
    cid = proposals(client, teacher)[0]["card"]["id"]
    today = store.now().date()
    if memory_backend == "mock":
        for assignment in store.state().classroom_staff:
            if assignment.user_id == seed.TEACHER:
                assignment.valid_to = today-timedelta(days=1)
        current = store.ClassroomStaff(seed.CLASS_SUN, seed.TEACHER, valid_from=today)
        store.state().classroom_staff.append(current)
    else:
        with transaction() as connection:
            connection.execute(text("UPDATE classroom_staff SET valid_to=CURRENT_DATE-1 WHERE user_id=:user"),
                               {"user": seed.TEACHER})
            connection.execute(text("""INSERT INTO classroom_staff (org_id,classroom_id,user_id,valid_from)
                VALUES (:org,:class,:user,CURRENT_DATE)"""),
                {"org": seed.ORG, "class": seed.CLASS_SUN, "user": seed.TEACHER})

    def classroom():
        rows = client.get(BASE + "/cards?kind=rule_proposal&size=100", headers=teacher).json()["items"]
        return next(row["classroom"] for row in rows if row["id"] == str(cid))

    assert classroom()["id"] == str(seed.CLASS_SUN)
    if memory_backend == "mock":
        current.valid_from = today+timedelta(days=1)
    else:
        with transaction() as connection:
            connection.execute(text("""UPDATE classroom_staff SET valid_from=CURRENT_DATE+1
                WHERE user_id=:user AND classroom_id=:class"""), {"user": seed.TEACHER, "class": seed.CLASS_SUN})
    assert classroom() is None


def test_rejection_memory_masks_names_from_entire_organization(client, parent, teacher):
    reject(client, parent, teacher, reason_text="[TEST] 하늘이와 노을이, 다른 반 바다도 확인해 주세요")
    assert memories(client, teacher)[0]["content"] == "[TEST] ○○이와 ○○이, 다른 반 ○○도 확인해 주세요"


def test_deleted_memory_erases_content_and_structured_but_keeps_audit_row(
    client, parent, teacher, memory_backend
):
    reject(client, parent, teacher, reason_text="[TEST] 파기할 사유 원문")
    memory_id = memories(client, teacher)[0]["id"]
    assert client.delete(f"{BASE}/memories/{memory_id}", headers=teacher).status_code == 204
    assert memories(client, teacher) == []
    if memory_backend == "mock":
        row = store.state().memories[memory_id]
        assert row.content == "" and row.structured == {} and row.deleted_at and row.source_card_id
    else:
        with transaction() as connection:
            content, structured, deleted_at, source = connection.execute(text("""
                SELECT content,structured,deleted_at,source_card_id FROM memories WHERE id=:id
            """), {"id": memory_id}).one()
            assert content == "" and structured == {} and deleted_at and source


@pytest.mark.parametrize("rule_json", [[], {"after": "3pm"}, {"before": "24:00"}, {"after": None},
                                       {"before": "09:00:00"}])
def test_rule_tool_rejects_invalid_time_bounds(memory_backend, rule_json):
    from app.core.errors import ApiError
    if memory_backend == "mock":
        from app.mock.memories import propose_rule
        with pytest.raises(ApiError) as caught:
            propose_rule(seed.TEACHER, "slot_unavailable", "[TEST] 시간", rule_json, org_id=seed.ORG)
    else:
        from app.modules.memories.memories import propose_rule
        with transaction() as connection, pytest.raises(ApiError) as caught:
            propose_rule(connection, seed.TEACHER, "slot_unavailable", "[TEST] 시간", rule_json, org_id=seed.ORG)
    assert caught.value.status == 422 and caught.value.code == "VALIDATION_FAILED"


def test_proposal_failure_rolls_back_only_proposal_and_keeps_rejection(client, parent, teacher, memory_backend, monkeypatch):
    from app.mock import memories as mock_memories
    from app.modules.memories import memories as db_memories
    module = mock_memories if memory_backend == "mock" else db_memories
    for _ in range(2):
        reject(client, parent, teacher)
    original, calls = module.propose_rule, []

    def fail_after_saving(*args, **kwargs):
        calls.append(1)
        original(*args, **kwargs)
        if memory_backend == "db":
            # SQL 오류도 savepoint 밖의 카드 거절 트랜잭션을 망가뜨리지 않아요.
            args[0].execute(text("SELECT 1/0"))
        raise RuntimeError("[TEST] 제안 저장 뒤 실패")

    monkeypatch.setattr(module, "propose_rule", fail_after_saving)
    _, cid, response = reject(client, parent, teacher)
    assert len(calls) == 2 and response.json()["next_card_id"]
    assert len(memories(client, teacher)) == 3 and proposals(client, teacher) == []
    saved = detail(client, teacher, cid)
    assert saved["card"]["status"] == "rejected"
    errors = [e for e in saved["timeline"] if e["action"] == "tool_failed"]
    assert len(errors) == 1 and errors[0]["detail"]["code"] == "SAVE_FAILED"
    if memory_backend == "db":
        with transaction() as connection:
            assert connection.scalar(text("SELECT count(*) FROM memory_rules WHERE reason_code='tone'")) == 0
            assert connection.scalar(text("SELECT count(*) FROM cards WHERE kind='rule_proposal'")) == 0
            assert connection.scalar(text("SELECT count(*) FROM notifications n JOIN cards c ON c.id=n.card_id WHERE c.kind='rule_proposal'")) == 0
    monkeypatch.setattr(module, "propose_rule", original)
    reject(client, parent, teacher)
    assert len(proposals(client, teacher)) == 1


def test_rule_proposal_notifies_owner_once_with_work_hours_delay(client, parent, teacher, memory_backend):
    from app.core.schedule import deliver_after
    for _ in range(3):
        reject(client, parent, teacher)
    proposal = proposals(client, teacher)[0]
    cid = proposal["card"]["id"]
    if memory_backend == "mock":
        rows = [n.__dict__ for n in store.state().notifications.values() if str(n.card_id) == cid]
    else:
        with transaction() as connection:
            rows = [dict(row) for row in connection.execute(text("SELECT * FROM notifications WHERE card_id=:id"),
                                                            {"id": cid}).mappings()]
    assert len(rows) == 1 and rows[0]["recipient_id"] == seed.TEACHER and rows[0]["kind"] == "new_card"
    assert rows[0]["request_id"] is None
    assert rows[0]["deliver_after"] == deliver_after(rows[0]["created_at"], "teacher")
