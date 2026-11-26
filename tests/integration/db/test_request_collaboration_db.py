"""새 협업 그래프가 실제 카드에 결과를 저장하는지 확인한다."""

from dataclasses import replace

import pytest
from sqlalchemy import text

from app.modules.requests import runner
from tests.integration.db.test_request_lock_timeout import cards_of, submit, use_model


@pytest.mark.parametrize("body, citations, no_evidence, conflict, expected_problem", [
    ("겨울방학은 언제부터 언제까지예요?",
     [("겨울방학 안내", "12월 24일"), ("2학기 학사 일정표", "2026-12-26")],
     False, True, "자료끼리 내용이 달라요."),
    ("소풍 준비물이 뭐예요?",
     [("10월 가정통신문 — 가을 소풍과 건강검진", "가을 소풍"),
      ("2학기 학사 일정표", "가을 소풍")],
     True, False, "자료에서 근거를 찾지 못했어요."),
    ("김장 준비물이 뭐예요?",
     [("김장 체험 안내 (만 4·5세반)", "앞치마")],
     False, False, None),
])
def test_collaboration_matches_original_card_on_conflict_and_missing_evidence(
        db_client, seeded_db, monkeypatch, body, citations, no_evidence, conflict, expected_problem):
    from db.seeds.documents import seed_documents
    from tests.integration.db.test_answer_t33 import Writer, create_card, setup_graph

    with seeded_db.begin() as connection:
        seed_documents(connection)
        evidence = []
        for title, quote in citations:
            chunk_id = connection.scalar(text("""
                SELECT ch.id FROM document_chunks ch JOIN documents d ON d.id=ch.document_id
                WHERE d.title=:title AND ch.content LIKE :quote ORDER BY ch.id LIMIT 1
            """), {"title": title, "quote": f"%{quote}%"})
            assert chunk_id is not None
            evidence.append({"chunk_id": chunk_id, "quote": quote})
    setup_graph(seeded_db, monkeypatch, {"text": "[TEST] 모델 초안", "evidence": evidence,
        "no_evidence": no_evidence, "conflict": conflict})
    monkeypatch.setattr(runner, "settings", replace(runner.settings,
        request_agent="app.modules.requests.graph_agent:run_request"))
    old_card, old_evidence, _ = create_card(db_client, body)
    assert [role for role, _ in Writer.calls] == (["DOCUMENT"] if expected_problem else ["DOCUMENT", "CHECKER"])
    enable_graph(monkeypatch)
    Writer.calls = []
    new_card, new_evidence, _ = create_card(db_client, body)
    assert [role for role, _ in Writer.calls] == (["DOCUMENT"] if expected_problem else ["DOCUMENT", "CHECKER"])
    assert len(old_evidence) == len(new_evidence) == len(citations)
    assert [(item["quote"], item["score"]) for item in old_evidence] == [
        (item["quote"], item["score"]) for item in new_evidence]
    assert old_card["draft"] == new_card["draft"]
    assert old_card["check_result"] == new_card["check_result"]
    assert old_card["draft"].get("conflict") is conflict
    if expected_problem:
        assert old_card["draft"]["text"] == new_card["draft"]["text"] == ""
        assert old_card["check_result"]["issues"] == [{"field": "출처", "problem": expected_problem}]


def enable_graph(monkeypatch):
    monkeypatch.setenv("REQUEST_COLLAB_GRAPH", "1")
    monkeypatch.setattr(runner, "settings", replace(runner.settings,
        request_agent="app.modules.requests.graph_agent:run_request"))


def test_collaboration_saves_checked_draft_and_evidence(db_client, seeded_db, monkeypatch):
    enable_graph(monkeypatch)
    seen = []
    use_model(seeded_db, monkeypatch, seen.append)
    request_id = submit(db_client)
    [card] = cards_of(seeded_db, request_id)
    assert seen == ["DOCUMENT", "CHECKER"]
    assert card["draft"]["text"] == "[TEST] 자료 확인 답"
    assert card["check_result"] == {"passed": True, "issues": [], "attempt": 1}
    with seeded_db.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM card_evidence WHERE card_id=:id"),
                                 {"id": card["id"]}) == 1


def test_collaboration_missing_evidence_requires_teacher_edit(db_client, seeded_db, monkeypatch):
    enable_graph(monkeypatch)
    use_model(seeded_db, monkeypatch, lambda _: None)
    from app.modules.documents import search
    monkeypatch.setattr(search, "search_documents", lambda *args, **kwargs: {"chunks": []})
    request_id = submit(db_client)
    [card] = cards_of(seeded_db, request_id)
    assert card["draft"]["text"] == ""
    assert card["check_result"]["passed"] is False
    from app.core.auth import issue_token
    from app.core import users
    from app.mock import seed
    teacher = {"Authorization": "Bearer " + issue_token(users.get_user(seed.TEACHER))}
    base = f"/api/v1/cards/{card['id']}/decisions"
    blocked = db_client.post(base, headers=teacher,
                             json={"version": card["version"], "decision": "approve"})
    assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "INVALID_TRANSITION"
    edited = db_client.post(base, headers=teacher, json={"version": card["version"],
                            "decision": "edit_approve", "edited_content": {"text": "[TEST] 담임 답변"}})
    assert edited.status_code == 200


def test_old_and_new_graphs_match_fake_answer(db_client, seeded_db, monkeypatch):
    use_model(seeded_db, monkeypatch, lambda _: None)
    monkeypatch.setattr(runner, "settings", replace(runner.settings,
        request_agent="app.modules.requests.graph_agent:run_request"))
    old_id = submit(db_client)
    enable_graph(monkeypatch)
    new_id = submit(db_client)
    old_card, new_card = cards_of(seeded_db, old_id)[0], cards_of(seeded_db, new_id)[0]
    assert (old_card["kind"], old_card["status"], old_card["draft"], old_card["check_result"]) == (
        new_card["kind"], new_card["status"], new_card["draft"], new_card["check_result"])
    with seeded_db.connect() as connection:
        def evidence(card):
            return connection.scalars(text("SELECT chunk_id FROM card_evidence WHERE card_id=:id ORDER BY rank"),
                                      {"id": card["id"]}).all()
        assert evidence(old_card) == evidence(new_card)


def test_collaboration_model_runs_without_request_lock(db_client, seeded_db, monkeypatch):
    from app.core.db import get_engine
    from sqlalchemy.exc import OperationalError

    enable_graph(monkeypatch)
    seen = []

    def probe(role):
        checked_out = get_engine().pool.checkedout()
        with seeded_db.connect() as connection:
            try:
                connection.execute(text("SELECT id FROM requests WHERE body=:body FOR UPDATE NOWAIT"),
                                   {"body": "[TEST] 겨울방학 언제부터인가요?"})
                lockable = True
            except OperationalError:
                lockable = False
        seen.append((role, checked_out, lockable))

    use_model(seeded_db, monkeypatch, probe)
    submit(db_client)
    assert seen == [("DOCUMENT", 0, True), ("CHECKER", 0, True)]


def test_collaboration_timeout_keeps_empty_card(db_client, seeded_db, monkeypatch):
    import threading
    from time import sleep

    enable_graph(monkeypatch)
    entered, release = threading.Event(), threading.Event()

    def hold(role):
        if role == "DOCUMENT":
            entered.set()
            release.wait(10)

    use_model(seeded_db, monkeypatch, hold)
    monkeypatch.setattr(runner, "AI_TIMEOUT_SECONDS", 0.3)
    request_id = submit(db_client)
    assert entered.wait(5)
    [card] = cards_of(seeded_db, request_id)
    assert not card["draft"].get("text")
    release.set()
    sleep(0.3)
    [late] = cards_of(seeded_db, request_id)
    assert late["id"] == card["id"] and not late["draft"].get("text")


def test_collaboration_memory_failure_keeps_complaint_draft(db_client, seeded_db, monkeypatch):
    from tests.integration.db.test_request_collaboration_complaint import setup, submit as complaint_submit
    from app.modules.requests import graph_agent

    setup(seeded_db, monkeypatch)

    def broken(_):
        raise RuntimeError("[TEST] 기억 읽기 실패")

    monkeypatch.setattr(graph_agent, "_load_request_memory", broken)
    cards, status, evidence = complaint_submit(db_client, seeded_db)
    assert status == "awaiting_review" and evidence
    assert cards[0]["draft"]["text"] == "[TEST] 행정실 안내를 확인해 주세요."
    assert cards[0]["check_result"]["memory_unavailable"] is True


def test_collaboration_checkpoint_excludes_content_and_resumes(db_client, seeded_db, monkeypatch):
    from app.core import users
    from app.core.auth import issue_token
    from app.mock import seed
    from app.modules.requests import graph_agent

    enable_graph(monkeypatch)
    use_model(seeded_db, monkeypatch, lambda _: None)
    tone = "[TEST] 체크포인트에 남기지 않을 담임 말투"
    with seeded_db.begin() as connection:
        connection.execute(text("""
            INSERT INTO memories(org_id,owner_id,kind,content)
            SELECT org_id,id,'tone',:tone FROM users WHERE id=:teacher
        """), {"tone": tone, "teacher": seed.TEACHER})
    request_id = submit(db_client)
    [card] = cards_of(seeded_db, request_id)
    thread = graph_agent.thread_id(request_id)

    def checkpoint_bytes():
        with seeded_db.connect() as connection:
            data = []
            for table, column in (("checkpoints", "checkpoint"), ("checkpoints", "metadata"),
                                  ("checkpoint_blobs", "blob"), ("checkpoint_writes", "blob")):
                rows = connection.execute(text(f"SELECT {column} FROM {table} WHERE thread_id=:thread"),
                                          {"thread": thread}).scalars()
                data.extend(value if isinstance(value, bytes) else str(value).encode("utf-8")
                            for value in rows if value is not None)
        return b" ".join(data)

    stored = checkpoint_bytes()
    assert stored
    for secret in (tone, "[TEST] 자료 확인 답", "12월 24일", "[TEST] 겨울방학 언제부터인가요?"):
        assert secret.encode("utf-8") not in stored
    assert card["draft"]["text"] == "[TEST] 자료 확인 답"
    teacher = {"Authorization": "Bearer " + issue_token(users.get_user(seed.TEACHER))}
    response = db_client.post(f"/api/v1/cards/{card['id']}/decisions", headers=teacher,
                              json={"version": card["version"], "decision": "approve"})
    assert response.status_code == 200, response.text
    assert graph_agent.resume_request(card["id"]) is None
    assert tone.encode("utf-8") not in checkpoint_bytes()
