# infra/backup

팀 서버의 DB와 사진 파일을 폴더 하나에 백업하고, 그 폴더로 다시 복원하는 스크립트가 들어 있어요.
두 스크립트는 저장소 루트로 옮겨 가서 실행되고, 환경 파일과 Compose 파일은 배포 스크립트(`infra/team-server/deploy.sh`)와 같은 것을 기본값으로 써요.
정기 실행은 아직 예약해 두지 않았어요. 주기와 보관 개수가 정해지면 여기에 적을게요.

아래 예시의 `compose`는 `docker compose --env-file infra/team-server/.env.server -f compose.yaml -f infra/team-server/compose.server.yaml`을 줄여 쓴 거예요.

## 백업

```sh
infra/backup/backup.sh                        # 환경 파일 기본값: infra/team-server/.env.server
BACKUP_KEEP=14 infra/backup/backup.sh "$SERVER_ENV_FILE"
```

실행하면 `backups/<UTC 시각>/` 폴더가 하나 생겨요.

| 파일 | 내용 |
| --- | --- |
| `db.sql.gz` | `db` 컨테이너에서 받은 `pg_dump` |
| `media.tar.gz` | 사진 볼륨(`media_data`)을 읽기 전용으로 붙인 임시 컨테이너에서 묶은 파일 |
| `meta.json` | 덤프를 시작하기 직전 시각(`created_at`), git 커밋, alembic 판, Compose 프로젝트 이름, 두 파일의 sha256 |

- 백업을 받는 동안에는 `<시각>.partial` 폴더에 쓰다가, 다 받으면 이름을 바꿔요. 중간에 실패하면 그 폴더는 지워요.
- 다 받은 폴더가 `BACKUP_KEEP`(기본 7)개를 넘으면 오래된 것부터 지워요.
- 백업을 다른 곳에 두고 싶으면 `BACKUP_DIR`을 지정해요. `backups/`는 Git에서 제외돼 있어서 배포 스크립트의 변경 검사에 걸리지 않아요.
- Compose 프로젝트 이름은 환경 파일의 `COMPOSE_PROJECT_NAME`을 따라요. 셸에서 같은 변수를 지정하면 그 값이 우선해요. Compose 파일을 바꾸려면 `COMPOSE_FILE`을 지정하면 돼요.
- 백업 폴더에는 아이 사진과 DB 전체가 들어 있어서 소유자만 읽을 수 있게 만들어요. 서버 밖으로 옮길 때도 같은 수준으로 다뤄 주세요.

## 복원

```sh
infra/backup/restore.sh backups/<시각>               # 할 일만 보여 줘요
infra/backup/restore.sh backups/<시각> --yes         # 실제로 복원해요
infra/backup/restore.sh backups/<시각> "$SERVER_ENV_FILE" --yes
```

복원을 시작하기 전에 두 파일의 sha256을 `meta.json`에 적힌 값과 맞춰 봐요. 그다음 아래 순서대로 진행하는데, 어느 단계에서든 실패하면 그 자리에서 멈춰요.

1. 지금 DB를 읽을 수 있으면 백업 시각 이후의 변경을 뽑아서 `backups/<시각>/reapply-<지금 시각>.json`에 저장해요. 읽을 수 없으면 경고만 남기고 이 단계를 건너뛰어요.
2. 실행 중인 api, worker, beat를 멈춰요. 웹과 DB는 그대로 둬요.
3. DB를 지우고 덤프로 다시 만들어요. 사진 볼륨도 비운 뒤 백업 파일로 채워요.
4. 마이그레이션을 올린 다음, 1단계에서 뽑아 둔 변경을 복원한 DB에 다시 적용해요.
5. 고아 사진 파일을 지워요.
6. 2단계에서 멈춘 서비스를 다시 켜요.

1단계를 마친 뒤에 실패했다면 다시 실행할 때 `REAPPLY_FILE=<1에서 만든 파일>`을 지정해 주세요. 그래야 복원하다 만 DB에서 변경을 다시 뽑지 않아요.

## 복원 뒤 다시 적용

덤프에는 백업 시각까지의 상태만 담겨요. 그래서 백업 뒤에 글을 지우거나 숨기고, 공개 범위를 좁히고, 기억을 지우고, 퇴소 처리를 했더라도 복원하면 그 변경이 모두 사라져요. 이렇게 다시 열린 것들을 `after_restore`가 도로 닫아요. 보통은 `restore.sh`가 4단계에서 부르지만 따로 실행해도 돼요.

```sh
# 복원하기 전, 지금 DB에서
compose exec -T api python -m app.maintenance.after_restore export --since <meta.json의 created_at> > reapply.json
# 복원한 DB에서
compose exec -T api python -m app.maintenance.after_restore apply - < reapply.json
```

| 되살아나는 것 | export가 찾는 곳 |
| --- | --- |
| 지운 글 | `feed_posts.deleted_at` |
| 숨긴 글 | `feed_post_hidden` 이력 |
| 공개 범위 | 아이마다 마지막 `photo_scope_changed` 이력의 `after` |
| 지운 기억 | `memories.deleted_at` |
| 퇴소 | `detail.withdrawn`이 있는 `photo_scope_changed` 이력 |
| 피드 이력 행 | 위 세 종류의 이력 행 그대로 |

이력에 찍히는 시각은 트랜잭션이 시작된 시각이에요. 백업 직전에 시작해서 덤프 뒤에 커밋된 변경까지 잡아야 하니까, 백업 시각보다 10분 앞부터 살펴봐요.
`apply`는 이미 닫힌 행을 건너뛰고, 시각과 내용이 같은 이력도 다시 넣지 않아요. 두 번 실행해도 결과가 같은 건 그래서예요.
복원한 DB에 없는 글, 아이, 기억은 건너뛰어요. 퇴소는 이력을 남기지 않고 같은 작업을 다시 돌린 뒤, 이력에는 원래 행을 그대로 넣어요.
이 단계에서는 파일을 지우지 않으니, 이어서 사진 정리를 돌려 주세요.

## 사진 정리 (고아 파일)

```sh
compose exec -T api python -m app.maintenance.media_sweep            # 목록만 보여 줘요
compose exec -T api python -m app.maintenance.media_sweep --apply    # 지워요
```

`MEDIA_DIR`에 있는 파일 가운데, 지우지 않은 글의 `feed_photos.storage_path` 어디에도 없는 파일을 고아로 봐요.
모의 모드에서 쓰는 `mock/` 폴더와 링크는 건너뛰어요. 생긴 지 10분이 안 된 파일도 건너뛰는데, 올리는 중인 사진을 지우지 않으려고 그래요. 이 기준은 `--min-age`로 정하고 단위는 초예요.
지울 경로가 `MEDIA_DIR` 밖을 가리키면 지우지 않고 거부해요.

## 퇴소 관리 작업

```sh
compose exec -T api python -m app.maintenance.withdraw_child <child_id>            # 할 일만 보여 줘요
compose exec -T api python -m app.maintenance.withdraw_child <child_id> --apply    # 실행해요
```

DB 설계서의 '아이가 퇴소할 때'에 나오는 네 단계를 한 트랜잭션에서 처리해요. 보호자 연결을 끝내고, 공개 범위를 family로 되돌리고, 그 아이만 찍힌 사진을 지우고, 기억을 비워요.
사진 파일은 커밋한 뒤에 지워요. 다른 아이와 함께 찍힌 사진은 지우지 않고 태그를 남겨서 계속 가려 둬요. 보호자 계정을 끄는 일(`users.is_active = false`)은 이 작업에서 하지 않아요.
처리 기록은 `photo_scope_changed` 이력 한 줄로 남고, `detail`에 `withdrawn: true`와 지운 사진 ID가 들어가요. 이미 퇴소 처리가 끝난 아이에게 다시 돌려도 아무것도 바뀌지 않아요.

데모 시드 아이는 퇴소 처리를 해도 되돌아올 수 있어요. `SEED_DEMO`가 켜진 API가 다시 뜨면 시드가 보호자 연결과 사진을 다시 넣기 때문이에요. 실제 아이는 시드에 없으니 상관없어요.
