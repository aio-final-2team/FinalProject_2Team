# 유치온 배포 가이드

> 상태: 첫 배포 준비 (2026-11-20). 실제 서버 배포·HTTPS 연결은 배포 담당자가 진행해요.
> T30 첫 배포의 실행 절차예요. T63 최종 URL·T66 아키텍처는 뒤 작업에서 확정해요.

## 1. 결정과 구성

첫 배포 대상은 기존 결정대로 AWS EC2예요. 이 문서와 스크립트는 서버를 만들거나 접속하지 않아요.
모바일 배포 방향은 Android APK·iOS TestFlight이고 Compose와 별개예요.

```text
브라우저·앱 → 기존 HTTPS 앞단(80/443)
                 ├─ 화면 요청          → web (호스트 loopback → 컨테이너 80)
                 └─ /health·/api/v1/*  → api (호스트 loopback → 컨테이너 8000)
                                         └─ db (Compose 내부 5432)
```

서버에서는 루트 `compose.yaml`에 `infra/team-server/compose.server.yaml`을 겹쳐 써요.
api·web·db만 실행해요. API는 한 프로세스·한 컨테이너로 유지해요.
worker·Redis·Beat는 다음 워커 항목에서 붙여요.

서버 설정은 API·웹 포트 목록을 바꾸고 DB 호스트 포트를 제거해요.
API는 기본 `127.0.0.1:18000`, 웹은 `127.0.0.1:15173`에서만 받아요.
기존 앞단의 80/443·인증서·설정은 스크립트가 바꾸지 않아요.
호스트 앞단은 `/health`·`/api/v1/...` 경로를 그대로 API에 전달해요.
앞단이 컨테이너라면 그 컨테이너의 localhost가 호스트와 다르므로 연결 방식을 먼저 확인해요.

Docker와 **Compose 2.24.4 이상**, Git, Python 3.9 이상이 필요해요.
Python은 smoke에서 표준 라이브러리만 써요. 포트 병합 방식은
[Compose 공식 문서](https://docs.docker.com/reference/compose-file/merge/)의 `!override`·`!reset`을 따라요.

## 2. 환경 파일 준비

배포 담당자는 배포할 브랜치를 받고 upstream을 지정해요. 브랜치는 팀에서 확정해요.
저장소 루트에서 아래 명령을 실행해요.

```sh
cp infra/team-server/.env.server.example infra/team-server/.env.server
python3 -c 'import secrets; print(secrets.token_hex(32))'
# 서로 다른 임의 값을 만들어 POSTGRES_PASSWORD와 JWT_SECRET에 각각 넣어요.
```

환경 파일은 Git에서 제외돼요. 실제 비밀값·주소는 문서나 커밋에 적지 않아요.
서버 명령은 이 파일을 `--env-file`로 읽어요. 셸에 같은 이름이 있으면 셸 값이 우선해요.
`.env.server.example` 자체는 실행 가능한 운영 설정이 아니에요. 예시 JWT 키는 DB 기동 검사가 거부해요.

| 이름 | 설정 |
| --- | --- |
| `COMPOSE_PROJECT_NAME` | 서버에서 계속 같은 이름을 써요. 기본 예시는 `yuchion-server`예요. |
| `DATA_BACKEND` | 서버 기본은 `db`예요. 대역 시연만 할 때 `mock`으로 바꿔요. |
| `SERVER_API_PORT`·`SERVER_WEB_PORT` | 기존 앞단이 연결할 비어 있는 loopback 포트예요. |
| `POSTGRES_DB`·`POSTGRES_USER`·`POSTGRES_PASSWORD` | 전용 DB 이름·계정·별도 임의 비밀번호예요. |
| `DATABASE_URL` | API 컨테이너에서 쓰는 `db:5432` 주소예요. 예시는 위 DB 비밀번호를 참조해요. |
| `JWT_SECRET` | 예시·mock 기본값과 다른 32바이트 이상 임의 값이에요. |
| `VITE_API_BASE_URL` | 브라우저·앱이 접근할 외부 API 기준 주소예요. API 경로는 `/api/v1/...`예요. |
| `CORS_ORIGINS` | 외부 웹 origin이에요. 여러 개면 쉼표로 나눠요. |
| `DAILY_NOTE_WRITER` | 기본은 `app.modules.daily_notes.stub_writer:write`예요. |
| `DAILY_NOTE_WRITER_TIMEOUT` | 현재 기본 120초예요. |
| `OPENAI_API_KEY`·`LLM_MODEL_*` | `graph`를 선택할 때 설정해요. 기본 대역 시연은 모델을 호출하지 않아요. |
| `LANGSMITH_API_KEY` | 추적이 필요할 때만 넣어요. |

`VITE_API_BASE_URL`은 웹 빌드 값이에요. 바꾸면 웹 이미지를 다시 빌드해요.
현재 웹은 화면 골격이므로 API 연결·화면 검증은 프론트 작업에서 따로 해요.
DB 볼륨이 생긴 뒤 `POSTGRES_*`만 바꿔도 기존 DB 계정·비밀번호가 바뀌지 않아요.

## 3. 배포 실행

기존 앞단 연결과 환경 파일을 준비한 뒤 **배포 담당자가 서버에서** 실행해요.
코드 작업 폴더에 변경·미추적 파일이 있으면 중단해요. 무시된 환경 파일은 그대로 둬요.

```sh
infra/team-server/deploy.sh
# 다른 환경 파일을 쓰면 절대경로로 넘겨요.
infra/team-server/deploy.sh "$SERVER_ENV_FILE"
```

스크립트는 현재 브랜치에서 `git pull --ff-only` → Compose 설정 검사 → 아래 기동 명령 → 상태 조회
순서로 실행해요. pull·검사가 실패하면 기동하지 않아요. 브랜치 전환·강제 덮어쓰기는 하지 않아요.
기존 `.github/workflows/cd.yml`은 아직 루트 Compose와 8000 health만 써요.
이 서버 설정은 위 스크립트로 적용하고, 수동 배포 워크플로 연결은 별도 확인이 필요해요.

```sh
docker compose --env-file infra/team-server/.env.server \
  -f compose.yaml -f infra/team-server/compose.server.yaml up -d --build
```

DB 모드는 기존 엔트리포인트가 설정 검사 → `alembic upgrade head` → 데모 시드 → API 순서로 시작해요.
시드는 기존 행을 덮어쓰지 않아요. mock은 DB 초기화를 하지 않고 메모리 데이터를 써요.
DB 컨테이너는 두 모드에서 함께 떠요. API health가 통과하면 웹이 시작해요.
`up -d` 종료만으로 기능 검증이 끝난 것은 아니므로 아래 smoke를 실행해요.

## 4. 배포 확인

API 기준 주소를 변수로 정하고 저장소 루트에서 실행해요.
URL은 `/health`와 `/api/v1/...` 앞의 기준 주소예요. 경로 접두사가 있다면 앞단도 똑같이 연결해요.

```sh
tools/smoke.sh "$API_BASE_URL"
```

smoke는 health 준비 → 담임 로그인 → 반 아이 목록 → 초안 만들기 → succeeded 상태 →
아이별 알림장 목록을 확인해요. 날짜 조회 쿼리는 `date`, 생성 본문은 `note_date`예요.
실패하면 0이 아닌 종료 코드를 돌려줘요. 모든 출력에 `[TEST]`가 붙고 토큰·비밀번호는 출력하지 않아요.
기본 `teacher01`·`demo1234`, 한국 날짜 오늘을 써요. 필요하면 아래 값만 바꿔요.

```sh
SMOKE_LOGIN_ID=teacher01 SMOKE_PASSWORD=demo1234 \
  SMOKE_NOTE_DATE=2026-11-20 SMOKE_TIMEOUT=180 tools/smoke.sh "$API_BASE_URL"
```

**이 검사는 초안을 만들어요.** 가상 데이터가 있는 데모 환경에서 실행해요.
같은 반·날짜 입력이 있으면 기존 입력을 조회하므로 새 내용 생성까지 보려면 빈 날짜를 골라요.
확인·보내기는 실행하지 않아요. mock과 DB 모두 같은 스크립트를 써요.
DB 모드에서 미구현인 문의·카드·상담·알림 API는 아직 501일 수 있어요.

웹은 `$WEB_BASE_URL`로 접속해 첫 화면을 따로 확인해요. 이 smoke는 웹·TLS·모바일을 검증하지 않아요.

## 5. 백업·롤백

배포 전에 기존 DB를 백업해요. 아래 명령은 서버 환경 파일과 같은 DB를 사용해요.

```sh
docker compose --env-file infra/team-server/.env.server \
  -f compose.yaml -f infra/team-server/compose.server.yaml \
  exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' > "$BACKUP_FILE"
```

DB 데이터는 프로젝트의 `postgres_data` 볼륨에 남아요. 운영에서 `down --volumes`를 쓰지 않아요.
복구와 코드 롤백은 배포 담당자가 백업·마이그레이션 호환성을 확인한 뒤 진행해요.
이미 스키마가 바뀌었다면 코드만 되돌려서 복구된다고 가정하지 않아요.

## 6. 남은 작업과 문제 확인

| 증상 | 확인 |
| --- | --- |
| 설정 검사가 실패해요 | Compose 버전·환경 파일·필수 변수 값을 확인해요. |
| API가 다시 시작돼요 | 같은 Compose 옵션으로 `logs api`를 보고 JWT·DB 접속·마이그레이션을 확인해요. |
| 외부 접속만 실패해요 | 기존 앞단의 loopback 포트·경로·HTTPS·CORS 연결을 확인해요. |
| smoke 초안이 failed예요 | API 로그와 writer 설정을 확인해요. stub으로 먼저 흐름을 확인해요. |
| 웹은 뜨는데 API를 못 불러요 | 빌드 시 API 주소와 실제 프론트 연결 상태를 확인해요. |

실제 서버 주소·리소스 측정·HTTPS 확인·최종 운영 브랜치는 배포 담당자가 확정해요.
모바일은 Capacitor 구성과 Android 서명·TestFlight 계정 준비가 남아 있어요.
APK·IPA는 Compose가 만들지 않아요. 앱에도 외부 HTTPS API 주소를 빌드 때 넣어요.

## 변경 이력

| 날짜 | 내용 |
| --- | --- |
| 2026-11-17 | EC2 첫 배포·모바일 배포 방향 초안이에요. |
| 2026-11-20 | 서버 Compose·환경 파일·배포 스크립트·알림장 smoke 절차를 현재 코드에 맞췄어요. |
