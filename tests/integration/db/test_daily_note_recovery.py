"""알림장 초안 작업이 실패한 뒤 같은 반 묶음 카드에 incident 이력이 쌓이고 정상 복구·대체 응답·사람 이관으로 집계되는지 본다."""

from dataclasses import replace
from datetime import datetime, timedelta
from threading import Event

from sqlalchemy import text

from app.core.schedule import KST
from app.mock import seed
from app.modules.daily_notes import runner, stub_writer
from tests.integration.db.test_daily_notes_runner import BASE, draft, set_writer, teacher as teacher
from tools.daily_note_recovery import summarize


def history(engine, input_id):
    with engine.connect() as connection:
        return connection.execute(text("""
            SELECT e.action, e.actor_type, e.actor_id, e.detail FROM events e
            JOIN cards c ON (c.id,c.org_id)=(e.card_id,e.org_id)
            WHERE c.subject_type='daily_note_batch' AND c.subject_id=:id ORDER BY e.id
        """), {"id": input_id}).mappings().all()


def summary(engine):
    now = datetime.now(KST)
    with engine.connect() as connection:
        return summarize(connection, now - timedelta(days=1), now + timedelta(days=1))


def test_timeout_then_regenerate_is_one_recovered_incident_with_times(db_client, teacher, seeded_db, monkeypatch):
    release = Event()

    def slow(payload):
        assert release.wait(15)
        return stub_writer.write(payload)

    timeout = runner.settings.daily_note_writer_timeout
    set_writer(monkeypatch, slow)
    monkeypatch.setattr(runner, "settings", replace(runner.settings, daily_note_writer_timeout=0.05))
    try:
        input_id = draft(db_client, teacher).json()["input_id"]
    finally:
        release.set()
    set_writer(monkeypatch, stub_writer.write)
    monkeypatch.setattr(runner, "settings", replace(runner.settings, daily_note_writer_timeout=timeout))
    assert db_client.post(f"{BASE}/daily-notes/drafts/{input_id}/regenerate", headers=teacher).status_code == 202
    rows = history(seeded_db, input_id)
    assert [(r["action"], r["actor_type"]) for r in rows] == [
        ("tool_failed", "system"), ("agent_requeued", "user"), ("drafted", "agent")]
    failed, requeued, drafted = (r["detail"] for r in rows)
    detection = failed.pop("detection_ms")
    assert failed.pop("trigger") == "initial" and failed.pop("queue_wait_ms") >= 0
    assert detection >= 50
    assert failed == {"incident_id": input_id, "detected_failure": "writer_timeout", "retry_count": 0,
                      "fallback_used": False, "validation_result": "job_failed", "recovery_status": "pending"}
    assert requeued == {"incident_id": input_id, "selected_strategy": "retry_by_teacher", "retry_count": 0,
                        "trigger": "teacher_regenerate"}
    assert rows[1]["actor_id"] == seed.TEACHER
    with seeded_db.connect() as connection:
        needs_check = connection.scalar(text("SELECT count(*) FROM daily_notes WHERE status='needs_check'"))
    duration = drafted.pop("duration_ms")
    queue_wait = drafted.pop("queue_wait_ms")
    assert queue_wait >= 0 and drafted.pop("detection_ms") >= 0
    assert drafted.pop("trigger") == "teacher_regenerate"
    assert drafted == {"incident_id": input_id, "retry_count": 0, "saved": 20, "needs_check": needs_check,
                       "draft_failed": 0, "fallback_used": False, "validation_result": "all_children_passed",
                       "recovery_status": "recovered"}
    result = summary(seeded_db)
    assert result["incidents"] == [{
        "incident_id": input_id, "detected_failure": "writer_timeout", "selected_strategy": "retry_by_teacher",
        "retry_count": 0, "fallback_used": False, "recovery_status": "recovered",
        "validation_result": "all_children_passed", "duration_ms": duration, "detection_ms": detection,
        "trigger": "teacher_regenerate", "queue_wait_ms": queue_wait}]
    assert (result["recovered"], result["fallback"], result["handed_off"], result["pending"]) == (1, 0, 0, 0)
    assert result["by_strategy"] == {"retry_by_teacher": {"recovered": 1}}
    assert result["recovery_rate"] == 1 and result["duration_ms"] == (duration, duration) and duration >= 0
    assert result["detection_ms"] == (detection, detection)


def test_failed_retry_is_handed_off_then_partial_template_is_fallback(db_client, teacher, seeded_db, monkeypatch):
    def broken(payload):
        raise RuntimeError("[TEST] 모델 일시 실패")

    set_writer(monkeypatch, broken)
    input_id = draft(db_client, teacher).json()["input_id"]
    assert summary(seeded_db)["pending"] == 1
    path = f"{BASE}/daily-notes/drafts/{input_id}/regenerate"
    assert db_client.post(path, headers=teacher).status_code == 202
    rows = history(seeded_db, input_id)
    assert [r["detail"]["retry_count"] for r in rows] == [0, 0, 0]
    assert rows[2]["detail"]["detected_failure"] == "writer_error"
    result = summary(seeded_db)
    assert (result["recovered"], result["fallback"], result["handed_off"], result["recovery_rate"]) == (0, 0, 1, 0)
    assert result["duration_ms"] is None

    # 다음 시도에서 두 아이만 아이별 초안이 실패하면 템플릿으로 저장되고, 그 두 아이는 담임이 직접 쓴다.
    def partial(payload):
        rows = stub_writer.write(payload)
        return [stub_writer.failed_child(payload, c) if i < 2 else r
                for i, (c, r) in enumerate(zip(payload["children"], rows, strict=True))]

    set_writer(monkeypatch, partial)
    assert db_client.post(path, headers=teacher).status_code == 202
    drafted = history(seeded_db, input_id)[-1]["detail"]
    assert (drafted["retry_count"], drafted["saved"], drafted["draft_failed"]) == (0, 20, 2)
    assert (drafted["fallback_used"], drafted["validation_result"], drafted["recovery_status"]) == (
        True, "some_children_template", "fallback")
    result = summary(seeded_db)
    assert result["incidents"][0]["selected_strategy"] == "retry_by_teacher+template_fallback"
    assert result["by_strategy"] == {"retry_by_teacher+template_fallback": {"fallback": 1}}
    assert (result["recovered"], result["fallback"], result["handed_off"], result["handed_children"]) == (0, 1, 0, 2)
    assert result["recovery_rate"] == 0 and result["duration_ms"] == (drafted["duration_ms"],) * 2


def all_templates(payload):
    return [stub_writer.failed_child(payload, child) for child in payload["children"]]


def clean_drafts(payload):
    rows = stub_writer.write(payload)
    for row in rows:
        row["open_checks"] = []
    return rows


def test_all_templates_are_failed_incident_and_children_recover_only_after_clean_draft(
        db_client, teacher, seeded_db, monkeypatch):
    set_writer(monkeypatch, all_templates)
    input_id = draft(db_client, teacher).json()["input_id"]
    result = summary(seeded_db)
    assert len(result["incidents"]) == 1 and result["incidents"][0]["detected_failure"] == "all_children_template"
    assert result["handed_off"] == 1 and result["recovery_rate"] == 0 and result["handed_children"] == 20
    children = result["child_recovery"]
    assert (children["targets"], children["recovered"], children["not_retried"]) == (20, 0, 20)
    assert children["automatic_targets"] == 20 and children["automatic_recovery_rate"] == 0
    assert children["duration_ms"] is None

    # 교사가 한 아이를 직접 쓰고 확인한 것은 AI 복구가 아니다. 해당 아이는 재생성에서도 보호된다.
    from tests.integration.db.test_daily_notes_runner import notes
    target = notes(db_client, teacher)[0]
    assert db_client.patch(f"{BASE}/daily-notes/{target['id']}", headers=teacher, json={
        "content": target["content"], "confirm": True,
        "resolved_checks": [c["id"] for c in target["open_checks"]]}).status_code == 200
    set_writer(monkeypatch, stub_writer.write)
    path = f"{BASE}/daily-notes/drafts/{input_id}/regenerate"
    assert db_client.post(path, headers=teacher).status_code == 202
    children = summary(seeded_db)["child_recovery"]
    passing = {n["child_id"] for n in notes(db_client, teacher) if n["status"] == "draft"}
    assert children["targets"] == 20 and children["recovered"] == len(passing)
    assert {c["child_id"] for c in children["children"] if c["recovery_status"] == "recovered"} == passing
    assert children["teacher_regenerate"] == 20 and children["duration_ms"]["mean"] >= 0
    assert children["automatic_recovery_rate"] is None
    assert db_client.post(path, headers=teacher).status_code == 202
    assert summary(seeded_db)["child_recovery"]["targets"] == 20


def test_automatic_retry_count_and_recovery_time_exclude_teacher_and_queue_wait(
        db_client, teacher, seeded_db, monkeypatch):
    set_writer(monkeypatch, all_templates)
    input_id = draft(db_client, teacher).json()["input_id"]
    with seeded_db.begin() as connection:
        connection.execute(text("UPDATE events SET created_at=clock_timestamp()-interval '120 seconds'"))
        connection.execute(text("UPDATE daily_note_inputs SET draft_status='queued' WHERE id=:id"), {"id": input_id})
        runner.requeued(connection, input_id, "system")
        connection.execute(text("""
            UPDATE cards SET draft=draft || jsonb_build_object('draft_queued_at',clock_timestamp()-interval '30 seconds')
            WHERE subject_id=:id
        """), {"id": input_id})
    set_writer(monkeypatch, clean_drafts)
    runner.run_daily_note_drafts(input_id)
    result = summary(seeded_db)
    incident = result["incidents"][0]
    assert incident["retry_count"] == 1 and incident["trigger"] == "auto_retry"
    assert 30000 <= incident["queue_wait_ms"] < 35000
    assert 88000 <= incident["duration_ms"] < 95000
    children = result["child_recovery"]
    assert children["targets"] == children["recovered"] == children["automatic_targets"] == 20
    assert children["automatic_recovery_rate"] == 1
    assert 88000 <= children["duration_ms"]["mean"] < 95000
    assert db_client.post(f"{BASE}/daily-notes/drafts/{input_id}/regenerate", headers=teacher).status_code == 202
    assert history(seeded_db, input_id)[-1]["detail"]["retry_count"] == 1
    assert summary(seeded_db)["incidents"][0]["retry_count"] == 1


def test_legacy_all_template_history_counts_failure_without_inventing_child_recovery(
        db_client, teacher, seeded_db, monkeypatch):
    set_writer(monkeypatch, all_templates)
    input_id = draft(db_client, teacher).json()["input_id"]
    with seeded_db.begin() as connection:
        connection.execute(text("""
            UPDATE events SET detail=detail-'recovery_status'-'trigger'-'queue_wait_ms'-'detection_ms'
            WHERE action='drafted'
        """))
        connection.execute(text("""
            UPDATE events SET detail=detail-'draft_failed'-'open_check_count'-'trigger'
            WHERE action='daily_note_drafted'
        """))
    result = summary(seeded_db)
    assert result["handed_off"] == 1 and result["recovery_rate"] == 0
    assert result["incidents"][0]["detection_ms"] is None
    assert result["child_recovery"]["targets"] == result["child_recovery"]["recovered"] == 0
    assert result["child_recovery"]["unmeasurable"] == 20
    set_writer(monkeypatch, clean_drafts)
    assert db_client.post(f"{BASE}/daily-notes/drafts/{input_id}/regenerate", headers=teacher).status_code == 202
    with seeded_db.begin() as connection:
        connection.execute(text("UPDATE events SET detail=detail-'recovery_status' WHERE action='drafted'"))
    assert summary(seeded_db)["recovered"] == 1
    assert summary(seeded_db)["child_recovery"]["recovered"] == 0
