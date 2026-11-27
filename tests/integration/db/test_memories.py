"""기억 제안의 동시 임계값·결정 원자성·승인 전 상담 적용 금지를 검증해요."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.mock import seed
from app.core.schedule import KST
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


def test_rule_decision_failure_rolls_back_card_approval_and_rule(db_client, seeded_db, monkeypatch):
    from app.modules.cards import cards

    for _ in range(3):
        _, cid = create(db_client, "inquiry")
        assert reject(db_client, cid).status_code == 200
    with seeded_db.connect() as connection:
        cid, rid = connection.execute(text("SELECT id,subject_id FROM cards WHERE kind='rule_proposal'")).one()
        tables = ("memories", "memory_rules", "cards", "approvals", "events", "notifications")
        before = {table: connection.scalar(text(f"SELECT count(*) FROM {table}")) for table in tables}

    def fail(*args, **kwargs):
        raise RuntimeError("[TEST] 이력 저장 실패")

    monkeypatch.setattr(cards, "record", fail)
    response = db_client.post(f"{BASE}/memory-rules/{rid}/decision", headers=auth(seed.TEACHER),
                              json={"decision": "activate"})
    assert response.status_code == 500 and response.json()["error"]["code"] == "INTERNAL_ERROR"
    with seeded_db.connect() as connection:
        assert {table: connection.scalar(text(f"SELECT count(*) FROM {table}")) for table in tables} == before
        assert connection.execute(text("SELECT status,version FROM cards WHERE id=:id"), {"id": cid}).one() == (
            "pending", 1)
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


def test_memory_timestamp_after_decline_uses_save_time_even_if_transaction_started_before(db_client, seeded_db):
    from app.mock import store
    from app.modules.memories.memories import remember_rejection
    for _ in range(3):
        _, cid = create(db_client, "inquiry")
        assert reject(db_client, cid).status_code == 200
    _, source = create(db_client, "inquiry")
    with seeded_db.begin() as connection:
        started = connection.scalar(text("SELECT now()"))
        rid = connection.scalar(text("SELECT id FROM memory_rules WHERE reason_code='tone'"))
        card = dict(connection.execute(text("SELECT * FROM cards WHERE id=:id"), {"id": source}).mappings().one())
        response = db_client.post(f"{BASE}/memory-rules/{rid}/decision", headers=auth(seed.TEACHER),
                                  json={"decision": "decline"})
        assert response.status_code == 200
        remember_rejection(connection, store.get_user(seed.TEACHER), card, "reject", "tone", "[TEST] 새 기억")
        decided = connection.scalar(text("SELECT decided_at FROM memory_rules WHERE id=:id"), {"id": rid})
        saved = connection.scalar(text("SELECT created_at FROM memories WHERE source_card_id=:id"), {"id": source})
        assert started < decided < saved
    for _ in range(2):
        _, cid = create(db_client, "inquiry")
        assert reject(db_client, cid).status_code == 200
    with seeded_db.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM memory_rules WHERE status='proposed' AND reason_code='tone'")) == 1


def test_rule_notification_off_hours_and_duplicate_event_replay(db_client, seeded_db):
    from app.modules.notifications.notifications import notify_event
    for _ in range(3):
        _, cid = create(db_client, "inquiry")
        assert reject(db_client, cid).status_code == 200
    with seeded_db.begin() as connection:
        card = dict(connection.execute(text("SELECT * FROM cards WHERE kind='rule_proposal'")).mappings().one())
        event = dict(connection.execute(text("SELECT * FROM events WHERE card_id=:id AND action='created'"),
                                        {"id": card["id"]}).mappings().one())
        connection.execute(text("DELETE FROM notifications WHERE card_id=:id"), {"id": card["id"]})
        event["created_at"] = datetime(2026, 11, 20, 20, tzinfo=KST)  # 금요일 퇴근 뒤
        for _ in range(2):
            notify_event(connection, event, None, card)
        rows = connection.execute(text("SELECT recipient_id,kind,request_id,deliver_after FROM notifications WHERE card_id=:id"),
                                  {"id": card["id"]}).all()
        assert rows == [(seed.TEACHER, "new_card", None, datetime(2026, 11, 23, 9, tzinfo=KST))]


def fake_memory_model(monkeypatch, reply):
    import json
    from types import SimpleNamespace
    from app.modules.memories import memories
    monkeypatch.setenv("LLM_MODEL_MEMORY", "fake-memory")
    seen = []

    def answer(system, user):
        seen.append(json.loads(user))
        if isinstance(reply, Exception):
            raise reply
        return reply
    monkeypatch.setattr(memories, "OpenAIModel", lambda role: SimpleNamespace(json=answer))
    return seen


def reject_with(client, code, reason_text):
    _, cid = create(client, "inquiry")
    response = client.post(f"{BASE}/cards/{cid}/decisions", headers=auth(seed.TEACHER),
                           json={"version": 1, "decision": "reject", "reason_code": code, "reason_text": reason_text})
    assert response.status_code == 200, response.text


def test_ai_rule_from_rejection_texts_feeds_consultation_time_after_activation(db_client, seeded_db, monkeypatch):
    """[TEST] 기억 AI가 쌓인 거절 글로 규칙 문장·시간 조건을 제안하고, 켠 뒤 상담 후보가 그 값을 받아요."""
    seen = fake_memory_model(monkeypatch, {"rule": {"rule_text": "[TEST] 상담은 14시 이후에만 잡아요",
                                                    "rule_json": {"after": "14:00", "reason_code": "tone"}}})
    for index in range(3):
        reject_with(db_client, "slot_unavailable", f"[TEST] 오전은 수업이라 어려워요 {index}")
    assert len(seen) == 1 and seen[0]["rejections"]["reason_code"] == "slot_unavailable"
    assert sorted(seen[0]["rejections"]["texts"]) == [f"[TEST] 오전은 수업이라 어려워요 {i}" for i in range(3)]
    with seeded_db.connect() as connection:
        rid, rule_text, rule_json = connection.execute(text(
            "SELECT id,rule_text,rule_json FROM memory_rules WHERE reason_code='slot_unavailable'")).one()
    assert rule_text == "[TEST] 상담은 14시 이후에만 잡아요"
    assert rule_json == {"reason_code": "slot_unavailable", "after": "14:00"}
    assert db_client.post(f"{BASE}/memory-rules/{rid}/decision", headers=auth(seed.TEACHER),
                          json={"decision": "activate"}).status_code == 200
    _, cid = create(db_client, "consultation")
    with seeded_db.connect() as connection:
        starts = connection.scalars(text("SELECT lower(period) FROM consultation_slots WHERE card_id=:id"),
                                    {"id": cid}).all()
        assert len(starts) == 3 and all(s.astimezone(KST).hour >= 14 for s in starts)
        from app.modules.memories.memories import active_rules
        assert [r["id"] for r in active_rules(connection, seed.ORG, seed.TEACHER)] == [rid]
        assert active_rules(connection, seed.ORG, seed.TEACHER, ("tone",)) == []


@pytest.mark.parametrize("code,reply,expected,failed", [
    ("other", {"rule": {"rule_text": "[TEST] 답 끝에 연락 방법을 붙여요", "rule_json": {}}},
     "[TEST] 답 끝에 연락 방법을 붙여요", False),
    ("tone", {"rule": None}, None, False),
    ("tone", RuntimeError("[TEST] 모델 오류"), "fallback", True),
    ("tone", {"rule": {"rule_text": "[TEST] 하늘이 답은 짧게 써요", "rule_json": {}}}, "fallback", True),
    ("other", RuntimeError("[TEST] 모델 오류"), None, True),
])
def test_ai_rule_judges_sameness_and_model_failure_uses_fixed_fallback(db_client, seeded_db, monkeypatch,
                                                                      code, reply, expected, failed):
    """[TEST] 공통 규칙인지는 AI가 정해요(other 포함). 모델 실패·선 위반은 코드별 고정 문장 대역이에요."""
    from app.core.constants import REJECTION_RULE_TEXTS
    seen = fake_memory_model(monkeypatch, reply)
    for _ in range(3):
        reject_with(db_client, code, "[TEST] 답을 더 짧게 해 주세요")
    assert len(seen) == 1
    with seeded_db.connect() as connection:
        texts = connection.scalars(text("SELECT rule_text FROM memory_rules WHERE reason_code=:code"),
                                   {"code": code}).all()
        assert texts == ([] if expected is None else [REJECTION_RULE_TEXTS[code] if expected == "fallback" else expected])
        assert connection.scalar(text("""SELECT count(*) FROM events WHERE action='tool_failed'
                                         AND detail->>'tool'='suggest_rule'""")) == (1 if failed else 0)
