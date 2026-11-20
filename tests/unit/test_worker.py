"""기본 API 실행·워커 설정과 큐 장애 경계를 확인해요. 외부 서비스는 부르지 않아요."""

import json
import os
from dataclasses import replace
from pathlib import Path
import subprocess
from uuid import uuid4

import anyio
from fastapi import BackgroundTasks
import pytest

from app import worker
from app.core import config, jobs

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("value,valid", [(None, True), ("api", True), ("worker", True), ("typo", False)])
def test_run_in_config(monkeypatch, value, valid):
    monkeypatch.delenv("RUN_IN", raising=False)
    if value is not None:
        monkeypatch.setenv("RUN_IN", value)
    if valid:
        assert config.load_settings().run_in == (value or "api")
    else:
        with pytest.raises(ValueError, match="RUN_IN"):
            config.load_settings()


def test_worker_dispatch_publishes_only_id_after_background_starts(monkeypatch):
    monkeypatch.setattr(jobs, "settings", replace(jobs.settings, run_in="worker"))
    captured = []
    monkeypatch.setattr(worker.daily_note_drafts, "apply_async", lambda **kw: captured.append(kw))
    object_id, tasks = uuid4(), BackgroundTasks()
    jobs.dispatch("daily_note", object_id, tasks)
    assert captured == []
    anyio.run(tasks)
    assert captured == [{"args": [str(object_id)], "retry": False}]


def test_publish_failure_keeps_private_error_out_of_logs(monkeypatch, caplog):
    def fail(**kwargs):
        raise ConnectionError("[TEST] private memo and secret")
    monkeypatch.setattr(worker.request_agent, "apply_async", fail)
    jobs.publish("request", uuid4())
    assert "ConnectionError" in caplog.text
    assert "private memo" not in caplog.text and "secret" not in caplog.text


def test_mock_periodic_tasks_never_open_database(monkeypatch):
    from app.core import db
    monkeypatch.setattr(worker, "settings", replace(worker.settings, data_backend="mock", run_in="worker"))
    def fail():
        pytest.fail("mock 워커가 DB를 열면 안 돼요")
    monkeypatch.setattr(db, "get_engine", fail)
    assert worker.sweep.apply().get() == 0
    assert worker.deliver_notifications.apply().get() == 0
    worker.daily_note_drafts.apply(args=[str(uuid4())]).get()
    worker.request_agent.apply(args=[str(uuid4())]).get()


def test_beat_intervals():
    entries = worker.celery_app.conf.beat_schedule
    assert {v["task"]: v["schedule"] for v in entries.values()} == {
        "yuchion.sweep": 300.0, "yuchion.deliver_notifications": 60.0}


def test_worker_compose_shares_api_configuration_and_initializes_database_once():
    result = subprocess.run(["docker", "compose", "--env-file", "/dev/null", "--profile", "worker",
                             "config", "--format", "json"], cwd=ROOT, capture_output=True, text=True,
                            env={**os.environ, "DATA_BACKEND": "db", "RUN_IN": "worker"}, check=True)
    services = json.loads(result.stdout)["services"]
    assert set(services) == {"api", "db", "web", "redis", "worker", "beat"}
    for name in ("worker", "beat"):
        assert services[name]["environment"] == services["api"]["environment"]
        assert services[name]["entrypoint"] == ["celery"]
        assert services[name]["depends_on"]["api"]["condition"] == "service_healthy"
        assert services[name]["depends_on"]["redis"]["condition"] == "service_healthy"
    assert not services["redis"].get("ports")
    assert "--pool=solo" in services["worker"]["command"]
