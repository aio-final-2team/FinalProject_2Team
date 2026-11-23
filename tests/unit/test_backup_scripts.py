"""백업·복원 스크립트가 --yes 없이는 아무것도 바꾸지 않고, 실패한 단계에서 멈추고, 보관 개수만 남기는지 본다."""

import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
CONFIG = {"name": "yuchion-test", "volumes": {"media_data": {"name": "yuchion-test_media_data"}},
          "services": {"db": {"image": "pgvector/pgvector:pg16"}}}
# 가짜 docker: 부른 명령을 적고, FAIL에 든 낱말이 명령에 있으면 실패한다.
FAKE_DOCKER = f'''#!/usr/bin/env bash
echo "docker $*" >> "$CALL_LOG"
if [[ -n "$FAIL" && "$*" == *"$FAIL"* ]]; then exit 42; fi
case "$*" in
  *"config --format json"*) echo '{json.dumps(CONFIG)}' ;;
  *"ps --services"*) printf 'api\\nweb\\ndb\\n' ;;
  *pg_dump*) echo "-- dump" ;;
  *alembic_version*) echo 0010 ;;
esac
'''


def run(tmp_path, script, *args, fail="", **env):
    docker = tmp_path / "bin" / "docker"
    docker.parent.mkdir(exist_ok=True)
    docker.write_text(FAKE_DOCKER)
    docker.chmod(0o755)
    (tmp_path / "server.env").write_text("# test\n")
    log = tmp_path / "calls"
    log.write_text("")
    environment = dict(os.environ, PATH=f"{docker.parent}:{os.environ['PATH']}", CALL_LOG=str(log), FAIL=fail, **env)
    result = subprocess.run(["bash", str(ROOT / "infra/backup" / script), *map(str, args)], cwd=tmp_path,
                            env=environment, capture_output=True, text=True, check=False)
    return result, log.read_text()


def backup_folder(path):
    path.mkdir(parents=True)
    for name in ("db.sql.gz", "media.tar.gz"):
        (path / name).write_bytes(name.encode())
    sums = {name: hashlib.sha256(name.encode()).hexdigest() for name in ("db.sql.gz", "media.tar.gz")}
    (path / "meta.json").write_text(json.dumps({"created_at": "2026-11-23T05:00:00Z", "sha256": sums}))
    return path


def test_restore_without_yes_only_prints_steps_and_checks_files(tmp_path):
    backup = backup_folder(tmp_path / "backups" / "20261123T050000Z")
    result, calls = run(tmp_path, "restore.sh", backup, tmp_path / "server.env")
    assert result.returncode == 0, result.stderr
    assert [line for line in result.stdout.splitlines() if line.startswith("== ")][-1].startswith("== 6.")
    assert all(" config " in line for line in calls.splitlines()), calls
    (backup / "media.tar.gz").write_bytes(b"changed")
    result, calls = run(tmp_path, "restore.sh", backup, tmp_path / "server.env", "--yes")
    assert result.returncode == 1 and "meta.json과 달라요" in result.stderr and " exec " not in calls


def test_restore_stops_at_the_failing_step(tmp_path):
    backup = backup_folder(tmp_path / "backups" / "20261123T050000Z")
    result, calls = run(tmp_path, "restore.sh", backup, tmp_path / "server.env", "--yes", fail=" stop ")
    assert result.returncode == 42
    assert "after_restore export --since 2026-11-23T05:00:00Z" in calls and "stop api" in calls
    assert "DROP DATABASE" not in calls and " start " not in calls


def test_restore_stops_when_current_db_is_unreadable_unless_skip_export(tmp_path):
    backup = backup_folder(tmp_path / "backups" / "20261123T050000Z")
    result, calls = run(tmp_path, "restore.sh", backup, tmp_path / "server.env", "--yes", fail="alembic_version")
    assert result.returncode == 1 and "SKIP_EXPORT=1" in result.stderr
    assert "after_restore" not in calls and " stop " not in calls and "DROP DATABASE" not in calls
    # SKIP_EXPORT=1이면 export 없이 2단계로 넘어간다. 2단계를 일부러 실패시켜 거기까지 간 것만 본다.
    result, calls = run(tmp_path, "restore.sh", backup, tmp_path / "server.env", "--yes", fail=" stop ",
                        SKIP_EXPORT="1")
    assert result.returncode == 42 and "stop api" in calls
    assert "alembic_version" not in calls and "after_restore" not in calls
    dry_run = run(tmp_path, "restore.sh", backup, tmp_path / "server.env", SKIP_EXPORT="1")[0].stdout
    assert "== 1. 지금 DB에서 백업 뒤 변경 뽑기 (SKIP_EXPORT=1이라 건너뜀)" in dry_run


def test_backup_keeps_only_newest_complete_folders(tmp_path):
    root = tmp_path / "backups"
    for stamp in ("20261101T000000Z", "20261102T000000Z", "20261103T000000Z"):
        backup_folder(root / stamp)
    (root / "20261104T000000Z.partial").mkdir()
    (root / "keep-me").mkdir()
    result, calls = run(tmp_path, "backup.sh", tmp_path / "server.env", BACKUP_DIR=str(root), BACKUP_KEEP="2")
    assert result.returncode == 0, result.stderr
    names = sorted(p.name for p in root.iterdir())
    assert names[:2] == ["20261103T000000Z", "20261104T000000Z.partial"] and names[-1] == "keep-me"
    new = root / names[2]
    assert json.loads((new / "meta.json").read_text())["alembic_version"] == "0010"
    assert "media:ro" in calls and len(names) == 4
