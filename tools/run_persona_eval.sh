#!/usr/bin/env bash
# 평가 전용 PostgreSQL을 만들고 원·문서 시드 후 정리한다. 공용 DB에는 연결하지 않는다.
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
export PATH="$PWD/.venv/bin:$PATH"

container="yuchion-persona-pg-$(python -c 'import secrets; print(secrets.token_hex(6))')"
created=0
cleanup() {
    local result=$?
    if (( created )); then
        if ! docker rm -fv "$container"; then
            echo "평가용 DB 컨테이너 정리 실패: $container"
            result=1
        fi
    fi
    exit "$result"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

docker create --name "$container" --publish 127.0.0.1::5432 \
    --env POSTGRES_USER=yuchion --env POSTGRES_PASSWORD=yuchion_test \
    --env POSTGRES_DB=yuchion_test pgvector/pgvector:pg16
created=1
docker start "$container"
port=$(docker port "$container" 5432/tcp)
port=${port##*:}
export TEST_DATABASE_URL="postgresql+psycopg://yuchion:yuchion_test@127.0.0.1:$port/yuchion_test"
export DATABASE_URL="$TEST_DATABASE_URL"
export TEST_DB_CONTAINER="$container"
export DATA_BACKEND=db
export EMBEDDING_MODEL=
export JWT_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"

ready=0
for (( attempt=0; attempt<60; attempt++ )); do
    if docker exec "$container" pg_isready -U yuchion -d yuchion_test >/dev/null 2>&1; then
        ready=1
        break
    fi
    sleep 1
done
if (( ! ready )); then
    docker logs "$container"
    echo "평가용 PostgreSQL 준비 시간 초과"
    exit 1
fi

echo "임시 평가 DB: 127.0.0.1:$port ($container)"
python -m alembic -c apps/api/alembic.ini upgrade head
PYTHONPATH=apps/api:. python -m db.seeds.demo
PYTHONPATH=apps/api:. python -m db.seeds.documents
PYTHONPATH=apps/api:. python tools/eval_persona.py "$@"
