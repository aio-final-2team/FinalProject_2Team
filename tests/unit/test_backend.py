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
    ("db", False, "T24·T27"),
    ("typo", False, "DATA_BACKEND"),
])
def test_backend_selection(backend, success, message):
    env = {key: value for key, value in os.environ.items() if key not in ("DATA_BACKEND", "DATABASE_URL")}
    env["PYTHONPATH"] = str(ROOT / "apps/api")
    if backend is not None:
        env["DATA_BACKEND"] = backend
    result = subprocess.run([sys.executable, "-c", "import sys; from app.main import app; "
                             "assert 'app.core.db' not in sys.modules; print('mock_without_db')"],
                            cwd=ROOT, env=env, capture_output=True, text=True)
    assert (result.returncode == 0) is success
    assert message in result.stdout + result.stderr


def test_initial_sql_is_immutable():
    # 설계 최신판이 바뀌어도 적용한 v0.7 SQL은 고치지 않는다.
    applied = (ROOT / "apps/api/migrations/sql/0001_initial.sql").read_bytes()
    assert sha256(applied).hexdigest() == "0aa90b95c718f50240e05ebf04aafc14cfe2a2f35e11a56016d9a412f6e155ee"
