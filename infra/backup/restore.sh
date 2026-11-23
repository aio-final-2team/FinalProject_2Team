#!/usr/bin/env bash
# 백업 폴더 하나로 DB와 사진을 되돌리고, 백업 뒤에 지우거나 좁힌 것을 다시 적용한다.
# 기본은 할 일만 출력한다. --yes를 붙여야 실행한다. 각 단계는 실패하면 거기서 멈춘다.
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
source infra/backup/common.sh

yes=0
args=()
for arg in "$@"; do
    if [[ "$arg" == --yes ]]; then yes=1; else args+=("$arg"); fi
done
if (( ${#args[@]} < 1 || ${#args[@]} > 2 )); then
    echo "사용법: $0 <백업 폴더> [환경 파일] [--yes]  (REAPPLY_FILE로 이미 뽑은 JSON을 쓰고, SKIP_EXPORT=1로 1단계를 건너뛰어요)" >&2
    exit 2
fi
backup=${args[0]%/}
compose_setup "${args[1]:-infra/team-server/.env.server}"
(cd "$backup" && python3 -c '
import json; print("\n".join(f"{d}  {n}" for n, d in json.load(open("meta.json"))["sha256"].items()))' \
    | sha256sum --check --quiet) || { echo "백업 폴더의 파일이 meta.json과 달라요: $backup" >&2; exit 1; }
since=$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["created_at"])' "$backup/meta.json")
reapply=${REAPPLY_FILE:-$backup/reapply-$(date -u +%Y%m%dT%H%M%SZ).json}
running=()
maint=("${compose[@]}" run --rm --no-deps -T --entrypoint python api -m)

step() {
    echo "== $1"
    if (( yes )); then "${@:2}"; fi
}

export_changes() {
    if [[ -n "${REAPPLY_FILE:-}" ]]; then
        echo "이미 뽑아 둔 파일을 써요: $reapply"
    elif [[ "${SKIP_EXPORT:-}" == 1 ]]; then
        reapply=
        echo "SKIP_EXPORT=1이라 건너뛰어요. 백업 뒤에 지운 글·기억은 다시 닫히지 않아요." >&2
    elif db_sh 'psql -At -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 1 FROM alembic_version"' >/dev/null 2>&1; then
        "${maint[@]}" app.maintenance.after_restore export --since "$since" > "$reapply"
        echo "뽑았어요: $reapply"
    else
        echo "지금 DB를 읽을 수 없어 멈춰요. 이대로 복원하면 백업 뒤에 지운 글·기억이 다시 열려요." >&2
        echo "DB가 잠깐 안 뜬 거면 db를 살린 뒤 다시 돌려요. DB를 통째로 잃었으면 SKIP_EXPORT=1을 붙여요." >&2
        exit 1
    fi
}

stop_services() {
    mapfile -t running < <("${compose[@]}" ps --services --status running | grep -xE 'api|worker|beat' || true)
    if (( ${#running[@]} )); then "${compose[@]}" stop "${running[@]}"; fi
}

restore_data() {
    db_sh 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d postgres -c "DROP DATABASE IF EXISTS \"$POSTGRES_DB\" WITH (FORCE)" \
        -c "CREATE DATABASE \"$POSTGRES_DB\" OWNER \"$POSTGRES_USER\""'
    gunzip -c "$backup/db.sql.gz" | db_sh 'psql -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null
    docker run --rm -i -v "$media_volume:/media" --entrypoint sh "$tool_image" \
        -c 'find /media -mindepth 1 -delete && tar -C /media -xzf -' < "$backup/media.tar.gz"
}

start_services() {
    if (( ${#running[@]} )); then "${compose[@]}" start "${running[@]}"; else echo "멈춘 서비스가 없어 켤 것도 없어요."; fi
}

reapply_changes() {
    # 복원한 덤프가 옛 판이어도 지금 코드의 표에 적용하도록 마이그레이션을 먼저 올린다.
    "${compose[@]}" run --rm --no-deps -T --entrypoint python api -m alembic -c apps/api/alembic.ini upgrade head
    if [[ -n "$reapply" ]]; then "${maint[@]}" app.maintenance.after_restore apply - < "$reapply"; fi
}

echo "백업 $backup (시각 $since) → 프로젝트 $project"
if [[ "${SKIP_EXPORT:-}" == 1 ]]; then export_note="SKIP_EXPORT=1이라 건너뜀"; else export_note="못 읽으면 멈춤, SKIP_EXPORT=1이면 건너뜀"; fi
step "1. 지금 DB에서 백업 뒤 변경 뽑기 ($export_note)" export_changes
step "2. api·worker·beat 멈춤" stop_services
step "3. DB와 사진 볼륨 복원" restore_data
step "4. 마이그레이션과 복원 뒤 다시 적용" reapply_changes
step "5. 고아 사진 파일 정리" "${maint[@]}" app.maintenance.media_sweep --apply --min-age 0
step "6. 2단계에서 멈춘 서비스 다시 켬" start_services
if (( ! yes )); then echo "할 일만 보였어요. 실행하려면 --yes를 붙여요."; fi
