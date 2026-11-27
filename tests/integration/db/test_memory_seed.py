"""가상 기억의 삭제 보존·권한·실제 상담 적용과 근거 연결을 확인해요."""

from collections import Counter
from datetime import datetime, timedelta
import re

import pytest
from sqlalchemy import text

from app.core.memory_rules import mask_child_names
from app.core.schedule import KST
from app.mock import seed
from db.seeds.documents import seed_documents
from db.seeds import memories
from tests.integration.db.test_cards import BASE, auth, create


@pytest.fixture
def memory_seed(seeded_db, monkeypatch):
    # DB 기능 시험의 벡터 대역. 실제 모델 적재는 EMBEDDING_MODEL을 켠 별도 실행으로 확인해요.
    monkeypatch.setattr(memories.embedding, "embed", lambda texts: [[1.0] + [0.0]*1023 for _ in texts])
    with seeded_db.begin() as connection:
        seed_documents(connection)
        assert memories.seed_memories(connection) == 30
    return seeded_db


def test_counts_repeat_and_preserve_deleted_memories_and_decisions(memory_seed):
    tables = ("memories", "memory_rules", "saved_answers", "saved_answer_sources", "requests", "cards",
              "approvals", "events", "request_messages", "card_evidence", "notifications")
    with memory_seed.begin() as connection:
        before = {table: connection.scalar(text(f"SELECT count(*) FROM {table}")) for table in tables}
        assert before["memories"] == 69 and before["memory_rules"] == 5 and before["saved_answers"] == 30
        assert connection.execute(text("SELECT status,count(*) FROM memory_rules GROUP BY status ORDER BY status")).all() == [
            ("active", 3), ("declined", 1), ("proposed", 1)]
        assert connection.execute(text("SELECT classroom_id,count(*) FROM saved_answers GROUP BY classroom_id "
                                       "ORDER BY classroom_id NULLS LAST")).all() == [(seed.CLASS_STAR, 20), (None, 10)]
        assert memories.seed_memories(connection) == 0
        assert {table: connection.scalar(text(f"SELECT count(*) FROM {table}")) for table in tables} == before
        connection.execute(text("UPDATE memories SET deleted_at=now(),content='',structured='{}' WHERE id=990200001"))
        connection.execute(text("UPDATE saved_answers SET status='off'"))
        connection.execute(text("UPDATE memory_rules SET status=CASE WHEN status='active' THEN 'off' "
                                "ELSE 'declined' END,decided_at=now()"))
        assert memories.seed_memories(connection) == 0
        assert {table: connection.scalar(text(f"SELECT count(*) FROM {table}")) for table in tables} == before
        assert connection.execute(text("SELECT content,structured,deleted_at IS NOT NULL FROM memories "
                                       "WHERE id=990200001")).one() == ("", {}, True)
        assert connection.scalar(text("SELECT count(*) FROM saved_answers WHERE status='off'")) == 30
        assert connection.scalar(text("SELECT count(*) FROM memory_rules WHERE status IN ('active','proposed')")) == 0


def test_owner_only_api_and_completed_history(db_client, memory_seed, monkeypatch):
    from app import backend
    from app.modules.memories import memories as module

    monkeypatch.setattr(backend, "memories", module)
    for owner, expected in ((seed.TEACHER, 30), (seed.TEACHER_OTHER, 16)):
        response = db_client.get(BASE + "/memories?size=100", headers=auth(owner))
        assert response.status_code == 200, response.text
        rows = response.json()["items"]
        assert len(rows) == response.json()["total"] == expected
        with memory_seed.connect() as connection:
            owned = set(connection.scalars(text("SELECT id FROM memories WHERE owner_id=:owner"), {"owner": owner}))
        assert {row["id"] for row in rows} == owned
    # 현재 경로는 담임만 허용해요. 시드 범위에서는 권한을 바꾸지 않고 403 경계를 명시해요.
    response = db_client.get(BASE + "/memories?size=100", headers=auth(seed.PARENT))
    assert response.status_code == 403 and response.json()["error"]["code"] == "FORBIDDEN_ROLE"
    from app.core.users import get_user
    rows = module.list_memories(get_user(seed.PARENT), None, 1, 100, "-created_at")["items"]
    assert len(rows) == 2 and {row["kind"] for row in rows} == {"preference"}
    inbox = db_client.get(BASE + "/cards?filter=done&size=100", headers=auth(seed.TEACHER))
    assert inbox.status_code == 200, inbox.text
    assert len(inbox.json()["items"]) == 30
    proposals = db_client.get(BASE + "/cards?kind=rule_proposal&size=100", headers=auth(seed.TEACHER))
    assert len(proposals.json()["items"]) == 1
    response = db_client.delete(BASE + "/memories/990200001", headers=auth(seed.TEACHER))
    assert response.status_code == 204, response.text
    with memory_seed.begin() as connection:
        assert memories.seed_memories(connection) == 0
        assert connection.scalar(text("SELECT deleted_at IS NOT NULL FROM memories WHERE id=990200001"))
    with memory_seed.connect() as connection:
        assert connection.scalar(text("""
            SELECT count(*) FROM memories m JOIN approvals a ON a.card_id=m.source_card_id
            WHERE m.owner_id=:owner AND m.kind='tone' AND m.structured->>'source'='edit_approve'
              AND a.decision='edit_approve' AND a.edited_content->>'text' IS NOT NULL
        """), {"owner": seed.TEACHER}) == 9
        earliest, latest = connection.execute(text("SELECT min(created_at),max(created_at) FROM saved_answers")).one()
        assert datetime.now(KST)-timedelta(days=21) < earliest < latest < datetime.now(KST)


def test_active_rule_restricts_real_consultation_candidates(db_client, memory_seed):
    from app.modules.consultations.slots import find_consult_slots

    _, cid = create(db_client, "consultation")
    with memory_seed.connect() as connection:
        slots = connection.scalars(text("SELECT period FROM consultation_slots WHERE card_id=:id"), {"id": cid}).all()
        assert len(slots) == 3
        assert all(14*60 <= slot.lower.astimezone(KST).hour*60+slot.lower.minute
                   and slot.upper.astimezone(KST).hour*60+slot.upper.minute <= 17*60 for slot in slots)
        rules = connection.scalars(text("SELECT rule_json FROM memory_rules WHERE owner_id=:owner "
                                        "AND status='active' AND reason_code='slot_unavailable'"),
                                   {"owner": seed.TEACHER}).all()
        late = find_consult_slots(connection, seed.TEACHER, slots[0].lower.astimezone(KST).date(),
                                  org_id=seed.ORG, rules=rules, preferred_times="17:30 이후")
        assert late and all(row["end"].astimezone(KST).hour*60+row["end"].minute <= 17*60 for row in late)
    # 활성 규칙을 끄면 같은 계산이 오전 후보를 다시 내놓아요.
    with memory_seed.begin() as connection:
        connection.execute(text("UPDATE memory_rules SET status='off' WHERE owner_id=:owner "
                                "AND reason_code='slot_unavailable'"), {"owner": seed.TEACHER})
    _, cid = create(db_client, "consultation")
    with memory_seed.connect() as connection:
        slots = connection.scalars(text("SELECT period FROM consultation_slots WHERE card_id=:id"), {"id": cid}).all()
        assert len(slots) == 3 and all(slot.lower.astimezone(KST).hour < 14 for slot in slots)


def test_fixture_privacy_counts_and_saved_answer_facts(memory_seed):
    data = memories.DATA
    assert data["is_virtual"] is True
    counts = Counter((row["owner"], row["kind"]) for row in data["memories"])
    assert [counts["teacher01", kind] for kind in ("tone", "preference", "rejection_reason")] == [10, 6, 14]
    assert [counts["teacher02", kind] for kind in ("tone", "preference", "rejection_reason")] == [6, 4, 6]
    assert sum(owner.startswith("parent") for owner, _ in counts) == 10
    for row in data["memories"]:
        assert mask_child_names(row["content"], [child["display_name"] for child in seed.CHILDREN]) == row["content"]
        assert not re.search(r"건강|알레르기|가정사|계좌|\d{2,3}-\d{3,4}-\d{4}", row["content"])
        if row["kind"] == "tone":
            assert len(row["content"]) <= 80
    with memory_seed.connect() as connection:
        rows = connection.execute(text("""
            SELECT a.question,a.answer,c.content,e.quote,ap.decision,ap.edited_content
            FROM saved_answers a JOIN saved_answer_sources s ON s.saved_answer_id=a.id
            JOIN card_evidence e ON e.card_id=a.source_card_id
            JOIN document_chunks c ON c.id=e.chunk_id AND c.document_id=s.document_id
            JOIN approvals ap ON ap.card_id=a.source_card_id
        """)).mappings().all()
        assert len(rows) == 30
        for row in rows:
            assert row["quote"] in row["content"]
            for fact in re.findall(r"\d{1,2}:\d{2}|\d+(?:년|월|일|시|분|명|벌)", row["answer"]):
                assert fact in row["content"], (row["question"], fact)
            for weekday in re.findall(r"([월화수목금토일])요일", row["answer"]):
                assert f"| {weekday} |" in row["content"] or f"({weekday})" in row["content"]
            assert row["answer"].endswith("궁금한 점은 언제든 알려 주세요.")
            if row["decision"] == "edit_approve":
                assert row["edited_content"]["text"] == row["answer"]


def test_missing_embedding_warns_once_and_can_fill_later(seeded_db, monkeypatch, capsys):
    monkeypatch.delenv("EMBEDDING_MODEL", raising=False)
    with seeded_db.begin() as connection:
        seed_documents(connection)
        assert memories.seed_memories(connection) == 0
        assert connection.scalar(text("SELECT count(*) FROM saved_answers")) == 0
        assert connection.scalar(text("SELECT count(*) FROM memories")) == 69
        assert connection.scalar(text("SELECT count(*) FROM approvals WHERE decision='edit_approve'")) == 10
        assert capsys.readouterr().out.count("경고:") == 1
        monkeypatch.setattr(memories.embedding, "embed", lambda texts: [[1.0] + [0.0]*1023 for _ in texts])
        assert memories.seed_memories(connection) == 30
        assert connection.scalar(text("SELECT count(*) FROM cards WHERE kind='reply_draft'")) == 30


def test_missing_source_document_never_creates_unsupported_answers(seeded_db, monkeypatch):
    monkeypatch.setattr(memories.embedding, "embed", lambda texts: [[1.0] + [0.0]*1023 for _ in texts])
    with seeded_db.begin() as connection:
        assert memories.seed_memories(connection) == 0
        assert connection.scalar(text("SELECT count(*) FROM saved_answers")) == 0
        assert connection.scalar(text("SELECT count(*) FROM cards WHERE kind='reply_draft'")) == 0
        assert connection.scalar(text("SELECT count(*) FROM memories WHERE source_card_id IS NOT NULL")) == 0
        seed_documents(connection)
        assert memories.seed_memories(connection) == 30
        assert connection.scalar(text("SELECT count(*) FROM memories WHERE source_card_id IS NOT NULL")) == 10
