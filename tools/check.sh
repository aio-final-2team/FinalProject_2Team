#!/usr/bin/env bash
set -Eeuo pipefail
exec > >(sed -u 's/^/[TEST] /') 2>&1
cd "$(dirname "${BASH_SOURCE[0]}")/.."
export PATH="$PWD/.venv/bin:$PATH"

# 셸에 DB 시험 변수가 남아 있어도 이 명령은 mock 시험만 실행해요.
export DATA_BACKEND=mock
unset TEST_DATABASE_URL TEST_DB_CONTAINER DATABASE_URL
ruff check .
python -m pytest -q "$@"
