# shellcheck shell=bash
# backup.sh·restore.sh가 같이 쓰는 Compose 설정이다. 기본값은 deploy.sh와 같다.
# COMPOSE_FILE을 주면 -f 대신 그 파일들을 쓰고, COMPOSE_PROJECT_NAME을 주면 환경 파일 값보다 앞선다.

compose_setup() {
    local env_file=$1 info
    if [[ ! -f "$env_file" ]]; then
        echo "환경 파일이 없어요: $env_file" >&2
        exit 1
    fi
    compose=(docker compose --env-file "$env_file")
    [[ -n "${COMPOSE_FILE:-}" ]] || compose+=(-f compose.yaml -f infra/team-server/compose.server.yaml)
    "${compose[@]}" config --quiet
    # 설정 JSON에는 비밀값이 들어 있어 화면에 내지 않고 이름만 꺼낸다.
    info=$("${compose[@]}" config --format json | python3 -c '
import json, sys
c = json.load(sys.stdin)
print(c["name"], c["volumes"]["media_data"]["name"], c["services"]["db"]["image"])')
    # shellcheck disable=SC2034  # 불러 쓰는 스크립트가 쓴다.
    read -r project media_volume tool_image <<< "$info"
}

db_sh() {
    "${compose[@]}" exec -T db sh -c "$1"
}
