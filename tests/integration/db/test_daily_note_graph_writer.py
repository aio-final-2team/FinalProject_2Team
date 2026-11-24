"""실제 그래프와 DB runner를 잇되 writer·checker는 가짜 모델만 쓴다."""

from dataclasses import replace
from datetime import datetime
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import UUID

import pytest
from sqlalchemy import text

from agents import llm
from agents.graphs import daily_note as graph
from agents.llm import ModelError, OpenAIModel
from app.core.auth import issue_token
from app.core import users
from app.core.schedule import KST
from app.mock import seed
from app.modules.daily_notes import runner
from tests.integration.api.helpers import BASE


@pytest.fixture
def graph_models(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("[TEST] 실제 모델 호출 금지")

    monkeypatch.setattr(OpenAIModel, "json", forbidden)
    monkeypatch.setattr(runner, "settings", replace(runner.settings, daily_note_writer="graph"))

    def install(writer, checker):
        class FakeModel:
            def __init__(self, answer):
                self.answer, self.inputs = answer, []

            def json(self, system, user):
                value = json.loads(user)
                self.inputs.append(value)
                return self.answer(value)

        models = {"DOCUMENT": FakeModel(writer), "CHECKER": FakeModel(checker)}
        monkeypatch.setattr(llm, "OpenAIModel", lambda role: models[role])
        return models

    return install


def echo_writer(value):
    return {"child": value["child_memo"] or None,
            "requests": [{"request_id": r["request_id"], "value": r["text"]} for r in value["requests"]]}


@pytest.fixture
def teacher(db_client):
    return {"Authorization": "Bearer " + issue_token(users.get_user(seed.TEACHER))}


def batch():
    return {"classroom_id": str(seed.CLASS_STAR), "note_date": datetime.now(KST).date().isoformat()}


def todays_requests():
    now = datetime.now(KST)
    return [r for r in seed.DEMO_NOTE_REQUESTS if r.get("created_at", now).astimezone(KST).date() == now.date()]


def draft(db_client, teacher, memos=()):
    return db_client.post(BASE + "/daily-notes/drafts", headers=teacher, json={
        **batch(), "activities": "[TEST] 블록 놀이", "supplies": "수건", "child_memos": list(memos)})


def notes(db_client, teacher, response):
    assert response.status_code == 202, response.text
    status = db_client.get(f"{BASE}/daily-notes/drafts/{response.json()['input_id']}", headers=teacher)
    assert status.json()["draft_status"] == "succeeded", status.text
    listed = db_client.get(BASE + "/daily-notes", headers=teacher,
                           params={"date": batch()["note_date"], "classroom_id": str(seed.CLASS_STAR)})
    assert listed.status_code == 200, listed.text
    assert len(listed.json()["items"]) == 20
    return listed.json()["items"]


def test_graph_stores_unique_check_ids_then_resolves_and_sends(db_client, teacher, seeded_db, graph_models):
    def sensitive(value):
        return {"checks": [{"item_key": "child", "kind": "sensitive", "problem": "[TEST] 메모 확인",
                            "sentence": value["child_memo"]}] if value["child_memo"] else []}

    models = graph_models(echo_writer, sensitive)
    listed = notes(db_client, teacher, draft(db_client, teacher, [
        {"child_id": str(seed.CHILD), "memo": "[TEST] 열이 남"},
        {"child_id": str(seed.demo_id("503")), "memo": "[TEST] 약 먹음"}]))
    checked = [n for n in listed if n["open_checks"]]
    assert len(checked) == 2 and all(n["status"] == "needs_check" for n in checked)
    checks = [n["open_checks"][0] for n in checked]
    assert len({c["id"] for c in checks}) == 2
    assert all(UUID(c["id"]).version == 4 and c["request_id"] is None for c in checks)
    assert all(c["kind"] == "sensitive" and c["problem"] == "[TEST] 메모 확인" for c in checks)
    inputs = models["DOCUMENT"].inputs
    expected_requests = todays_requests()
    expected_children = {str(r["child_id"]) for r in expected_requests} | {str(seed.CHILD), str(seed.demo_id("503"))}
    assert len(inputs) == len(models["CHECKER"].inputs) == len(expected_children)
    assert all(v["classroom"]["id"] == str(seed.CLASS_STAR) and v["note_date"] == batch()["note_date"] for v in inputs)
    assert {r["request_id"] for v in inputs for r in v["requests"]} == {str(r["id"]) for r in expected_requests}
    with seeded_db.connect() as connection:
        stored = connection.execute(text("SELECT open_checks FROM daily_notes WHERE status='needs_check'"))
        assert {row[0][0]["id"] for row in stored} == {c["id"] for c in checks}
    target = checked[0]
    old_id = db_client.patch(f"{BASE}/daily-notes/{target['id']}", headers=teacher,
                             json={"confirm": True, "resolved_checks": ["c1"]})
    assert old_id.status_code == 409
    for note in listed:
        resolved = db_client.patch(f"{BASE}/daily-notes/{note['id']}", headers=teacher, json={
            "confirm": True, "resolved_checks": [c["id"] for c in note["open_checks"]]})
        assert resolved.status_code == 200, resolved.text
        assert resolved.json()["note"]["status"] == "ready" and resolved.json()["note"]["open_checks"] == []
    sent = db_client.post(BASE + "/daily-notes/send", headers=teacher, json=batch())
    assert sent.status_code == 200 and sent.json()["sent_count"] == 20
    with seeded_db.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM notifications WHERE kind='note_sent'")) == 18


def test_graph_keeps_request_missed_reference_after_returns(db_client, teacher, graph_models):
    models = graph_models(lambda value: {"child": None, "requests": []}, lambda value: {"checks": []})
    listed = notes(db_client, teacher, draft(db_client, teacher))
    checks = [c for n in listed for c in n["open_checks"]]
    expected_requests = todays_requests()
    missed = [c for c in checks if c["kind"] == "request_missed"]
    # 두 번 돌려보내도 요청이 빠져 있으면 아이마다 return_limit 확인이 하나씩 더 붙는다.
    limit_children = [n["child_id"] for n in listed for c in n["open_checks"] if c["kind"] == "return_limit"]
    assert len(missed) == len(expected_requests) and len(missed) + len(limit_children) == len(checks)
    assert sorted(limit_children) == sorted({str(r["child_id"]) for r in expected_requests})
    assert {c["request_id"] for c in missed} == {str(r["id"]) for r in expected_requests}
    assert all(UUID(c["id"]).version == 4 and c["sentence"] is None for c in checks)
    assert len(models["DOCUMENT"].inputs) == len(models["CHECKER"].inputs) == 3 * len({r["child_id"] for r in expected_requests})
    assert all(line["key"] != "child" for n in listed for line in n["content"]["items"])
    blocked = db_client.post(BASE + "/daily-notes/send", headers=teacher, json=batch())
    assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "NOTE_BATCH_BLOCKED"


@pytest.mark.parametrize("failed_role,kind,keeps_child", [
    ("DOCUMENT", "draft_failed", False), ("CHECKER", "check_failed", True)])
def test_graph_model_failure_isolated_to_one_child(db_client, teacher, graph_models, failed_role, kind, keeps_child):
    def answer(role, value):
        if role == failed_role and value["child_memo"] == "[TEST] 실패":
            raise ModelError("[TEST] 가짜 모델 실패")
        return echo_writer(value) if role == "DOCUMENT" else {"checks": []}

    models = graph_models(lambda value: answer("DOCUMENT", value), lambda value: answer("CHECKER", value))
    listed = notes(db_client, teacher, draft(db_client, teacher, [
        {"child_id": str(seed.CHILD), "memo": "[TEST] 실패"},
        {"child_id": str(seed.demo_id("5401")), "memo": "[TEST] 성공 메모"}]))
    child = next(n for n in listed if n["child_id"] == str(seed.CHILD))
    [check] = child["open_checks"]
    assert check["kind"] == kind and check["request_id"] is None and UUID(check["id"]).version == 4
    assert child["status"] == "needs_check"
    assert any(line["key"] == "child" for line in child["content"]["items"]) is keeps_child
    success = next(n for n in listed if n["child_id"] == str(seed.demo_id("5401")))
    assert success["status"] == "draft" and success["open_checks"] == []
    assert any(line["value"] == "[TEST] 성공 메모" for line in success["content"]["items"])
    # 전송 실패 재시도는 llm.py(API 6.2)가 하고, 그래프는 같은 모델 오류를 다시 묻지 않아요(#293)
    assert sum(v["child_memo"] == "[TEST] 실패" for v in models[failed_role].inputs) == 1


def test_medication_code_check_and_checker_failure_are_both_saved(db_client, teacher, seeded_db, graph_models):
    medication_id = seed.demo_id("7201")
    child_id = seed.demo_id("5412")
    with seeded_db.begin() as connection:
        connection.execute(text("UPDATE requests SET created_at=:at WHERE id=:id"),
                           {"at": datetime.now(KST), "id": medication_id})

    def check(value):
        if value["child_memo"] == "[TEST] 투약 확인":
            raise ModelError("[TEST] 검사 실패")
        return {"checks": []}

    graph_models(echo_writer, check)
    listed = notes(db_client, teacher, draft(db_client, teacher, [
        {"child_id": str(child_id), "memo": "[TEST] 투약 확인"}]))
    target = next(n for n in listed if n["child_id"] == str(child_id))
    assert target["status"] == "needs_check"
    assert [c["kind"] for c in target["open_checks"]] == ["sensitive", "check_failed"]
    with seeded_db.connect() as connection:
        stored = connection.scalar(text("SELECT open_checks FROM daily_notes WHERE id=:id"), {"id": target["id"]})
    assert [c["kind"] for c in stored] == ["sensitive", "check_failed"]


def test_graph_entry_exception_marks_whole_job_failed(db_client, teacher, seeded_db, graph_models, monkeypatch):
    def fail(payload, *, writer, checker):
        raise RuntimeError("[TEST] 그래프 전체 실패")

    monkeypatch.setattr(graph, "draft_daily_notes", fail)
    response = draft(db_client, teacher)
    assert response.status_code == 202
    status = db_client.get(f"{BASE}/daily-notes/drafts/{response.json()['input_id']}", headers=teacher).json()
    assert status["draft_status"] == "failed" and status["error"]["code"] == "UPSTREAM_UNAVAILABLE"
    with seeded_db.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM daily_notes")) == 0


@pytest.mark.parametrize("blocked_role", ["DOCUMENT", "CHECKER"])
def test_superseded_graph_stops_before_next_model_call(
        db_client, teacher, seeded_db, monkeypatch, graph_models, blocked_role):
    started, release = Event(), Event()
    runs, calls = [], []

    class FakeModel:
        def __init__(self, role):
            if role == "DOCUMENT":
                runs.append(len(runs))
            self.run, self.role = runs[-1], role

        def json(self, system, user):
            calls.append((self.run, self.role))
            value = json.loads(user)
            if self.run == 0 and self.role == blocked_role:
                started.set()
                assert release.wait(20), "[TEST] 이전 호출 해제 시간 초과"
            if self.role == "DOCUMENT":
                return echo_writer(value)
            return {"checks": [{"item_key": "child", "kind": "not_in_memo", "problem": "[TEST] 다시 쓰기"}]
                    if self.run == 0 else []}

    monkeypatch.setattr(llm, "OpenAIModel", FakeModel)
    with seeded_db.begin() as connection:
        # 한 아이의 메모만 모델을 호출하게 해서 옛 실행의 호출 수를 정확히 센다.
        connection.execute(text("UPDATE requests SET created_at=created_at-interval '1 day'"))
    with ThreadPoolExecutor(max_workers=1) as pool:
        previous = pool.submit(draft, db_client, teacher,
                               [{"child_id": str(seed.CHILD), "memo": "[TEST] 블록 놀이"}])
        try:
            assert started.wait(15), "[TEST] 이전 호출 시작 시간 초과"
            with seeded_db.begin() as connection:
                input_id = connection.scalar(text("SELECT id FROM daily_note_inputs"))
                connection.execute(text("""
                    UPDATE cards SET draft=draft || '{"draft_started_at":"2020-01-01T00:00:00+09:00"}'::jsonb
                    WHERE subject_id=:id
                """), {"id": input_id})
            response = db_client.post(f"{BASE}/daily-notes/drafts/{input_id}/regenerate", headers=teacher)
            before = notes(db_client, teacher, response)
            assert all(n["status"] == "draft" for n in before)
        finally:
            release.set()
        old_response = previous.result(timeout=15)
    assert notes(db_client, teacher, old_response) == before
    assert [role for run, role in calls if run == 0] == (
        ["DOCUMENT"] if blocked_role == "DOCUMENT" else ["DOCUMENT", "CHECKER"])
    assert [role for run, role in calls if run == 1] == ["DOCUMENT", "CHECKER"]
    with seeded_db.connect() as connection:
        assert connection.scalar(text("SELECT draft_status FROM daily_note_inputs")) == "succeeded"
        assert connection.scalar(text("SELECT count(*) FROM events WHERE action='tool_failed'")) == 0
        assert connection.scalar(text("SELECT count(*) FROM events WHERE action='daily_note_drafted'")) == 20
