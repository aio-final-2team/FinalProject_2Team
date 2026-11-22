"""배포 실패가 기동으로 이어지지 않고 서버 포트가 닫히는지 확인해요."""

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("failure", ["dirty", "pull", "config", None])
def test_deployment_stops_before_starting_on_failure(tmp_path, failure):
    log = tmp_path / "calls"
    env_file = tmp_path / "server.env"
    env_file.write_text("# test\n")
    git = tmp_path / "git"
    git.write_text('''#!/usr/bin/env bash
echo "git $*" >> "$CALL_LOG"
if [[ "$1" == status && "$FAILURE" == dirty ]]; then echo ' M tracked'; fi
if [[ "$1" == pull && "$FAILURE" == pull ]]; then exit 42; fi
''')
    docker = tmp_path / "docker"
    docker.write_text('''#!/usr/bin/env bash
echo "docker $*" >> "$CALL_LOG"
if [[ "$*" == *'config --quiet' && "$FAILURE" == config ]]; then exit 42; fi
''')
    git.chmod(0o755)
    docker.chmod(0o755)
    env = dict(os.environ, PATH=f"{tmp_path}:{os.environ['PATH']}",
               CALL_LOG=str(log), FAILURE=failure or "")
    result = subprocess.run(["bash", str(ROOT / "infra/team-server/deploy.sh"), str(env_file)],
                            cwd=tmp_path, env=env, capture_output=True, text=True, check=False)
    calls = log.read_text()
    assert (result.returncode == 0) == (failure is None), result.stderr
    assert ("up -d --build" in calls) == (failure is None)
    assert ("git pull --ff-only" in calls) == (failure != "dirty")
    assert ("config --quiet" in calls) == (failure not in ("dirty", "pull"))


@pytest.mark.parametrize("backend", [None, "mock", "db"])
@pytest.mark.parametrize("override", [False, True])
@pytest.mark.parametrize("worker_profile", [False, True])
def test_server_compose_replaces_ports_and_preserves_database_volume(backend, override, worker_profile):
    if not shutil.which("docker"):
        pytest.skip("서버 Compose 검사는 Docker Compose가 필요해요.")
    version = subprocess.run(["docker", "compose", "version"], capture_output=True, check=False)
    if version.returncode:
        pytest.skip("Docker Compose 플러그인이 없어요.")
    env = dict(os.environ, POSTGRES_PASSWORD="test-only-password",
               DATABASE_URL="postgresql://test:password@db:5432/test",
               JWT_SECRET="test-server-compose-key-at-least-32-bytes",
               CORS_ORIGINS="https://app.example.invalid", VITE_API_BASE_URL="https://api.example.invalid",
               SERVER_API_PORT="18000", SERVER_WEB_PORT="15173")
    env.pop("COMPOSE_PROFILES", None)
    if backend is None:
        env.pop("DATA_BACKEND", None)
    else:
        env["DATA_BACKEND"] = backend
    image = "yuchion-api:test-restore" if override else "yuchion-api:local"
    if override:
        env["API_IMAGE"] = image
    else:
        env.pop("API_IMAGE", None)
    expected = {"SEED_DEMO": "false" if override else "true",
                "DAILY_NOTE_WRITER_TIMEOUT": "420" if override else "300",
                "NOTE_DRAFT_CONCURRENCY": "3" if override else "5",
                "OPENAI_API_KEY": "[TEST]-unused-model-key",
                "LAW_GO_KR_OC": "[TEST]-law-oc" if override else "",
                "DATA_GO_KR_API_KEY": "[TEST]-data-go-kr-key" if override else "",
                **{f"LLM_MODEL_{role}": f"[TEST]-{role}" for role in
                   ("DEFAULT", "SUPERVISOR", "DOCUMENT", "MEMORY", "CHECKER", "CODE")}}
    env.update(expected)
    if not override:
        env.pop("SEED_DEMO")
        env.pop("DAILY_NOTE_WRITER_TIMEOUT")
        env.pop("NOTE_DRAFT_CONCURRENCY")
        env.pop("LAW_GO_KR_OC")
        env.pop("DATA_GO_KR_API_KEY")
    command = ["docker", "compose", "--env-file", "/dev/null", "-f", "compose.yaml",
               "-f", "infra/team-server/compose.server.yaml"]
    if worker_profile:
        command += ["--profile", "worker"]
    result = subprocess.run([*command, "config", "--format", "json"],
                            cwd=ROOT, env=env, capture_output=True, text=True, check=True)
    services = json.loads(result.stdout)["services"]
    assert set(services) == {"api", "web", "db"} | ({"worker", "beat", "redis", "media-worker"} if worker_profile else set())
    assert not services["db"].get("ports")
    assert services["db"]["volumes"][0]["source"] == "postgres_data"
    for service, port in [("api", "18000"), ("web", "15173")]:
        assert len(services[service]["ports"]) == 1
        assert services[service]["ports"][0]["host_ip"] == "127.0.0.1"
        assert services[service]["ports"][0]["published"] == port
    for name in (["api", "worker", "beat", "media-worker"] if worker_profile else ["api"]):
        assert services[name]["environment"]["DATA_BACKEND"] == (backend or "db")
        assert services[name]["image"] == image
        assert {key: services[name]["environment"][key] for key in expected} == expected
    assert services["web"]["depends_on"]["api"]["condition"] == "service_healthy"
