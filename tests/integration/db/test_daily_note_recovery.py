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
    assert detection >= 50
    assert failed == {"incident_id": input_id, "detected_failure": "writer_timeout", "retry_count": 0,
                      "fallback_used": False, "validation_result": "job_failed", "recovery_status": "pending"}
    assert requeued == {"incident_id": input_id, "selected_strategy": "retry_by_teacher", "retry_count": 1}
    assert rows[1]["actor_id"] == seed.TEACHER
    with seeded_db.connect() as connection:
        needs_check = connection.scalar(text("SELECT count(*) FROM daily_notes WHERE status='needs_check'"))
    duration = drafted.pop("duration_ms")
    assert drafted == {"incident_id": input_id, "retry_count": 1, "saved": 20, "needs_check": needs_check,
                       "draft_failed": 0, "fallback_used": False, "validation_result": "all_children_passed",
                       "recovery_status": "recovered"}
    result = summary(seeded_db)
    assert result["incidents"] == [{
        "incident_id": input_id, "detected_failure": "writer_timeout", "selected_strategy": "retry_by_teacher",
        "retry_count": 1, "fallback_used": False, "recovery_status": "recovered",
        "validation_result": "all_children_passed", "duration_ms": duration, "detection_ms": detection}]
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
    assert [r["detail"]["retry_count"] for r in rows] == [0, 1, 1]
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
    assert (drafted["retry_count"], drafted["saved"], drafted["draft_failed"]) == (2, 20, 2)
    assert (drafted["fallback_used"], drafted["validation_result"], drafted["recovery_status"]) == (
        True, "some_children_template", "fallback")
    result = summary(seeded_db)
    assert result["incidents"][0]["selected_strategy"] == "retry_by_teacher+template_fallback"
    assert result["by_strategy"] == {"retry_by_teacher+template_fallback": {"fallback": 1}}
    assert (result["recovered"], result["fallback"], result["handed_off"], result["handed_children"]) == (0, 1, 0, 2)
    assert result["recovery_rate"] == 0 and result["duration_ms"] == (drafted["duration_ms"],) * 2
