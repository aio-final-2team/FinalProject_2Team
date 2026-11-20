"""기본 mock을 유지하고 잘못된 백엔드 선택으로 메모리 구현이 실행되지 않게 한다."""

from hashlib import sha256
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("backend,success,message", [
    (None, True, "mock_without_db"),
    ("mock", True, "mock_without_db"),
    ("db", True, "db_without_mock"),
    ("typo", False, "DATA_BACKEND"),
])
def test_backend_selection(backend, success, message):
    env = {key: value for key, value in os.environ.items() if key not in ("DATA_BACKEND", "DATABASE_URL")}
    env["PYTHONPATH"] = str(ROOT / "apps/api")
    env["JWT_SECRET"] = "[TEST]-backend-selection-key-32-bytes-min"
    if backend is not None:
        env["DATA_BACKEND"] = backend
    check = ("assert 'app.mock.store' not in sys.modules; print('db_without_mock')" if backend == "db"
             else "assert 'app.core.db' not in sys.modules; print('mock_without_db')")
    result = subprocess.run([sys.executable, "-c", "import sys; from app.main import app; " + check],
                            cwd=ROOT, env=env, capture_output=True, text=True)
    assert (result.returncode == 0) is success
    assert message in result.stdout + result.stderr


def test_initial_sql_is_immutable():
    # 설계 최신판이 바뀌어도 적용한 v0.7 SQL은 고치지 않는다.
    applied = (ROOT / "apps/api/migrations/sql/0001_initial.sql").read_bytes()
    assert sha256(applied).hexdigest() == "0aa90b95c718f50240e05ebf04aafc14cfe2a2f35e11a56016d9a412f6e155ee"


@pytest.mark.parametrize("value,valid", [(None, True), ("0.05", True), ("0", False), ("-1", False),
                                         ("inf", False), ("nan", False), ("bad", False)])
def test_writer_timeout_requires_finite_positive_seconds(monkeypatch, value, valid):
    from app.core.config import load_settings
    if value is None:
        monkeypatch.delenv("DAILY_NOTE_WRITER_TIMEOUT", raising=False)
    else:
        monkeypatch.setenv("DAILY_NOTE_WRITER_TIMEOUT", value)
    if valid:
        assert load_settings().daily_note_writer_timeout == (120 if value is None else float(value))
    else:
        with pytest.raises(ValueError):
            load_settings()


@pytest.mark.parametrize("backend", ["mock", "db"])
@pytest.mark.parametrize("secret,valid_for_db", [
    (None, False),
    ("", False),
    ("local-dev-only-change-me-32-bytes-min", False),
    (next(line.split("=", 1)[1] for line in (ROOT / ".env.example").read_text().splitlines()
          if line.startswith("JWT_SECRET=")), False),
    ("a" * 31, False),
    ("가" * 10, False),
    ("a" * 32, True),
    ("가" * 11, True),
], ids=["missing", "empty", "mock_default", "env_example", "31_bytes", "30_utf8_bytes",
        "32_bytes", "33_utf8_bytes"])
def test_app_startup_requires_separate_db_jwt_key(backend, secret, valid_for_db):
    env = {key: value for key, value in os.environ.items()
           if key not in ("JWT_SECRET", "DATABASE_URL")}
    env.update(DATA_BACKEND=backend, PYTHONPATH=str(ROOT / "apps/api"))
    if secret is not None:
        env["JWT_SECRET"] = secret
    result = subprocess.run([sys.executable, "-c", "from app.main import app"],
                            cwd=ROOT, env=env, capture_output=True, text=True)
    assert (result.returncode == 0) is (backend == "mock" or valid_for_db)
    if backend == "db" and not valid_for_db:
        assert "ValueError: JWT_SECRET:" in result.stderr
