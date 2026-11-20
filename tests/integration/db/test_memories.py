"""기억 제안의 동시 임계값·결정 원자성·승인 전 상담 적용 금지를 검증해요."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.mock import seed
from tests.integration.db.test_cards import BASE, auth, create


def reject(client, cid, code="tone"):
    return client.post(f"{BASE}/cards/{cid}/decisions", headers=auth(seed.TEACHER),
                       json={"version": 1, "decision": "reject", "reason_code": code})


def test_concurrent_rejections_on_distinct_requests_do_not_miss_third_or_duplicate_proposal(
    db_client, seeded_db, monkeypatch
):
    from app.modules.cards import cards

    _, first = create(db_client, "inquiry")
    assert reject(db_client, first).status_code == 200
    targets = [create(db_client, "inquiry")[1] for _ in range(2)]
    barrier = Barrier(2)
    remember = cards.remember_rejection

    def simultaneous(*args):
        barrier.wait(timeout=15)
        return remember(*args)

    monkeypatch.setattr(cards, "remember_rejection", simultaneous)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda cid: reject(db_client, cid), targets))
    assert [r.status_code for r in responses] == [200, 200], [r.text for r in responses]
    with seeded_db.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM memories")) == 3
        assert connection.scalar(text("SELECT count(DISTINCT source_card_id) FROM memories")) == 3
        assert connection.scalar(text("SELECT count(*) FROM memory_rules WHERE reason_code='tone'")) == 1
        assert connection.scalar(text("SELECT count(*) FROM cards WHERE kind='rule_proposal'")) == 1
        assert connection.scalar(text("SELECT count(*) FROM events WHERE agent_name='memory' AND action='created'")) == 1


@pytest.mark.parametrize("step", ["proposal", "decision"])
def test_failure_rolls_back_memory_proposal_card_and_approval(db_client, seeded_db, monkeypatch, step):
    from app.modules.cards import cards
    from app.modules.memories import memories

    for _ in range(2 if step == "proposal" else 3):
        _, cid = create(db_client, "inquiry")
        assert reject(db_client, cid).status_code == 200
    if step == "proposal":
        _, cid = create(db_client, "inquiry")
    else:
        with seeded_db.connect() as connection:
            cid, rid = connection.execute(text("SELECT id,subject_id FROM cards WHERE kind='rule_proposal'")).one()
    tables = ("memories", "memory_rules", "cards", "approvals", "events", "notifications")
    with seeded_db.connect() as connection:
        before = {table: connection.scalar(text(f"SELECT count(*) FROM {table}")) for table in tables}

    def fail(*args, **kwargs):
        raise RuntimeError("[TEST] 이력 저장 실패")

    monkeypatch.setattr(memories if step == "proposal" else cards, "record", fail)
    if step == "proposal":
        response = reject(db_client, cid)
    else:
        response = db_client.post(f"{BASE}/memory-rules/{rid}/decision", headers=auth(seed.TEACHER),
                                  json={"decision": "activate"})
    assert response.status_code == 500 and response.json()["error"]["code"] == "INTERNAL_ERROR"
    with seeded_db.connect() as connection:
        assert {table: connection.scalar(text(f"SELECT count(*) FROM {table}")) for table in tables} == before
        assert connection.execute(text("SELECT status,version FROM cards WHERE id=:id"), {"id": cid}).one() == (
            "pending", 1)
        if step == "decision":
            assert connection.execute(text("SELECT status,decided_at FROM memory_rules WHERE id=:id"),
                                      {"id": rid}).one() == ("proposed", None)


@pytest.mark.parametrize("choice", ["activate", "decline"])
def test_propose_rule_reuses_id_and_only_active_time_rule_changes_next_candidates(db_client, seeded_db, choice):
    from app.modules.memories.memories import propose_rule

    values = {"org": seed.ORG, "owner": seed.TEACHER}
    with seeded_db.begin() as connection:
        assert propose_rule(connection, seed.TEACHER, "slot_unavailable", "[TEST] 오후만 상담", {"after": "14:00"},
                            org_id=seed.ORG) is None
        connection.execute(text("""
            INSERT INTO memories (org_id,owner_id,kind,reason_code,content)
            SELECT :org,:owner,'rejection_reason','slot_unavailable','[TEST] 오후만 상담' FROM generate_series(1,3)
        """), values)
        rid = propose_rule(connection, seed.TEACHER, "slot_unavailable", "[TEST] 오후만 상담", {"after": "14:00"},
                           org_id=seed.ORG)
        assert rid is not None
        assert propose_rule(connection, seed.TEACHER, "slot_unavailable", "[TEST] 다른 제안", {"after": "16:00"},
                            org_id=seed.ORG) == rid

    def candidates():
        _, cid = create(db_client, "consultation")
        with seeded_db.connect() as connection:
            return connection.scalars(text("SELECT period FROM consultation_slots WHERE card_id=:id ORDER BY rank"),
                                      {"id": cid}).all()

    before = candidates()
    assert len(before) == 3 and all(slot.lower.hour < 14 for slot in before)
    response = db_client.post(f"{BASE}/memory-rules/{rid}/decision", headers=auth(seed.TEACHER),
                              json={"decision": choice})
    assert response.status_code == 200, response.text
    after = candidates()
    assert len(after) == 3
    assert all((slot.lower.hour >= 14) == (choice == "activate") for slot in after)
    with seeded_db.begin() as connection:
        if choice == "activate":
            assert propose_rule(connection, seed.TEACHER, "slot_unavailable", "[TEST] 중복", {}, org_id=seed.ORG) == rid
        assert connection.scalar(text("SELECT count(*) FROM cards WHERE kind='rule_proposal'")) == 1
        assert connection.scalar(text("SELECT rule_json FROM memory_rules WHERE id=:id"),
                                 {"id": rid}) == {"after": "14:00"}


def test_foreign_rule_is_hidden_and_denial_event_has_no_foreign_key_link(db_client, seeded_db):
    org, owner, rid, cid = (uuid4() for _ in range(4))
    with seeded_db.begin() as connection:
        connection.execute(text("INSERT INTO organizations (id,name) VALUES (:id,'[TEST] 다른 기관')"), {"id": org})
        connection.execute(text("""
            INSERT INTO users (id,org_id,role,login_id,display_name,password_hash)
            VALUES (:id,:org,'teacher','[TEST]-other','[TEST] 다른 담임','[TEST]-unused')
        """), {"id": owner, "org": org})
        connection.execute(text("""
            INSERT INTO memory_rules (id,org_id,owner_id,reason_code,rule_text,rule_json)
            VALUES (:id,:org,:owner,'tone','[TEST] 비공개','{}')
        """), {"id": rid, "org": org, "owner": owner})
        connection.execute(text("""
            INSERT INTO cards (id,org_id,kind,status,assignee_id,subject_type,subject_id)
            VALUES (:id,:org,'rule_proposal','pending',:owner,'memory_rule',:rule)
        """), {"id": cid, "org": org, "owner": owner, "rule": rid})
    response = db_client.post(f"{BASE}/memory-rules/{rid}/decision", headers=auth(seed.TEACHER),
                              json={"decision": "activate"})
    assert response.status_code == 404 and response.json()["error"]["code"] == "NOT_FOUND"
    with seeded_db.connect() as connection:
        assert connection.scalar(text("SELECT status FROM memory_rules WHERE id=:id"), {"id": rid}) == "proposed"
        assert connection.execute(text("""
            SELECT org_id,request_id,card_id FROM events WHERE action='permission_denied' ORDER BY id DESC LIMIT 1
        """)).one() == (seed.ORG, None, None)
