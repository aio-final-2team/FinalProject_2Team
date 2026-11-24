"""새 협업 그래프가 실제 카드에 결과를 저장하는지 확인한다."""

from dataclasses import replace

from sqlalchemy import text

from app.modules.requests import runner
from tests.integration.db.test_request_lock_timeout import cards_of, submit, use_model


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


def test_collaboration_memory_failure_blanks_complaint(db_client, seeded_db, monkeypatch):
    from tests.integration.db.test_request_graph_t29 import graph_request
    from app.modules.requests import graph_agent

    enable_graph(monkeypatch)

    def broken(_):
        raise RuntimeError("[TEST] 기억 읽기 실패")

    monkeypatch.setattr(graph_agent, "_load_request_memory", broken)
    request_id, _ = graph_request(db_client, monkeypatch, "complaint")
    [card] = cards_of(seeded_db, request_id)
    assert card["draft"]["text"] == ""
    assert card["check_result"]["passed"] is False
