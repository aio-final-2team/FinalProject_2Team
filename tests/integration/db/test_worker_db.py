"""Celery eager 모드에서 실제 DB 입구·중복 실행·주기 복구를 확인해요."""

from dataclasses import replace
from datetime import datetime, timedelta
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
from app.modules.requests import requests, runner as request_runner


@pytest.fixture
def eager_worker(seeded_db, monkeypatch):
    for module in (jobs, worker, main, request_runner):
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
    with eager_worker.connect() as connection:
        assert connection.scalar(text("SELECT draft_status FROM daily_note_inputs WHERE id=:id"), {"id": input_id}) == "succeeded"
        assert connection.scalar(text("SELECT count(*) FROM daily_notes")) == 20
        assert connection.scalar(text("SELECT count(*) FROM events WHERE daily_note_id IS NOT NULL")) == 20
        assert connection.scalar(text("SELECT count(*) FROM cards WHERE request_id=:id"), {"id": request_id}) == 1
    # 첫 dispatch 성공을 단정한 뒤 중복 전달도 확인해요.
    worker.daily_note_drafts.delay(str(input_id)).get()
    worker.request_agent.delay(str(request_id)).get()
    with eager_worker.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM events WHERE daily_note_id IS NOT NULL")) == 20
        assert connection.scalar(text("SELECT count(*) FROM cards WHERE request_id=:id"), {"id": request_id}) == 1
    again = BackgroundTasks()
    assert notes.regenerate(users.get_user(seed.TEACHER), input_id, again)["draft_status"] == "queued"
    anyio.run(again)
    with eager_worker.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM daily_notes")) == 20
        assert connection.scalar(text("SELECT count(*) FROM events WHERE daily_note_id IS NOT NULL")) == 40


def test_broker_failure_marks_note_failed_and_teacher_regenerates_while_request_sweep_recovers(eager_worker, monkeypatch):
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
        assert connection.scalar(text("SELECT draft_status FROM daily_note_inputs WHERE id=:id"), {"id": input_id}) == "failed"
        assert connection.execute(text("""
            SELECT e.action,e.detail->>'detected_failure' FROM events e JOIN cards c ON c.id=e.card_id
            WHERE c.subject_type='daily_note_batch' AND c.subject_id=:id
        """), {"id": input_id}).all() == [("tool_failed", "queue_error")]
    worker.sweep.delay().get()
    worker.sweep.delay().get()
    with eager_worker.connect() as connection:
        assert connection.scalar(text("SELECT draft_status FROM daily_note_inputs WHERE id=:id"), {"id": input_id}) == "failed"
        assert connection.scalar(text("SELECT count(*) FROM daily_notes WHERE input_id=:id"), {"id": input_id}) == 0
    retry = BackgroundTasks()
    assert notes.regenerate(users.get_user(seed.TEACHER), input_id, retry)["draft_status"] == "queued"
    anyio.run(retry)
    with eager_worker.connect() as connection:
        assert connection.scalar(text("SELECT draft_status FROM daily_note_inputs WHERE id=:id"), {"id": input_id}) == "succeeded"
        assert connection.scalar(text("SELECT count(*) FROM cards WHERE request_id=:id"), {"id": request_id}) == 1
        assert connection.scalar(text("SELECT status FROM requests WHERE id=:id"), {"id": request_id}) == "awaiting_review"
        assert connection.scalar(text("SELECT count(*) FROM events WHERE request_id=:id AND action='agent_requeued'"),
                                 {"id": request_id}) == 1
        assert connection.scalar(text("SELECT count(*) FROM events WHERE request_id=:id AND detail->>'handoff_reason'='card_missing'"),
                                 {"id": request_id}) == 0
        assert connection.scalar(text("SELECT draft->>'text' FROM cards WHERE request_id=:id"), {"id": request_id})


@pytest.mark.parametrize("status", ["running", "succeeded", "failed"])
def test_late_publish_failure_does_not_overwrite_progress_or_duplicate_failure(eager_worker, monkeypatch, status):
    input_id = draft(BackgroundTasks())
    with eager_worker.begin() as connection:
        connection.execute(text("UPDATE daily_note_inputs SET draft_status=:status WHERE id=:id"),
                           {"id": input_id, "status": status})
    def fail(**kwargs):
        raise ConnectionError("[TEST] queue unavailable")
    monkeypatch.setattr(worker.daily_note_drafts, "apply_async", fail)
    jobs.publish("daily_note", input_id)
    with eager_worker.connect() as connection:
        assert connection.scalar(text("SELECT draft_status FROM daily_note_inputs WHERE id=:id"), {"id": input_id}) == status
        assert connection.scalar(text("SELECT count(*) FROM events WHERE action='tool_failed'")) == 0


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


def test_worker_recovery_gives_writer_sixty_seconds_to_finish(eager_worker):
    from app.modules.daily_notes import runner
    fresh, stale = draft(BackgroundTasks(), "2026-11-19"), draft(BackgroundTasks())
    with eager_worker.begin() as connection:
        connection.execute(text("UPDATE daily_note_inputs SET draft_status='running'"))
        for input_id, grace in ((fresh, 30), (stale, 61)):
            connection.execute(text("""
                UPDATE cards SET draft=draft || jsonb_build_object('draft_started_at',
                    now()-make_interval(secs=>:seconds))
                WHERE subject_type='daily_note_batch' AND subject_id=:id
            """), {"id": input_id, "seconds": runner.settings.daily_note_writer_timeout+grace})
    assert runner.requeue_daily_note_drafts(stale_only=True) == [stale]
    with eager_worker.connect() as connection:
        assert dict(connection.execute(text("SELECT id,draft_status FROM daily_note_inputs")).all()) == {
            fresh: "running", stale: "queued"}


def test_worker_startup_checks_broker_once(eager_worker, monkeypatch):
    calls = []
    monkeypatch.setattr(jobs, "check_broker", lambda: calls.append("checked"))
    with TestClient(main.app) as client:
        assert client.get("/health").status_code == 200
    assert calls == ["checked"]


def test_queued_request_is_republished_once_then_handed_off_after_five_more_minutes(eager_worker, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from app.modules.requests import runner
    request_id = request(BackgroundTasks())
    now = datetime.now(KST)
    with eager_worker.begin() as connection:
        connection.execute(text("UPDATE requests SET created_at=:at WHERE id=:id"),
                           {"id": request_id, "at": now-timedelta(minutes=6)})
    published = []
    monkeypatch.setattr(jobs, "publish", lambda job, oid: published.append((job, str(oid))))
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: runner.sweep_missing_cards(now), range(2)))
    assert published.count(("request", str(request_id))) == 1
    # 시드의 다른 요청도 이때 5분을 넘을 수 있어요. 이 요청의 경계를 검사해요.
    runner.sweep_missing_cards(now+timedelta(minutes=5, microseconds=-1))
    assert published.count(("request", str(request_id))) == 1
    with eager_worker.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM cards WHERE request_id=:id"), {"id": request_id}) == 0
        assert connection.scalar(text("SELECT status FROM requests WHERE id=:id"), {"id": request_id}) == "received"
        assert connection.scalar(text("SELECT count(*) FROM events WHERE request_id=:id AND action='agent_requeued'"),
                                 {"id": request_id}) == 1
        assert connection.scalar(text("SELECT count(*) FROM notifications WHERE request_id=:id"), {"id": request_id}) == 0
    runner.sweep_missing_cards(now+timedelta(minutes=5))
    runner.sweep_missing_cards(now+timedelta(minutes=10))
    assert published.count(("request", str(request_id))) == 1
    with eager_worker.connect() as connection:
        card = connection.execute(text("SELECT * FROM cards WHERE request_id=:id"), {"id": request_id}).mappings().one()
        assert card["status"] == "pending" and card["assignee_id"] == seed.TEACHER and card["draft"] == {}
        assert connection.scalar(text("SELECT count(*) FROM events WHERE request_id=:id AND detail->>'handoff_reason'='card_missing'"),
                                 {"id": request_id}) == 1


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


@pytest.fixture
def expired_requests(eager_worker):
    """조회 없이 오래된 보류·체크·상담 보고를 준비해요."""
    from app.modules.requests import agent_stub
    ids = {}
    for name, kind, body in (("held", "complaint", "[TEST] 보류 재개"),
                             ("chosen", "consultation", "[TEST] 상담 체크 만료"),
                             ("report", "consultation", "[TEST] 상담 중 아이가 다쳤어요"),
                             ("future", "complaint", "[TEST] 미래 보류"),
                             ("paused", "consultation", "[TEST] 보류 중 상담 체크"),
                             ("escalated", "consultation", "[TEST] 원장 확인 중 상담 체크")):
        rid = requests.create(users.get_user(seed.PARENT), background_tasks=BackgroundTasks(),
                              client_request_id=str(uuid4()), type=kind, body=body,
                              child_id=seed.CHILD, previous_request_id=None, trace_id="[TEST]-expiry")[0]["id"]
        agent_stub.run_request(rid)
        ids[name] = rid
    with eager_worker.begin() as connection:
        for name in ("held", "future"):
            connection.execute(text("UPDATE requests SET status='on_hold' WHERE id=:id"), {"id": ids[name]})
            connection.execute(text("""
                UPDATE cards SET status='on_hold',hold_until=CURRENT_DATE+:days
                WHERE request_id=:id AND kind='reply_draft'
            """), {"id": ids[name], "days": -1 if name == "held" else 1})
        for name, status in (("chosen", "awaiting_review"), ("paused", "on_hold"), ("escalated", "escalated")):
            connection.execute(text("UPDATE requests SET status=:status WHERE id=:id"),
                               {"id": ids[name], "status": status})
            connection.execute(text("""
                UPDATE consultation_slots SET status='chosen_by_parent',chosen_at=now()-interval '24 hours'
                WHERE id=(SELECT s.id FROM consultation_slots s JOIN cards c ON c.id=s.card_id
                          WHERE c.request_id=:id ORDER BY s.id LIMIT 1)
            """), {"id": ids[name]})
            if name == "paused":
                connection.execute(text("""
                    UPDATE cards SET status='on_hold',hold_until=CURRENT_DATE+1 WHERE request_id=:id
                """), {"id": ids[name]})
        connection.execute(text("""
            UPDATE cards SET status='on_hold',hold_until=CURRENT_DATE-1
            WHERE request_id=:id AND kind='director_report'
        """), {"id": ids["report"]})
    return ids


def assert_expiry(engine, ids):
    with engine.connect() as connection:
        states = {name: connection.scalar(text("SELECT status FROM requests WHERE id=:id"), {"id": rid})
                  for name, rid in ids.items()}
        assert states == {"held": "awaiting_review", "chosen": "needs_info", "report": "needs_info",
                          "future": "on_hold", "paused": "on_hold", "escalated": "escalated"}
        for name, action, kind in (("held", "resumed", "hold_resumed"),
                                   ("chosen", "slot_hold_expired", "slot_hold_expired"),
                                   ("report", "resumed", "hold_resumed")):
            assert connection.scalar(text("SELECT count(*) FROM events WHERE request_id=:id AND action=:action"),
                                     {"id": ids[name], "action": action}) == 1
            assert connection.scalar(text("SELECT count(*) FROM notifications WHERE request_id=:id AND kind=:kind"),
                                     {"id": ids[name], "kind": kind}) == (0 if name == "report" else 1)
        assert connection.scalar(text("""
            SELECT status FROM cards WHERE request_id=:id AND kind='director_report'
        """), {"id": ids["report"]}) == "pending"
        assert connection.scalar(text("""
            SELECT count(*) FROM consultation_slots s JOIN cards c ON c.id=s.card_id
            WHERE c.request_id=:id AND s.status='chosen_by_parent'
        """), {"id": ids["chosen"]}) == 0


def test_worker_expiry_resumes_and_expires_without_http_reads_once(eager_worker, expired_requests):
    worker.expire_requests.delay().get()
    worker.expire_requests.delay().get()
    assert_expiry(eager_worker, expired_requests)


def test_expiry_advisory_lock_and_busy_request_skip_then_retry(eager_worker, expired_requests):
    with eager_worker.begin() as connection:
        connection.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('requests:expiry',0))"))
        assert worker.expire_requests.delay().get() == 0
    with eager_worker.begin() as connection:
        connection.execute(text("SELECT id FROM requests WHERE id=:id FOR UPDATE"), {"id": expired_requests["held"]})
        worker.expire_requests.delay().get()
        assert connection.scalar(text("SELECT status FROM requests WHERE id=:id"),
                                 {"id": expired_requests["held"]}) == "on_hold"
    worker.expire_requests.delay().get()
    assert_expiry(eager_worker, expired_requests)


def test_api_startup_and_periodic_thread_expire_and_recover_missing_cards(
    eager_worker, expired_requests, monkeypatch
):
    from threading import Event
    for module in (jobs, main, request_runner):
        monkeypatch.setattr(module, "settings", replace(module.settings, data_backend="db", run_in="api"))
    missing = request(BackgroundTasks())
    with eager_worker.begin() as connection:
        connection.execute(text("UPDATE requests SET created_at=now()-interval '6 minutes' WHERE id=:id"), {"id": missing})
    original, repeated, calls = jobs.run_api_maintenance, Event(), []
    def checked():
        original()
        calls.append(True)
        if len(calls) >= 2:
            repeated.set()
    monkeypatch.setattr(jobs, "run_api_maintenance", checked)
    monkeypatch.setattr(jobs, "API_MAINTENANCE_INTERVAL", 0.02)
    with TestClient(main.app) as client:
        assert_expiry(eager_worker, expired_requests)
        assert client.get("/health").status_code == 200
        assert repeated.wait(10), "[TEST] API 주기 점검이 다시 실행되지 않음"
        with eager_worker.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM cards WHERE request_id=:id"), {"id": missing}) == 1
            assert connection.scalar(text("SELECT count(*) FROM events WHERE request_id=:id AND action='agent_requeued'"),
                                     {"id": missing}) == 1
    count = len(calls)
    assert count >= 2  # TestClient 종료는 주기 작업을 기다리지 않고 정상적으로 끝나요.


def test_api_maintenance_advisory_lock_skips_competing_process(eager_worker, expired_requests):
    with eager_worker.begin() as connection:
        connection.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('api:maintenance',0))"))
        jobs.run_api_maintenance()
        assert connection.scalar(text("SELECT status FROM requests WHERE id=:id"),
                                 {"id": expired_requests["held"]}) == "on_hold"
    jobs.run_api_maintenance()
    assert_expiry(eager_worker, expired_requests)
