#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."

if (( $# > 1 )); then
    echo "사용법: $0 [환경 파일]" >&2
    exit 2
fi
env_file=${1:-infra/team-server/.env.server}
if [[ ! -f "$env_file" ]]; then
    echo "환경 파일이 없어요. .env.server.example을 복사하고 실제 값을 넣어 주세요." >&2
    exit 1
fi
if [[ -n "$(git status --porcelain)" ]]; then
    echo "작업 폴더에 변경이 있어요. 정리한 뒤 다시 배포해 주세요." >&2
    exit 1
fi

# 현재 브랜치의 upstream만 갱신해요. 브랜치 전환이나 강제 덮어쓰기는 하지 않아요.
git pull --ff-only
export GIT_SHA=$(git rev-parse HEAD) DEPLOYED_AT=$(date -Iseconds)
compose=(docker compose --env-file "$env_file" -f compose.yaml -f infra/team-server/compose.server.yaml)
"${compose[@]}" config --quiet
# 직접 빌드하는 이미지(api·web)의 지금 판을 :prev로 남겨요. 새 판이 안 뜨면 다시 빌드하지 않고 바로 되돌려요(DEPLOY.md 7-1).
mapfile -t built < <("${compose[@]}" config --format json | python3 -c '
import json, sys
c = json.load(sys.stdin)
project = c["name"]
print("\n".join(sorted({s.get("image") or project + "-" + n for n, s in c["services"].items() if "build" in s})))')
for image in "${built[@]}"; do
    if docker image inspect "$image" >/dev/null 2>&1; then
        docker tag "$image" "${image%:*}:prev"
        echo "직전 이미지를 남겼어요: ${image%:*}:prev"
    fi
done
"${compose[@]}" up -d --build
"${compose[@]}" ps
echo '기동을 요청했어요. tools/smoke.sh "$API_BASE_URL"로 API 흐름을 확인해 주세요.'
