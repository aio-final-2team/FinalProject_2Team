"""컨테이너 시작 순서와 실패 시 서버를 띄우지 않는 동작을 확인해요."""

import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
ENTRYPOINT = ROOT / "apps/api/entrypoint.sh"


@pytest.mark.parametrize("backend,fail_step,seed_demo", [
    (None, None, None), ("mock", None, None), ("db", None, None),
    ("db", "settings", None), ("db", "migrate", None), ("db", "seed", None),
    ("db", "documents", None), ("db", None, "true"), ("db", None, "false"), ("db", "migrate", "false"),
])
def test_startup_sequence_and_failure(tmp_path, backend, fail_step, seed_demo):
    log = tmp_path / "calls"
    python = tmp_path / "python"
    python.write_text('''#!/usr/bin/env bash
case "$*" in
    -c*) step=settings ;;
    *alembic*) step=migrate ;;
    *db.seeds.demo*) step=seed ;;
    *db.seeds.documents*) step=documents ;;
    *) exit 99 ;;
esac
echo "$step" >> "$CALL_LOG"
[[ "$step" != "${FAIL_STEP:-}" ]] || exit 42
''')
    server = tmp_path / "server"
    server.write_text('''#!/usr/bin/env bash
echo server >> "$CALL_LOG"
printf '%s\n' "$@" >> "$CALL_LOG"
''')
    python.chmod(0o755)
    server.chmod(0o755)
    env = {key: value for key, value in os.environ.items() if key not in ("DATA_BACKEND", "SEED_DEMO")}
    env.update(PATH=f"{tmp_path}:{env['PATH']}", CALL_LOG=str(log), FAIL_STEP=fail_step or "")
    if backend is not None:
        env["DATA_BACKEND"] = backend
    if seed_demo is not None:
        env["SEED_DEMO"] = seed_demo
    result = subprocess.run(["bash", str(ENTRYPOINT), str(server), "argument with spaces"],
                            cwd=ROOT, env=env, capture_output=True, text=True, check=False)
    expected = ["settings"]
    if backend == "db":
        expected += ["migrate"]
        if seed_demo != "false":
            expected += ["seed", "documents"]
    if fail_step:
        expected = expected[:expected.index(fail_step) + 1]
    else:
        expected += ["server", "argument with spaces"]
    assert result.returncode == (42 if fail_step else 0), result.stderr
    assert log.read_text().splitlines() == expected


@pytest.mark.parametrize("backend,error", [("db", "JWT_SECRET:"), ("typo", "DATA_BACKEND:")])
def test_invalid_configuration_stops_before_database_or_server(tmp_path, backend, error):
    env = dict(os.environ, DATA_BACKEND=backend, JWT_SECRET="short",
               DATABASE_URL="postgresql://invalid@127.0.0.1:1/unused",
               PYTHONPATH=str(ROOT / "apps/api"))
    env["PATH"] = f"{Path(sys.executable).parent}:{env['PATH']}"
    started = tmp_path / "server-started"
    result = subprocess.run(["bash", str(ENTRYPOINT), "touch", str(started)],
                            cwd=ROOT, env=env, capture_output=True, text=True, check=False)
    assert result.returncode != 0
    assert error in result.stderr
    assert "sqlalchemy" not in result.stderr
    assert not started.exists()


@pytest.mark.parametrize("script", [ENTRYPOINT, ROOT / "tools/check.sh", ROOT / "tools/smoke.sh",
                                    ROOT / "infra/team-server/deploy.sh"])
def test_shell_syntax(script):
    subprocess.run(["bash", "-n", str(script)],
                   cwd=ROOT, check=True, capture_output=True, text=True)
