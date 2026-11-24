"""실제 DB에서 백그라운드 상태·writer 경계·원자적 저장을 검사한다."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, time, timedelta
from uuid import UUID
import json
from threading import Event

import pytest
from fastapi import BackgroundTasks
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.auth import issue_token
from app.core.schedule import KST
from app.core import users
from app.mock import seed
from app.modules.daily_notes import runner, stub_writer

BASE = "/api/v1"


@pytest.fixture
def teacher(db_client):
    return {"Authorization": "Bearer " + issue_token(users.get_user(seed.TEACHER))}


def batch():
    return {"classroom_id": str(seed.CLASS_STAR), "note_date": datetime.now(KST).date().isoformat()}


def draft(db_client, teacher, **extra):
    return db_client.post(BASE + "/daily-notes/drafts", headers=teacher,
                          json={**batch(), "activities": "[TEST] 블록 놀이", "supplies": "내일 실내화", **extra})


def notes(db_client, teacher):
    response = db_client.get(BASE + "/daily-notes", headers=teacher,
                             params={"date": batch()["note_date"], "classroom_id": str(seed.CLASS_STAR)})
    assert response.status_code == 200, response.text
    return response.json()["items"]


def set_writer(monkeypatch, writer):
    # 실제 import 경로 설정을 거쳐 시험용 입구 함수를 호출한다.
    monkeypatch.setattr(stub_writer, "test_write", writer, raising=False)
    monkeypatch.setattr(runner, "settings", replace(runner.settings,
                                                  daily_note_writer="app.modules.daily_notes.stub_writer:test_write"))


@pytest.mark.parametrize("regenerating", [False, True])
def test_request_received_during_writer_is_kept_as_missed_check_at_save(db_client, teacher, monkeypatch, regenerating):
    started, release = Event(), Event()
    input_id = draft(db_client, teacher).json()["input_id"] if regenerating else None

    def writer(payload):
        started.set()
        assert release.wait(15)
        return stub_writer.write(payload)

    set_writer(monkeypatch, writer)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(lambda: db_client.post(f"{BASE}/daily-notes/drafts/{input_id}/regenerate", headers=teacher)
                             if regenerating else draft(db_client, teacher))
        try:
            assert started.wait(15)
            parent = {"Authorization": "Bearer " + issue_token(users.get_user(seed.PARENT))}
            created = db_client.post(BASE + "/requests", headers=parent, json={
                "client_request_id": f"late-writer-{regenerating}", "child_id": str(seed.CHILD),
                "type": "medication", "body": "[TEST] 작성 중 새 투약 요청"})
            assert created.status_code == 202, created.text
            request_id = created.json()["request"]["id"]
            pending = next((n for n in notes(db_client, teacher) if n["child_id"] == str(seed.CHILD)), None)
            original_check = next(c for c in pending["open_checks"] if c["request_id"] == request_id) if pending else None
        finally:
            release.set()
        assert future.result(timeout=15).status_code == 202
    note = next(n for n in notes(db_client, teacher) if n["child_id"] == str(seed.CHILD))
    checks = [c for c in note["open_checks"] if c["request_id"] == request_id]
    assert note["status"] == "needs_check" and len(checks) == 1
    assert checks[0]["kind"] == "request_missed"
    if original_check:
        assert checks[0] == original_check
    assert not any(line["source"]["request_id"] == request_id for line in note["content"]["items"])


def test_startup_recovers_running_and_queued_without_replaying_finished(seeded_db, monkeypatch):
    from app import backend, main
    from app.api.schemas.actions import NoteDraftIn
    from app.modules.daily_notes import notes as db_notes

    monkeypatch.setattr(main, "settings", replace(main.settings, data_backend="db"))
    monkeypatch.setattr(backend, "users", users)
    monkeypatch.setattr(backend, "notes", db_notes)
    user = users.get_user(seed.TEACHER)
    ids = {}
    for index, status in enumerate(("running", "queued", "succeeded", "failed")):
        body = NoteDraftIn.model_validate({**batch(), "note_date": f"2026-11-{16 + index}",
                                          "activities": "[TEST] 복구", "supplies": "수건"})
        result, _ = db_notes.draft(user, body, BackgroundTasks())
        ids[status] = result["input_id"]
        with seeded_db.begin() as connection:
            connection.execute(text("UPDATE daily_note_inputs SET draft_status=:status WHERE id=:id"),
                               {"status": status, "id": result["input_id"]})
    started, release = Event(), Event()
    captured = []

    def writer(payload):
        captured.append(payload["input_id"])
        started.set()
        assert release.wait(15)
        return stub_writer.write(payload)

    set_writer(monkeypatch, writer)
    with TestClient(main.app) as client:
        try:
            assert started.wait(15)
            # writer가 끝나지 않아도 앱은 요청을 받는다. 두 번째 복구는 아직 queued다.
            assert client.get("/health").status_code == 200
            with seeded_db.connect() as connection:
                states = dict(connection.execute(text("SELECT id, draft_status FROM daily_note_inputs")).all())
            assert sorted(states[ids[s]] for s in ("running", "queued")) == ["queued", "running"]
        finally:
            release.set()
    assert set(captured) == {str(ids["running"]), str(ids["queued"])} and len(captured) == 2
    with seeded_db.connect() as connection:
        states = dict(connection.execute(text("SELECT id, draft_status FROM daily_note_inputs")).all())
        assert all(states[ids[s]] == "succeeded" for s in ("running", "queued", "succeeded"))
        assert states[ids["failed"]] == "failed"
        assert connection.scalar(text("SELECT count(*) FROM daily_notes")) == 40
        assert connection.scalar(text("SELECT count(*) FROM cards WHERE subject_type='daily_note_batch'")) == 4
        # 멈춘 running 하나만 점검 작업(시스템)이 되돌린 이력으로 남는다.
        assert connection.execute(text("""
            SELECT actor_type, detail->>'selected_strategy', (detail->>'retry_count')::int FROM events
            WHERE action='agent_requeued' AND card_id IN (
                SELECT id FROM cards WHERE subject_type='daily_note_batch')
        """)).all() == [("system", "requeue_stale", 1)]
    with TestClient(main.app):
        pass
    assert len(captured) == 2


def test_writer_timeout_fails_job_and_discards_late_result(db_client, teacher, seeded_db, monkeypatch):
    release, finished = Event(), Event()

    def writer(payload):
        assert release.wait(15)
        result = stub_writer.write(payload)
        finished.set()
        return result

    set_writer(monkeypatch, writer)
    monkeypatch.setattr(runner, "settings", replace(runner.settings, daily_note_writer_timeout=0.05))
    try:
        response = draft(db_client, teacher)
        status = db_client.get(f"{BASE}/daily-notes/drafts/{response.json()['input_id']}", headers=teacher).json()
        assert status["draft_status"] == "failed" and status["error"]["code"] == "UPSTREAM_UNAVAILABLE"
        assert not finished.is_set()
        blocked = db_client.post(BASE + "/daily-notes/send", headers=teacher, json=batch())
        assert blocked.status_code == 409 and blocked.json()["error"]["details"]["blocked"] == []
    finally:
        release.set()
        assert finished.wait(15)
    assert notes(db_client, teacher) == []
    with seeded_db.connect() as connection:
        assert connection.scalar(text("SELECT draft_status FROM daily_note_inputs")) == "failed"
        assert connection.scalar(text("SELECT count(*) FROM daily_notes")) == 0


def test_writer_can_round_trip_json_input_and_output(db_client, teacher, monkeypatch):
    def writer(payload):
        decoded = json.loads(json.dumps(payload))
        assert decoded == payload
        assert isinstance(decoded["input_id"], str) and decoded["note_date"] == batch()["note_date"]
        assert decoded["classroom"]["id"] == str(seed.CLASS_STAR)
        child = next(c for c in decoded["children"] if c["child_id"] == str(seed.CHILD))
        assert child["memo"] == "[TEST] 아이 메모"
        assert child["requests"] == [{"request_id": str(seed.REQUEST_COUGH), "type": "inquiry", "text": "기침해요"}]
        assert decoded["menu"]["document_id"] == str(seed.MENU)
        return json.loads(json.dumps(stub_writer.write(decoded)))

    set_writer(monkeypatch, writer)
    response = draft(db_client, teacher, child_memos=[{"child_id": str(seed.CHILD), "memo": "[TEST] 아이 메모"}])
    status = db_client.get(f"{BASE}/daily-notes/drafts/{response.json()['input_id']}", headers=teacher).json()
    assert status["draft_status"] == "succeeded" and len(notes(db_client, teacher)) == 20
    child = next(n for n in notes(db_client, teacher) if n["child_id"] == str(seed.CHILD))
    assert any(l["key"] == "child" and l["value"] == "[TEST] 아이 메모" for l in child["content"]["items"])


def test_background_claims_running_and_deduplicates_concurrent_input(db_client, teacher, seeded_db, monkeypatch):
    started, release = Event(), Event()
    captured = []

    def writer(payload):
        captured.append(payload)
        started.set()
        assert release.wait(15)
        return stub_writer.write(payload)

    set_writer(monkeypatch, writer)
    with ThreadPoolExecutor(max_workers=1) as pool:
        result = pool.submit(draft, db_client, teacher)
        try:
            assert started.wait(15)
            with seeded_db.connect() as connection:
                entry = connection.execute(text("SELECT * FROM daily_note_inputs")).mappings().one()
                assert entry["draft_status"] == "running"
                assert connection.scalar(text("SELECT count(*) FROM daily_notes")) == 0
            duplicate = draft(db_client, teacher, activities="중복 입력")
            assert duplicate.status_code == 200 and duplicate.json()["draft_status"] == "running"
            assert duplicate.json()["input_id"] == str(entry["id"])
            blocked = db_client.post(BASE + "/daily-notes/send", headers=teacher, json=batch())
            assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "NOTE_BATCH_BLOCKED"
            # 중복 runner도 writer를 두 번 실행하지 않는다.
            runner.run_daily_note_drafts(entry["id"])
        finally:
            release.set()
        response = result.result(timeout=15)
    assert response.status_code == 202 and response.json()["draft_status"] == "queued"
    assert len(captured) == 1 and len(notes(db_client, teacher)) == 20
    payload = captured[0]
    assert set(payload) == {"input_id", "note_date", "classroom", "activities", "supplies", "children", "menu", "roster_names"}
    assert payload["classroom"] == {"id": str(seed.CLASS_STAR), "name": "만 4세 별빛반"}
    assert set(payload["children"][0]) == {"child_id", "display_name", "memo", "requests"}
    assert payload["menu"]["document_id"] == str(seed.MENU)
    with seeded_db.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM daily_note_inputs")) == 1
        assert connection.scalar(text("SELECT count(*) FROM cards WHERE kind='daily_note'")) == 1
        assert connection.scalar(text("SELECT count(*) FROM events WHERE action='daily_note_drafted'")) == 20


@pytest.mark.parametrize("failure", ["child_exception", "missing", "duplicate", "invalid_content", "foreign_source"])
def test_one_child_failure_keeps_other_children_and_blocks_batch(db_client, teacher, monkeypatch, failure):
    original = stub_writer.write_child

    def write_child(payload, child, index):
        if child["child_id"] == str(seed.CHILD):
            raise RuntimeError("[TEST] 아이 하나 실패")
        return original(payload, child, index)

    if failure == "child_exception":
        monkeypatch.setattr(stub_writer, "write_child", write_child)
    else:
        def writer(payload):
            rows = stub_writer.write(payload)
            target = next(row for row in rows if row["child_id"] == str(seed.CHILD))
            if failure == "missing":
                rows.remove(target)
            elif failure == "duplicate":
                rows.append(target)
            elif failure == "invalid_content":
                target["content"] = {"items": [{"key": "unknown"}]}
            else:
                target["content"]["items"].append({"key": "day", "label": "출처", "value": "잘못된 출처",
                                                    "source": {"type": "request", "request_id": seed.REQUEST_PICKUP}})
            return rows
        set_writer(monkeypatch, writer)
    response = draft(db_client, teacher, child_memos=[{"child_id": str(seed.CHILD), "memo": "아이 메모"},
                                                     {"child_id": str(seed.demo_id("5401")), "memo": "성공 메모"}])
    status = db_client.get(f"{BASE}/daily-notes/drafts/{response.json()['input_id']}", headers=teacher).json()
    assert status["draft_status"] == "succeeded"
    listed = notes(db_client, teacher)
    assert len(listed) == 20
    failed = next(n for n in listed if n["child_id"] == str(seed.CHILD))
    assert [c["kind"] for c in failed["open_checks"]] == ["draft_failed"]
    assert UUID(failed["open_checks"][0]["id"]).version == 4
    assert failed["open_checks"][0]["request_id"] is None
    assert failed["status"] == "needs_check" and all(l["key"] != "child" for l in failed["content"]["items"])
    success = next(n for n in listed if n["child_id"] == str(seed.demo_id("5401")))
    assert any(l["key"] == "child" and l["value"] == "성공 메모" for l in success["content"]["items"])
    assert db_client.post(BASE + "/daily-notes/send", headers=teacher, json=batch()).status_code == 409


@pytest.mark.parametrize("path", ["missing.writer:write", "app.modules.daily_notes.stub_writer:missing", "bad-path"])
def test_bad_writer_configuration_marks_failed_with_safe_queryable_error(db_client, teacher, monkeypatch, path, seeded_db):
    monkeypatch.setattr(runner, "settings", replace(runner.settings, daily_note_writer=path))
    response = draft(db_client, teacher)
    assert response.status_code == 202
    status = db_client.get(f"{BASE}/daily-notes/drafts/{response.json()['input_id']}", headers=teacher).json()
    assert status["draft_status"] == "failed" and status["error"]["code"] == "UPSTREAM_UNAVAILABLE"
    assert notes(db_client, teacher) == []
    with seeded_db.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM cards WHERE kind='daily_note'")) == 1
        # 아이별 이력은 없고, 반 묶음 카드에 작업 실패 한 줄만 남는다.
        assert connection.execute(text("""
            SELECT e.action,e.actor_type FROM events e JOIN cards c ON c.id=e.card_id
            WHERE c.subject_type='daily_note_batch' AND c.subject_id=:id
        """), {"id": response.json()["input_id"]}).all() == [("tool_failed", "system")]


def test_unknown_writer_check_preserves_draft_and_logs_only_kind(db_client, teacher, monkeypatch, caplog):
    def writer(payload):
        rows = stub_writer.write(payload)
        target = next(row for row in rows if row["child_id"] == str(seed.CHILD))
        target["open_checks"].append({"id": "future", "item_key": "child", "kind": "future_check",
                                      "problem": "[TEST] 설명은 그대로", "sentence": "[TEST] 비공개 문장"})
        return rows

    set_writer(monkeypatch, writer)
    draft(db_client, teacher, child_memos=[{"child_id": str(seed.CHILD), "memo": "[TEST] 보존할 메모"}])
    child = next(n for n in notes(db_client, teacher) if n["child_id"] == str(seed.CHILD))
    assert child["status"] == "needs_check"
    assert [c["kind"] for c in child["open_checks"]] == ["date_check", "check_failed"]
    check = child["open_checks"][-1]
    assert check["problem"] == "[TEST] 설명은 그대로" and check["sentence"] == "[TEST] 비공개 문장"
    assert any(line["value"] == "[TEST] 보존할 메모" for line in child["content"]["items"])
    assert "future_check" in caplog.text
    assert all(value not in caplog.text for value in ("보존할 메모", "설명은 그대로", "비공개 문장"))


@pytest.mark.parametrize("memo", ["열이 났음", "넘어져 다침", "약 먹음"])
def test_sensitive_memo_is_verbatim_with_one_check(db_client, teacher, memo):
    draft(db_client, teacher, child_memos=[{"child_id": str(seed.CHILD), "memo": memo}])
    child = next(n for n in notes(db_client, teacher) if n["child_id"] == str(seed.CHILD))
    assert [l["value"] for l in child["content"]["items"] if l["key"] == "child"] == [memo]
    checks = [c for c in child["open_checks"] if c["kind"] == "sensitive"]
    assert len(checks) == 1 and checks[0]["sentence"] == memo


@pytest.mark.parametrize("seconds,included", [(-1, False), (0, True), (86399, True), (86400, False)])
def test_requests_use_kst_day_boundaries(db_client, teacher, seeded_db, seconds, included):
    start = datetime.combine(datetime.now(KST).date(), time.min, KST)
    with seeded_db.begin() as connection:
        connection.execute(text("UPDATE requests SET created_at=:at WHERE id=:id"),
                           {"id": seed.REQUEST_COUGH, "at": (start + timedelta(seconds=seconds)).astimezone(UTC)})
    draft(db_client, teacher)
    ids = {l["source"]["request_id"] for n in notes(db_client, teacher) for l in n["content"]["items"]}
    assert (str(seed.REQUEST_COUGH) in ids) is included


@pytest.mark.parametrize("mismatch", ["classroom", "child", "guardian", "consultation", "complaint"])
def test_unrelated_requests_never_enter_writer(db_client, teacher, seeded_db, mismatch):
    sql, value = {"classroom": ("classroom_id", seed.CLASS_SUN), "child": ("child_id", seed.CHILD_OTHER),
                  "guardian": ("requester_id", seed.TEACHER), "consultation": ("type", "consultation"),
                  "complaint": ("type", "complaint")}[mismatch]
    with seeded_db.begin() as connection:
        connection.execute(text(f"UPDATE requests SET {sql}=:value WHERE id=:id"),
                           {"id": seed.REQUEST_COUGH, "value": value})
    draft(db_client, teacher)
    assert all(l["source"]["request_id"] != str(seed.REQUEST_COUGH)
               for n in notes(db_client, teacher) for l in n["content"]["items"])


@pytest.mark.parametrize("excluded", ["missing", "staff", "future", "expired", "other_class", "failed"])
def test_menu_is_nullable_and_excludes_unusable_documents(db_client, teacher, seeded_db, excluded):
    with seeded_db.begin() as connection:
        if excluded == "missing":
            connection.execute(text("DELETE FROM documents WHERE id=:id"), {"id": seed.MENU})
        elif excluded == "other_class":
            connection.execute(text("INSERT INTO document_classrooms (document_id,org_id,classroom_id) VALUES (:id,:org,:class)"),
                               {"id": seed.MENU, "org": seed.ORG, "class": seed.CLASS_SUN})
        else:
            column, value = {"staff": ("visibility", "staff"), "failed": ("ingest_status", "failed"),
                             "future": ("effective_from", datetime.now(KST).date() + timedelta(days=1)),
                             "expired": ("effective_to", datetime.now(KST).date() - timedelta(days=1))}[excluded]
            connection.execute(text(f"UPDATE documents SET {column}=:value WHERE id=:id"), {"id": seed.MENU, "value": value})
    draft(db_client, teacher)
    listed = notes(db_client, teacher)
    assert len(listed) == 20 and all(l["key"] != "meal" for n in listed for l in n["content"]["items"])


def test_notification_error_rolls_back_entire_batch(db_client, teacher, seeded_db):
    draft(db_client, teacher)
    for note in notes(db_client, teacher):
        assert db_client.patch(f"{BASE}/daily-notes/{note['id']}", headers=teacher, json={
            "confirm": True, "resolved_checks": [c["id"] for c in note["open_checks"]]}).status_code == 200
    with seeded_db.begin() as connection:
        connection.execute(text("ALTER TABLE notifications ADD CONSTRAINT test_reject_notification CHECK (kind<>'note_sent')"))
    try:
        response = db_client.post(BASE + "/daily-notes/send", headers=teacher, json=batch())
        assert response.status_code == 500 and response.json()["error"]["code"] == "INTERNAL_ERROR"
        with seeded_db.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM daily_notes WHERE status='ready'")) == 20
            assert connection.scalar(text("SELECT count(*) FROM notifications WHERE kind='note_sent'")) == 0
            assert connection.scalar(text("SELECT status FROM cards WHERE kind='daily_note'")) == "pending"
    finally:
        with seeded_db.begin() as connection:
            connection.execute(text("ALTER TABLE notifications DROP CONSTRAINT test_reject_notification"))


def test_note_save_error_rolls_back_all_children_and_marks_job_failed(db_client, teacher, seeded_db):
    with seeded_db.begin() as connection:
        connection.execute(text("""
            ALTER TABLE daily_notes ADD CONSTRAINT test_reject_child
            CHECK (child_id<>'00000000-0000-4000-8000-000000005401'::uuid)
        """))
    try:
        response = draft(db_client, teacher)
        assert response.status_code == 202
        status = db_client.get(f"{BASE}/daily-notes/drafts/{response.json()['input_id']}", headers=teacher).json()
        assert status["draft_status"] == "failed" and status["error"]["code"] == "UPSTREAM_UNAVAILABLE"
        assert notes(db_client, teacher) == []
        with seeded_db.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM daily_notes")) == 0
            assert connection.execute(text("""
                SELECT e.action FROM events e JOIN cards c ON c.id=e.card_id
                WHERE c.subject_type='daily_note_batch' AND c.subject_id=:id
            """), {"id": response.json()["input_id"]}).scalars().all() == ["tool_failed"]
    finally:
        with seeded_db.begin() as connection:
            connection.execute(text("ALTER TABLE daily_notes DROP CONSTRAINT test_reject_child"))


def test_notification_uses_schedule_and_does_not_delay_parent_at_night(db_client, teacher, seeded_db, monkeypatch):
    from app.modules.daily_notes import notes as db_notes
    from app.core.schedule import deliver_after
    draft(db_client, teacher)
    for note in notes(db_client, teacher):
        db_client.patch(f"{BASE}/daily-notes/{note['id']}", headers=teacher, json={
            "confirm": True, "resolved_checks": [c["id"] for c in note["open_checks"]]})
    calls = []

    def schedule(at, role):
        calls.append(role)
        return deliver_after(at, role)

    class Night(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 22, 23, 0, tzinfo=KST)

    monkeypatch.setattr(db_notes, "datetime", Night)
    monkeypatch.setattr(db_notes, "deliver_after", schedule)
    assert db_client.post(BASE + "/daily-notes/send", headers=teacher, json=batch()).json()["sent_count"] == 20
    with seeded_db.connect() as connection:
        after = connection.scalars(text("SELECT deliver_after FROM notifications WHERE kind='note_sent'")).all()
    assert calls == ["parent"] * 18 and len(after) == 18
    assert all(at == Night.now() for at in after)
