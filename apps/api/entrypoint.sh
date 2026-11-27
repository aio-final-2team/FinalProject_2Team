#!/usr/bin/env bash
set -Eeuo pipefail

# DB를 바꾸기 전에 백엔드 값과 JWT 키 등 앱 설정부터 검사해요.
python -c 'from app.core.config import settings'
if [[ "${DATA_BACKEND:-mock}" == "db" ]]; then
    python -m alembic -c apps/api/alembic.ini upgrade head
    if [[ "${SEED_DEMO:-true}" != "false" ]]; then
        python -m db.seeds.demo
        # 자료 창고 가상 원 자료 66개(T20). 같은 내용은 건너뛰어서 다시 켜도 안전해요.
        python -m db.seeds.documents
        python -m db.seeds.memories
    fi
fi

# 종료 신호를 uvicorn에 바로 전달해요. API 프로세스는 하나만 띄워요.
exec "$@"
