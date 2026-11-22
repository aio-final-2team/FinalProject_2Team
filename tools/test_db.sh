#!/usr/bin/env bash
# 중앙 PG와 다른 컨테이너는 쓰지 않는다. Docker가 호스트의 빈 포트를 고른다.
set -Eeuo pipefail
exec > >(sed -u 's/^/[TEST] /') 2>&1
cd "$(dirname "${BASH_SOURCE[0]}")/.."
export PATH="$PWD/.venv/bin:$PATH"

container="yuchion-test-pg-$(python -c 'import secrets; print(secrets.token_hex(6))')"
created=0
cleanup() {
    local result=$?
    if (( created )); then
        if ! docker rm -f "$container"; then
            echo "시험 컨테이너 정리 실패: $container"
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
# 임시 DB 시험용 키만 만든다. 실제 환경의 키나 mock 기본값을 쓰지 않는다.
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
    echo "시험 DB 준비 시간 초과"
    exit 1
fi
echo "임시 DB: $container, 포트 $port"
python -m pytest -q -rs tests/integration/db "$@"
# 공유 HTTP 시험은 fixture로 mock·DB를 고른다. 별도 프로세스로 설정을 분리한다.
DATA_BACKEND=mock python -m pytest -q -rs tests/integration/api/test_auth.py tests/integration/api/test_daily_notes.py \
    tests/integration/api/test_read_resources.py tests/integration/api/test_note_v05.py tests/integration/api/test_requests.py \
    tests/integration/api/test_cards.py tests/integration/api/test_complaints.py \
    tests/integration/api/test_consultations.py tests/integration/api/test_memories.py \
    tests/integration/api/test_consultation_reminders.py tests/integration/api/test_care_requests.py \
    tests/integration/api/test_feed.py tests/integration/api/test_video_consult.py tests/integration/api/test_voice_analysis.py \
    tests/integration/api/test_neighborhood_feed.py "$@"
