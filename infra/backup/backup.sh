#!/usr/bin/env bash
# DB 덤프·사진 볼륨·메타를 backups/<UTC 시각>/ 한 폴더로 받고, 보관 개수를 넘는 옛 폴더를 지운다.
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
source infra/backup/common.sh

if (( $# > 1 )); then
    echo "사용법: $0 [환경 파일]  (BACKUP_DIR 기본 backups, BACKUP_KEEP 기본 7)" >&2
    exit 2
fi
compose_setup "${1:-infra/team-server/.env.server}"
root=${BACKUP_DIR:-backups}
keep=${BACKUP_KEEP:-7}
[[ "$keep" =~ ^[1-9][0-9]*$ ]] || { echo "BACKUP_KEEP은 1 이상의 정수예요." >&2; exit 2; }
docker volume inspect "$media_volume" >/dev/null 2>&1 || { echo "사진 볼륨이 없어요: $media_volume" >&2; exit 1; }

umask 077
# 덤프를 시작하기 전 시각을 적는다. 복원 뒤 다시 적용은 이 시각 뒤의 변경을 찾는다.
created_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
stamp=$(date -u -d "$created_at" +%Y%m%dT%H%M%SZ)
work="$root/$stamp.partial"
mkdir -p "$work"
trap 'rm -rf "$work"' ERR

db_sh 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB"' | gzip > "$work/db.sql.gz"
alembic=$(db_sh 'psql -At -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT version_num FROM alembic_version"')
docker run --rm -v "$media_volume:/media:ro" --entrypoint tar "$tool_image" -C /media -czf - . > "$work/media.tar.gz"
sums=$(cd "$work" && sha256sum db.sql.gz media.tar.gz)
python3 - "$work/meta.json" "$created_at" "$(git rev-parse HEAD)" "$alembic" "$project" "$sums" <<'PY'
import json, sys
path, created_at, commit, alembic, project, sums = sys.argv[1:]
meta = {"created_at": created_at, "git_commit": commit, "alembic_version": alembic, "compose_project": project,
        "sha256": {name: digest for digest, name in (line.split() for line in sums.splitlines())}}
open(path, "w").write(json.dumps(meta, indent=2) + "\n")
PY
mv "$work" "$root/$stamp"
echo "백업했어요: $root/$stamp ($(du -sh "$root/$stamp" | cut -f1), 판 $alembic)"

# 끝까지 받은 폴더만 센다. 이름이 시각 모양이고 meta.json이 있는 폴더다.
mapfile -t done_dirs < <(find "$root" -mindepth 1 -maxdepth 1 -type d -regextype posix-extended \
    -regex '.*/[0-9]{8}T[0-9]{6}Z' -exec test -f '{}/meta.json' ';' -print | sort)
extra=$(( ${#done_dirs[@]} - keep ))
for old in "${done_dirs[@]:0:extra>0?extra:0}"; do
    rm -rf "$old"
    echo "보관 개수($keep)를 넘어 지웠어요: $old"
done
