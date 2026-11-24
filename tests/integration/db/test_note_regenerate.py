"""이전 실행의 늦은 성공·실패가 재생성 결과를 덮어쓰지 못한다."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Event

import pytest
from fastapi import BackgroundTasks
from sqlalchemy import text

from app.core import users
from app.mock import seed
from app.modules.daily_notes import notes as db_notes, stub_writer, runner
from tests.integration.db.test_daily_notes_runner import (
    BASE, batch, draft, notes, set_writer, teacher as teacher,
)


@pytest.mark.parametrize("old_failure", [False, True])
def test_regenerate_supersedes_active_writer_success_or_failure(db_client, teacher, seeded_db, monkeypatch, old_failure):
    started, release = Event(), Event()
    calls = []

    def writer(payload):
        calls.append(payload)
        if len(calls) == 1:
            started.set()
            assert release.wait(20)
            if old_failure:
                raise RuntimeError("[TEST] 늦은 이전 실패")
            rows = stub_writer.write(payload)
            rows[0]["content"]["items"][0]["value"] = "[TEST] 버려야 할 이전 초안"
            return rows
        return stub_writer.write(payload)

    set_writer(monkeypatch, writer)
    with ThreadPoolExecutor(max_workers=1) as pool:
        previous = pool.submit(draft, db_client, teacher)
        try:
            assert started.wait(15)
            with seeded_db.connect() as connection:
                input_id = connection.scalar(text("SELECT id FROM daily_note_inputs"))
            with seeded_db.begin() as connection:
                connection.execute(text("""
                    UPDATE cards SET draft=draft || '{"draft_started_at":"2020-01-01T00:00:00+09:00"}'::jsonb
                    WHERE subject_id=:id
                """), {"id": input_id})
            response = db_client.post(f"{BASE}/daily-notes/drafts/{input_id}/regenerate", headers=teacher)
            assert response.status_code == 202, response.text
            before = deepcopy(notes(db_client, teacher))
            assert len(before) == 20
        finally:
            release.set()
        assert previous.result(timeout=15).status_code == 202
    assert len(calls) == 2 and notes(db_client, teacher) == before
    with seeded_db.connect() as connection:
        assert connection.scalar(text("SELECT draft_status FROM daily_note_inputs")) == "succeeded"
        assert connection.scalar(text("SELECT count(*) FROM events WHERE action='daily_note_drafted'")) == 20


@pytest.mark.parametrize("status", ["failed", "queued", "running"])
def test_regenerate_recovers_input_without_any_saved_notes(db_client, teacher, seeded_db, status):
    from app.api.schemas.actions import NoteDraftIn
    body = NoteDraftIn.model_validate({**batch(), "activities": "[TEST] 저장 전 멈춤", "supplies": "수건"})
    result, _ = db_notes.draft(users.get_user(seed.TEACHER), body, BackgroundTasks())
    with seeded_db.begin() as connection:
        connection.execute(text("UPDATE daily_note_inputs SET draft_status=:status, created_at=created_at-interval '1 day' WHERE id=:id"),
                           {"status": status, "id": result["input_id"]})
    assert db_client.post(f"{BASE}/daily-notes/drafts/{result['input_id']}/regenerate", headers=teacher).status_code == 202
    assert len(notes(db_client, teacher)) == 20


def test_confirmation_during_writer_preserves_ready_note(db_client, teacher, seeded_db, monkeypatch):
    input_id = draft(db_client, teacher).json()["input_id"]
    target = next(n for n in notes(db_client, teacher) if not n["open_checks"])
    started, release = Event(), Event()

    def writer(payload):
        started.set()
        assert release.wait(20)
        rows = stub_writer.write(payload)
        for row in rows:
            row["content"]["items"][0]["value"] = "[TEST] 새 초안"
        return rows

    set_writer(monkeypatch, writer)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(db_client.post, f"{BASE}/daily-notes/drafts/{input_id}/regenerate", headers=teacher)
        try:
            assert started.wait(15)
            confirmed = db_client.patch(f"{BASE}/daily-notes/{target['id']}", headers=teacher, json={"confirm": True})
            assert confirmed.status_code == 200, confirmed.text
        finally:
            release.set()
        assert pending.result(timeout=15).status_code == 202
    assert next(n for n in notes(db_client, teacher) if n["id"] == target["id"]) == {
        **confirmed.json()["note"], "input_id": input_id}
    with seeded_db.connect() as connection:
        assert connection.scalar(text("SELECT draft_status FROM daily_note_inputs")) == "succeeded"


def test_actual_failed_writer_can_retry_and_all_ready_does_not_call_writer(db_client, teacher, monkeypatch):
    def fail(payload):
        raise RuntimeError("[TEST] 모델 일시 실패")

    set_writer(monkeypatch, fail)
    input_id = draft(db_client, teacher).json()["input_id"]
    assert db_client.get(f"{BASE}/daily-notes/drafts/{input_id}", headers=teacher).json()["draft_status"] == "failed"
    set_writer(monkeypatch, stub_writer.write)
    path = f"{BASE}/daily-notes/drafts/{input_id}/regenerate"
    assert db_client.post(path, headers=teacher).status_code == 202
    for note in notes(db_client, teacher):
        assert db_client.patch(f"{BASE}/daily-notes/{note['id']}", headers=teacher, json={
            "confirm": True, "resolved_checks": [c["id"] for c in note["open_checks"]]}).status_code == 200
    set_writer(monkeypatch, fail)
    assert db_client.post(path, headers=teacher).status_code == 202
    assert db_client.get(f"{BASE}/daily-notes/drafts/{input_id}", headers=teacher).json()["draft_status"] == "succeeded"
    assert all(n["status"] == "ready" for n in notes(db_client, teacher))


def test_failed_child_regeneration_replaces_failure_original(db_client, teacher, seeded_db, monkeypatch):
    def partial(payload):
        rows = stub_writer.write(payload)
        rows[0]["content"] = {"items": [{"key": "invalid"}]}
        return rows

    set_writer(monkeypatch, partial)
    input_id = draft(db_client, teacher, child_memos=[{"child_id": str(seed.CHILD), "memo": "[TEST] 모래 놀이"}]).json()["input_id"]
    failed = next(n for n in notes(db_client, teacher) if any(c["kind"] == "draft_failed" for c in n["open_checks"]))
    assert not any(line["key"] == "child" for line in failed["content"]["items"])
    set_writer(monkeypatch, stub_writer.write)
    assert db_client.post(f"{BASE}/daily-notes/drafts/{input_id}/regenerate", headers=teacher).json()["kept_edited"] == 0
    after = next(n for n in notes(db_client, teacher) if n["id"] == failed["id"])
    assert any(line["key"] == "child" for line in after["content"]["items"])
    with seeded_db.connect() as connection:
        row = connection.execute(text("SELECT content,ai_original FROM daily_notes WHERE id=:id"), {"id": failed["id"]}).one()
        assert row.content == row.ai_original


def test_two_regenerates_dispatch_one_writer_and_keep_edit_during_run(db_client, teacher, seeded_db, monkeypatch):
    input_id = draft(db_client, teacher).json()["input_id"]
    target = notes(db_client, teacher)[0]
    started, release = Event(), Event()
    calls = []

    def writer(payload):
        calls.append(payload)
        started.set()
        assert release.wait(20)
        rows = stub_writer.write(payload)
        for row in rows:
            row["content"]["items"][0]["value"] = "[TEST] 재생성 결과"
        return rows

    set_writer(monkeypatch, writer)
    path = f"{BASE}/daily-notes/drafts/{input_id}/regenerate"
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(db_client.post, path, headers=teacher)
        try:
            assert started.wait(15)
            edited = deepcopy(target["content"])
            edited["items"][0]["value"] = "[TEST] 작성기 실행 중 선생님 수정"
            changed = db_client.patch(f"{BASE}/daily-notes/{target['id']}", headers=teacher, json={"content": edited})
            assert changed.status_code == 200
            duplicate = db_client.post(path, headers=teacher)
            assert duplicate.status_code == 202
            assert duplicate.json()["draft_status"] == "running" and duplicate.json()["kept_edited"] == 1
        finally:
            release.set()
        assert pending.result(timeout=15).status_code == 202
    assert len(calls) == 1
    assert next(n for n in notes(db_client, teacher) if n["id"] == target["id"]) == {
        **changed.json()["note"], "input_id": input_id}
    with seeded_db.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM events WHERE action='daily_note_drafted'")) == 39


def test_second_queued_regenerate_does_not_dispatch_or_replace_requester(db_client, seeded_db, teacher):
    input_id = draft(db_client, teacher).json()["input_id"]
    first, second = BackgroundTasks(), BackgroundTasks()
    user = users.get_user(seed.TEACHER)
    result = db_notes.regenerate(user, input_id, first)
    duplicate = db_notes.regenerate(user, input_id, second)
    assert result == duplicate and duplicate["draft_status"] == "queued"
    assert len(first.tasks) == 1 and not second.tasks
    runner.run_daily_note_drafts(input_id)
    with seeded_db.connect() as connection:
        assert connection.scalar(text("SELECT draft->>'regenerated_by' FROM cards WHERE subject_id=:id"), {"id": input_id}) == str(user.id)
