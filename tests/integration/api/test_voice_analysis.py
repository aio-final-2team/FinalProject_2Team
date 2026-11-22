"""[TEST] 코드로 만든 무음 WAV만 쓰고 분석·외부 호출은 가짜로 검사해요."""

from dataclasses import replace
from datetime import timedelta
from io import BytesIO
from threading import Event, Thread
from types import SimpleNamespace
from uuid import UUID, uuid4
import wave

import pytest
from sqlalchemy import text

from app import backend, worker
from app.core import config, jobs, media, voice_analysis as rules
from app.core.auth import CurrentUser, current_user
from app.main import app
from app.mock import seed, store, voice_analyses
from app.modules.consultations import voice_runner as runner, voice_stub
from tests.integration.api.test_video_consult import events

BASE = f"/api/v1/consultations/{seed.VIDEO_BOOKING}/voice-analyses"


@pytest.fixture(autouse=True, params=["mock", "db"])
def voice_backend(request, monkeypatch, tmp_path, _reset_store):
    settings = replace(config.settings, feature_video_consult=False, feature_voice_analysis=True,
                       consult_voice_analyzer="app.modules.consultations.voice_stub:analyze", run_in="api",
                       media_dir=str(tmp_path))
    for module in (config, rules, runner, media, jobs, worker):
        monkeypatch.setattr(module, "settings", settings)
    if request.param == "db":
        engine = request.getfixturevalue("seeded_db")
        from app.core import users
        from app.modules.consultations import voice as module
    else:
        engine, users, module = None, store, voice_analyses
        store.reset()
    monkeypatch.setattr(backend, "users", users)
    monkeypatch.setattr(backend, "voice_analyses", module)
    return SimpleNamespace(engine=engine, root=tmp_path)


def wav():
    buffer = BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b"\0\0" * 800)
    return buffer.getvalue()


def post(client, actor, *, data=None, synthetic="true", **kwargs):
    return client.post(BASE, headers=actor, files={"file": ("spoof.txt", wav() if data is None else data, "text/plain")},
                       data={} if synthetic is None else {"synthetic": synthetic}, **kwargs)


def files(ctx):
    return [p for p in ctx.root.rglob("*") if p.is_file() and p.suffix != ".png"]


def pending(client, teacher, monkeypatch):
    monkeypatch.setattr(jobs, "dispatch", lambda *args: None)
    response = post(client, teacher)
    assert response.status_code == 202, response.text
    return UUID(response.json()["id"])


def test_success_deletes_audio_and_keeps_only_results(voice_backend, client, teacher, director, monkeypatch):
    observed = []
    def analyze(path):
        row = client.get(BASE, headers=teacher).json()["items"][0]
        observed.append(row["status"])
        assert path.is_file() and row["started_at"]
        return voice_stub.analyze(path)
    monkeypatch.setattr(runner, "analyze", analyze)
    queued = post(client, teacher)
    assert queued.status_code == 202 and queued.json()["status"] == "queued"
    row = client.get(f"/api/v1/voice-analyses/{queued.json()['id']}", headers=director).json()
    assert observed == ["running"] and row["status"] == "succeeded"
    assert row["duration_seconds"] == 0.1 and len(row["sha256"]) == 64 and "가상" in row["transcript"]
    assert not files(voice_backend) and "storage_path" not in row and row["completed_at"]
    assert client.get(BASE, headers=teacher).headers["Cache-Control"] == "private, no-store"
    for action in ("voice_analysis_requested", "voice_analysis_completed"):
        ev = events(voice_backend, action)
        assert len(ev) == 1 and ev[0]["request_id"] == seed.VIDEO_REQUEST
        assert "transcript" not in str(ev[0]["detail"])


@pytest.mark.parametrize("value", [None, "false"])
def test_synthetic_required(voice_backend, client, teacher, value):
    assert post(client, teacher, synthetic=value).status_code == 422
    assert not files(voice_backend)


@pytest.mark.parametrize("data,status", [(b"not audio", 422), (b"x" * (10 * 1024 * 1024 + 1), 413)])
def test_invalid_or_large_upload_rejected(voice_backend, client, teacher, data, status):
    assert post(client, teacher, data=data).status_code == status
    assert not files(voice_backend)


@pytest.mark.parametrize("actor", ["director", "parent", "teacher_other"])
def test_only_booking_teacher_can_upload(voice_backend, client, request, actor):
    assert post(client, request.getfixturevalue(actor)).status_code == 403
    assert events(voice_backend, "permission_denied")[-1]["request_id"] == seed.VIDEO_REQUEST
    assert not files(voice_backend)


@pytest.mark.parametrize("actor", ["parent", "teacher_other"])
def test_result_read_forbidden_and_audited(voice_backend, client, teacher, request, actor):
    row = post(client, teacher).json()
    for path in (BASE, f"/api/v1/voice-analyses/{row['id']}"):
        assert client.get(path, headers=request.getfixturevalue(actor)).status_code == 403
    assert len(events(voice_backend, "permission_denied")) == 2


def test_other_org_and_missing_are_404(voice_backend, client, teacher):
    row = post(client, teacher).json()
    app.dependency_overrides[current_user] = lambda: CurrentUser(id=seed.TEACHER, org_id=uuid4(), role="teacher")
    try:
        assert post(client, teacher).status_code == 404
        for path in (BASE, f"/api/v1/voice-analyses/{row['id']}"):
            assert client.get(path, headers=teacher).status_code == 404
        assert not events(voice_backend, "permission_denied")
    finally:
        del app.dependency_overrides[current_user]
    assert client.get(f"/api/v1/voice-analyses/{uuid4()}", headers=teacher).status_code == 404


@pytest.mark.parametrize("failure", ["exception", "bad_result", "timeout"])
def test_failure_or_timeout_deletes_audio(voice_backend, client, teacher, monkeypatch, failure):
    gate = Event()
    def fail(path):
        if failure == "timeout":
            gate.wait(2)
            return voice_stub.analyze(path)
        if failure == "bad_result":
            return {"transcript": "[TEST]", "result": {"summary": "1\n2\n3\n4"}}
        raise RuntimeError("[TEST] secret transcript must not leak")
    monkeypatch.setattr(runner, "analyze", fail)
    if failure == "timeout":
        monkeypatch.setattr(rules, "VOICE_TIMEOUT", 0.01)
    try:
        row = post(client, teacher).json()
        saved = client.get(f"/api/v1/voice-analyses/{row['id']}", headers=teacher).json()
        assert saved["status"] == "failed" and not files(voice_backend) and not saved["transcript"]
    finally:
        gate.set()


def test_duplicate_run_is_claimed_once(voice_backend, client, teacher, monkeypatch):
    analysis_id = pending(client, teacher, monkeypatch)
    entered, release = Event(), Event()
    def slow(path):
        entered.set()
        assert release.wait(5)
        return voice_stub.analyze(path)
    monkeypatch.setattr(runner, "analyze", slow)
    thread = Thread(target=runner.run_voice_analysis, args=(analysis_id,))
    thread.start()
    try:
        assert entered.wait(5)
        runner.run_voice_analysis(analysis_id)
    finally:
        release.set()
        thread.join(5)
    assert not thread.is_alive() and len(events(voice_backend, "voice_analysis_completed")) == 1


def test_sweep_fails_stale_running_and_ignores_late_results(voice_backend, client, teacher, monkeypatch):
    analysis_id = pending(client, teacher, monkeypatch)
    backend.voice_analyses.claim(analysis_id)
    if voice_backend.engine:
        with voice_backend.engine.begin() as c:
            c.execute(text("UPDATE consultation_voice_analyses SET started_at=now()-interval '6 minutes' WHERE id=:id"),
                      {"id": analysis_id})
    else:
        store.state().voice_analyses[analysis_id]["started_at"] -= timedelta(minutes=6)
    assert backend.voice_analyses.sweep() == 1
    backend.voice_analyses.finish(analysis_id, {**voice_stub.analyze(None), "duration_seconds": 1})
    assert backend.voice_analyses.get(CurrentUser(id=seed.TEACHER, org_id=seed.ORG, role="teacher"), analysis_id)["status"] == "failed"
    assert not files(voice_backend) and backend.voice_analyses.sweep() == 0


def test_worker_dispatch_default_queue_and_shared_runner(voice_backend, client, teacher, monkeypatch):
    monkeypatch.setattr(jobs, "settings", replace(jobs.settings, run_in="worker"))
    calls = []
    monkeypatch.setattr(worker.voice_analysis, "apply_async", lambda **kw: calls.append(kw))
    row = post(client, teacher).json()
    assert row["status"] == "queued" and calls == [{"args": [row["id"]], "retry": False}]
    assert worker.celery_app.amqp.router.route({}, "yuchion.voice_analysis")["queue"].name == "default"
    monkeypatch.setattr(worker, "settings", replace(worker.settings, data_backend="db", run_in="worker"))
    worker.voice_analysis.run(row["id"])
    assert client.get(BASE, headers=teacher).json()["items"][0]["status"] == "succeeded" and not files(voice_backend)


def test_openai_uses_stt_and_document_role(voice_backend, client, teacher, monkeypatch):
    import openai
    from agents import llm
    calls = []
    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.audio = SimpleNamespace(transcriptions=SimpleNamespace(create=self.transcribe))
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def transcribe(self, **kwargs):
            assert kwargs["file"].read().startswith(b"RIFF")
            calls.append(kwargs["model"])
            return SimpleNamespace(text="[TEST] 가상 녹취")
    class FakeModel:
        def __init__(self, role):
            calls.append(role)
        def json(self, system, user):
            assert user == "[TEST] 가상 녹취"
            return voice_stub.analyze(None)["result"]
    monkeypatch.setattr(openai, "OpenAI", FakeOpenAI)
    monkeypatch.setattr(llm, "OpenAIModel", FakeModel)
    monkeypatch.setattr(runner, "settings", replace(runner.settings, consult_voice_analyzer="openai"))
    post(client, teacher)
    assert calls == ["gpt-4o-mini-transcribe", "DOCUMENT"] and not files(voice_backend)


def test_disabled_routes_are_common_404(voice_backend, client, teacher, monkeypatch):
    monkeypatch.setattr(rules, "settings", replace(rules.settings, feature_voice_analysis=False))
    for actor in (teacher, {}):
        assert post(client, actor).status_code == 404
        for path in (BASE, f"/api/v1/voice-analyses/{uuid4()}"):
            response = client.get(path, headers=actor)
            assert response.status_code == 404 and response.json()["error"]["code"] == "NOT_FOUND"


def test_tts_without_key_only_guides(voice_backend, monkeypatch, capsys):
    from tools.make_virtual_voice import make
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    output = voice_backend.root / "demo.wav"
    make(output)
    assert not output.exists() and "OPENAI_API_KEY" in capsys.readouterr().out


def test_tts_joins_two_generated_voices(voice_backend, monkeypatch):
    import openai
    from tools.make_virtual_voice import make
    calls = []
    class FakeTTS:
        def __init__(self, **kwargs):
            self.audio = SimpleNamespace(speech=SimpleNamespace(create=self.create))
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(content=wav())
    monkeypatch.setenv("OPENAI_API_KEY", "[TEST] fake")
    monkeypatch.setattr(openai, "OpenAI", FakeTTS)
    output = voice_backend.root / "demo.wav"
    make(output)
    with wave.open(str(output)) as audio:
        assert audio.getnframes() == 1600
    assert [c["voice"] for c in calls] == ["coral", "onyx"]
    assert all(c["response_format"] == "wav" and "가상" in c["input"] for c in calls)
