"""Celery eager 모드에서 실제 DB 입구·중복 실행·주기 복구를 확인해요."""

from dataclasses import replace
from datetime import datetime
from uuid import uuid4

import anyio
from fastapi import BackgroundTasks
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import text

from app import main, worker
from app.api.schemas.actions import NoteDraftIn
from app.core import jobs, users
from app.core.schedule import KST
from app.mock import seed
from app.modules.daily_notes import notes
from app.modules.requests import requests


@pytest.fixture
def eager_worker(seeded_db, monkeypatch):
    for module in (jobs, worker, main):
        monkeypatch.setattr(module, "settings", replace(module.settings, data_backend="db", run_in="worker"))
    monkeypatch.setitem(worker.celery_app.conf, "task_always_eager", True)
    monkeypatch.setitem(worker.celery_app.conf, "task_eager_propagates", True)
    monkeypatch.setitem(worker.celery_app.conf, "broker_url", "memory://")
    return seeded_db


def draft(tasks, day="2026-11-20"):
    return notes.draft(users.get_user(seed.TEACHER), NoteDraftIn.model_validate({
        "classroom_id": str(seed.CLASS_STAR), "note_date": day,
        "activities": "[TEST] 워커 활동", "supplies": "수건"}), tasks)[0]["input_id"]


def request(tasks):
    return requests.create(users.get_user(seed.PARENT), background_tasks=tasks, client_request_id=str(uuid4()),
                           type="inquiry", body="[TEST] 워커 문의", child_id=seed.CHILD,
                           previous_request_id=None, trace_id="worker-test")[0]["id"]


def test_eager_note_request_and_regenerate_use_same_db_guards(eager_worker):
    tasks = BackgroundTasks()
    input_id, request_id = draft(tasks), request(tasks)
    with eager_worker.connect() as connection:
        assert connection.scalar(text("SELECT draft_status FROM daily_note_inputs WHERE id=:id"), {"id": input_id}) == "queued"
        assert connection.scalar(text("SELECT count(*) FROM cards WHERE request_id=:id"), {"id": request_id}) == 0
    anyio.run(tasks)
    worker.daily_note_drafts.delay(str(input_id)).get()
    worker.request_agent.delay(str(request_id)).get()
    with eager_worker.connect() as connection:
        assert connection.scalar(text("SELECT draft_status FROM daily_note_inputs WHERE id=:id"), {"id": input_id}) == "succeeded"
        assert connection.scalar(text("SELECT count(*) FROM daily_notes")) == 20
        assert connection.scalar(text("SELECT count(*) FROM events WHERE daily_note_id IS NOT NULL")) == 20
        assert connection.scalar(text("SELECT count(*) FROM cards WHERE request_id=:id"), {"id": request_id}) == 1
    again = BackgroundTasks()
    assert notes.regenerate(users.get_user(seed.TEACHER), input_id, again)["draft_status"] == "queued"
    anyio.run(again)
    with eager_worker.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM daily_notes")) == 20
        assert connection.scalar(text("SELECT count(*) FROM events WHERE daily_note_id IS NOT NULL")) == 40


def test_broker_failure_preserves_rows_and_periodic_sweep_recovers(eager_worker, monkeypatch):
    tasks = BackgroundTasks()
    input_id, request_id = draft(tasks), request(tasks)
    def fail(**kwargs):
        raise ConnectionError("[TEST] Redis unavailable")
    with monkeypatch.context() as patch:
        patch.setattr(worker.daily_note_drafts, "apply_async", fail)
        patch.setattr(worker.request_agent, "apply_async", fail)
        anyio.run(tasks)
    with eager_worker.begin() as connection:
        connection.execute(text("UPDATE requests SET created_at=now()-interval '6 minutes' WHERE id=:id"), {"id": request_id})
        assert connection.scalar(text("SELECT draft_status FROM daily_note_inputs WHERE id=:id"), {"id": input_id}) == "queued"
    worker.sweep.delay().get()
    worker.sweep.delay().get()
    with eager_worker.connect() as connection:
        assert connection.scalar(text("SELECT draft_status FROM daily_note_inputs WHERE id=:id"), {"id": input_id}) == "succeeded"
        assert connection.scalar(text("SELECT count(*) FROM cards WHERE request_id=:id"), {"id": request_id}) == 1
        assert connection.scalar(text("SELECT status FROM requests WHERE id=:id"), {"id": request_id}) == "awaiting_review"
        assert connection.scalar(text("SELECT count(*) FROM events WHERE request_id=:id AND detail->>'handoff_reason'='card_missing'"),
                                 {"id": request_id}) == 1


def test_api_restart_keeps_active_worker_run_and_sweep_recovers_only_stale_run(eager_worker):
    fresh, stale = draft(BackgroundTasks(), "2026-11-19"), draft(BackgroundTasks())
    with eager_worker.begin() as connection:
        connection.execute(text("UPDATE daily_note_inputs SET draft_status='running'"))
        connection.execute(text("""
            UPDATE cards SET draft=draft || jsonb_build_object('draft_started_at',now())
            WHERE subject_type='daily_note_batch'
        """))
    with TestClient(main.app):
        pass
    with eager_worker.begin() as connection:
        assert connection.scalar(text("SELECT count(*) FROM daily_note_inputs WHERE draft_status='running'")) == 2
        connection.execute(text("""
            UPDATE cards SET draft=draft || jsonb_build_object('draft_started_at',now()-interval '10 minutes')
            WHERE subject_type='daily_note_batch' AND subject_id=:id
        """), {"id": stale})
    worker.sweep.delay().get()
    with eager_worker.connect() as connection:
        states = dict(connection.execute(text("SELECT id,draft_status FROM daily_note_inputs")).all())
        assert states == {fresh: "running", stale: "succeeded"}


def test_eager_notification_task_marks_only_app_rows_sent(eager_worker):
    now = datetime.now(KST)
    with eager_worker.begin() as connection:
        connection.execute(text("""
            INSERT INTO notifications(org_id,recipient_id,kind,title,dedupe_key,deliver_after,next_attempt_at)
            VALUES (:org,:user,'new_card','[TEST] 알림','worker-notice',:now,:now)
        """), {"org": seed.ORG, "user": seed.PARENT, "now": now})
    assert worker.deliver_notifications.delay().get() == 1
    assert worker.deliver_notifications.delay().get() == 0
    with eager_worker.connect() as connection:
        row = connection.execute(text("SELECT * FROM notifications WHERE dedupe_key='worker-notice'")).mappings().one()
        assert row["status"] == "sent" and row["attempts"] == 1 and row["sent_at"] is not None
