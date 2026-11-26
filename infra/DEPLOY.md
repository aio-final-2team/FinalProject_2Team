# 유치온 배포 가이드

> 상태: **초안** (2026-11-17) · `TODO`는 확정되면 채웁니다.
> 이 문서는 T30(첫 배포), T63(최종 배포 URL), T66(배포 아키텍처 설계도)의 기준 문서입니다.

## 0. 결정 사항

| 날짜 | 결정 | 영향 |
|---|---|---|
| 2026-11-17 | 첫 배포부터 **AWS EC2**로 진행 (강사님 팀 VM 사용 안 함) | WBS T30·T73 일정 조정 필요, `infra/team-server/` 정리 대상 |
| 2026-11-17 | 모바일은 **Android APK + iOS TestFlight** | iOS 작업 WBS 추가 필요, Mac·Apple Developer 계정 필요 |

## 1. 전체 구성

```
[브라우저] ──https──┐
                    ├─▶ [EC2 (ap-northeast-2)]
[폰 앱 APK/IPA] ────┘      ├─ web        React + nginx      (컨테이너 :80)
                           ├─ api        FastAPI            (컨테이너 :8000)
                           └─ db         PostgreSQL+pgvector (컨테이너 :5432, 외부 비공개)
```

- 서버에서는 루트의 `compose.yaml`로 `web`, `api`, `db` 세 서비스를 띄웁니다. 원장 현황은 같은 React 앱의 역할별 화면에서 제공합니다.
- 폰 앱은 `apps/web` 코드를 Capacitor로 포장한 것이며 **compose로 배포하지 않습니다** (8장).
- 외부 연동: OpenAI, LangSmith, (예정) AWS Rekognition

| 항목 | 값 |
|---|---|
| 리전 | ap-northeast-2 (서울) |
| EC2 사양 | t3.large (vCPU 2개·메모리 7.6GiB). 11/26 실측은 6장 '리소스 실측' |
| 도메인 | `https://3-34-13-40.sslip.io` (EC2 공인 IP로 만든 주소라 IP가 바뀌면 같이 바뀌어요) |
| 팀 서버 브랜치 | `develop` (머지되면 자동 반영, 5-2) |
| 배포 담당 / AWS 계정 관리자 | `TODO` |

## 2. 환경

| 환경 | 위치 | 주소 | 용도 |
|---|---|---|---|
| 로컬 | 각자 PC | http://localhost:5173 (web), :8000 (api) | 개발 |
| 운영 | AWS EC2 | `TODO` https://도메인 | 시연·제출·앱 테스트 |

## 3. 사전 준비 (최초 1회)

### 3-1. AWS 계정
- [ ] 계정 수령 및 접근 확인 (`TODO` 수령일)
- [ ] **AWS Budgets 알림 설정** (예: 월 `TODO` 달러 초과 시 팀 메일 알림) — AWS는 자동으로 과금을 멈추지 않음
- [ ] IAM 사용자 분리 (루트 계정 사용 금지)

### 3-2. EC2
- [ ] 인스턴스 생성 (Ubuntu, 리전 ap-northeast-2)
- [ ] 키페어 생성 → `.pem`은 **레포에 올리지 않음**, 보관 위치 `TODO`
- [ ] 탄력적 IP(Elastic IP) 연결 — 재시작해도 주소가 바뀌지 않도록
- [ ] Docker, Docker Compose 플러그인 설치

### 3-3. 보안그룹 (인바운드)

| 포트 | 허용 대상 | 용도 |
|---|---|---|
| 22 | 전체(키 로그인만, 비밀번호 로그인 꺼짐) | SSH·수동 CD |
| 80 | 0.0.0.0/0 | HTTP (HTTPS 리다이렉트용) |
| 443 | 0.0.0.0/0 | HTTPS |
| 8000 | `TODO` | 리버스 프록시 적용 전 임시 개방 여부 결정 |
| **5432** | **열지 않음** | DB는 외부 노출 금지 |

### 3-4. 도메인 · HTTPS (`TODO`)
- iOS 앱은 `http://` 접속을 기본으로 막으므로 **HTTPS가 필수**입니다.
- 방식 후보: 리버스 프록시(nginx 또는 Caddy) + Let's Encrypt 인증서
- 라우팅 후보: `/` → web, `/api` → api

## 4. 환경변수

`infra/team-server/.env.server.example`을 복사해 서버의 `infra/team-server/.env.server`를 만들어요. **실제 값은 문서·레포에 적지 않습니다.**
배포 명령은 이 파일을 `--env-file`로 읽어요. 셸에 같은 이름의 변수가 있으면 셸 값이 우선해요.

| 이름 | 설명 | 운영 값 기준 | 보관 위치 |
|---|---|---|---|
| `COMPOSE_PROJECT_NAME` | Compose 프로젝트 이름 | 배포마다 같은 이름 사용 | 서버 `.env.server` |
| `DATA_BACKEND` | 데이터 저장 방식 | 서버 기본 `db`, 대역 시연은 `mock` | 서버 `.env.server` |
| `SERVER_API_PORT`·`SERVER_WEB_PORT` | 기존 앞단이 연결할 포트 | 비어 있는 loopback 포트 | 서버 `.env.server` |
| `POSTGRES_DB` | DB 이름 | yuchion | 서버 `.env.server` |
| `POSTGRES_USER` | DB 사용자 | yuchion | 서버 `.env.server` |
| `POSTGRES_PASSWORD` | DB 비밀번호 | **로컬 기본값 사용 금지**, 새로 생성 | 서버 `.env.server` |
| `DATABASE_URL` | API → DB 접속 주소 | 컨테이너 내부 `db:5432`, 위 비밀번호 반영 | 서버 `.env.server` |
| `VITE_API_BASE_URL` | 프론트가 호출할 API 주소 | 외부 API 기준 주소, `/api/v1/...` 앞까지 | 서버 `.env.server`, 앱 빌드 시 |
| `CORS_ORIGINS` | 웹 origin | 외부 웹 origin, 여러 개면 쉼표로 구분 | 서버 `.env.server` |
| `JWT_SECRET` | 로그인 토큰 서명 키 | 예시·mock 기본값과 다른 32바이트 이상 임의 값 | 서버 `.env.server` |
| `DAILY_NOTE_WRITER` | 알림장 초안 함수 | 기본 `app.modules.daily_notes.stub_writer:write`, 그래프는 `graph` | 서버 `.env.server` |
| `DAILY_NOTE_WRITER_TIMEOUT` | 초안 함수 대기 제한 | 기본 300초 | 서버 `.env.server` |
| `NOTE_DRAFT_CONCURRENCY` | 아이별 초안 동시 실행 수 | 기본 5, 지원하는 그래프에서 사용 | 서버 `.env.server` |
| `ANSWER_WRITER` | 문의 답변 초안(요청 처리 AI) | 기본 `stub`(대역 문장), 모델을 쓰면 `graph`. 켜고 끄는 법은 5-4 | 서버 `.env.server` |
| `OPENAI_API_KEY` | OpenAI 호출 | `graph`를 선택할 때 팀 키 | 서버 `.env.server` |
| `LLM_MODEL_DEFAULT`·`LLM_MODEL_*` | 그래프 모델 선택 | 팀에서 정한 모델, 역할별 값은 예시 파일 참고 | 서버 `.env.server` |
| `REQUEST_AGENT` | 요청 처리 입구 | 기본은 대역(`agent_stub`). 그래프·체크포인트·승인 대기는 `app.modules.requests.graph_agent:run_request`. 5-5 | 서버 `.env.server` |
| `REQUEST_COLLAB_GRAPH` | 협업 그래프 | `1`이면 `REQUEST_AGENT`가 그래프일 때 협업 그래프를 써요. 5-5 | 서버 `.env.server` |
| `LLM_MODEL_SUPERVISOR` | 감독 AI 모델 | **비우면 감독 모델을 부르지 않고 낱말 규칙만 봐요.** 켜려면 모델 이름을 적어요. 5-5 | 서버 `.env.server` |
| `EMBEDDING_MODEL`·`INSTALL_EMBEDDING` | 자료 검색 임베딩 | `BAAI/bge-m3`와 빌드 인자 `INSTALL_EMBEDDING=1`. 5-5 | 서버 `.env.server` |
| `LAW_GO_KR_OC` | 법령 조문 조회 | 법제처 OPEN API 신청 ID. 비우면 법령 근거를 붙이지 않아요 | 서버 `.env.server` |
| `LANGSMITH_API_KEY`·`LANGSMITH_TRACING` | LangSmith 추적 | 키와 `true`를 둘 다 넣으면 그래프 단계와 모델 호출(보낸 글·받은 답·토큰 수)이 LangSmith에 남아요. 5-5 | 서버 `.env.server` |

> ⚠️ `VITE_API_BASE_URL`은 **빌드할 때 결과물에 박힙니다.** 값을 바꾸면 컨테이너 재시작이 아니라 `web` 이미지를 다시 빌드해야 하고, 앱(APK/IPA)도 다시 빌드해야 합니다. 기본값 `http://localhost:8000`으로 빌드하면 브라우저·폰에서 API 호출이 실패합니다.

예시 JWT 값으로는 DB 모드가 시작되지 않아요. 기본 대역 writer는 모델을 호출하지 않아요.
DB 볼륨이 생긴 뒤 `POSTGRES_*`만 바꿔도 기존 DB 계정·비밀번호가 바뀌지 않아요.

## 5. 서버 배포 절차

PR의 CI는 API·웹 이미지 빌드를 확인합니다(WBS T74).
GitHub Actions의 **Manual Deploy (Docker Compose)**도 아래 서버 배포 스크립트를 실행해요.
상태 검사는 `.env.server`의 `SERVER_API_PORT`(기본 18000)를 서버 Compose 설정에서 읽어 사용해요.
11/22 `aws-ec2` Environment에 CD 비밀값을 넣었고, 워크플로 실제 실행(develop)도 통과했어요.

### 5-1. 최초 배포

Docker, Docker Compose **2.24.4 이상**, Git, Python 3.9 이상을 준비해요.
운영 브랜치와 upstream은 배포 담당자가 정해요. 접속 대상·저장소·작업 폴더는 아래 변수로 지정해요.

```bash
# EC2 접속
ssh "$DEPLOY_TARGET"

# 코드 받기: 접속한 서버에서 REPO_URL·DEPLOY_BRANCH·CHECKOUT_DIR을 정해요.
git clone --branch "$DEPLOY_BRANCH" "$REPO_URL" "$CHECKOUT_DIR"
cd "$CHECKOUT_DIR"

# 환경변수
cp infra/team-server/.env.server.example infra/team-server/.env.server
python3 -c 'import secrets; print(secrets.token_hex(32))'
# 서로 다른 임의 값을 만들어 POSTGRES_PASSWORD와 JWT_SECRET에 각각 넣어요.
nano infra/team-server/.env.server  # 4장 기준으로 운영 값 입력

# 실행
infra/team-server/deploy.sh
```

스크립트는 환경 파일·작업 폴더 확인 → 현재 브랜치의 `git pull --ff-only` → Compose 설정 검사 →
기동 → 상태 조회 순서로 실행해요. 변경·미추적 파일이 있거나 pull·검사가 실패하면 기동하지 않아요.
무시된 환경 파일은 그대로 두고 브랜치 전환·강제 덮어쓰기는 하지 않아요.

### 5-2. 업데이트 배포

```bash
cd "$CHECKOUT_DIR"
infra/team-server/deploy.sh
# 다른 환경 파일을 쓰면 절대경로로 넘겨요.
# infra/team-server/deploy.sh "$SERVER_ENV_FILE"
```

기동·상태 조회에 사용하는 Compose 옵션은 아래와 같아요. 이후 확인·백업·롤백에도 같은 옵션을 써요.

```bash
docker compose --env-file infra/team-server/.env.server \
  -f compose.yaml -f infra/team-server/compose.server.yaml up -d --build
docker compose --env-file infra/team-server/.env.server \
  -f compose.yaml -f infra/team-server/compose.server.yaml ps
```

**팀 서버 자동 반영.** `develop`에 PR이 머지되면 자동 배포가 그 커밋을 팀 서버에 `deploy.sh`로 올리고 디스코드 #일반에 결과를 알려요.
- CI가 실패한 커밋이나 서버 작업 폴더에 손댄 변경이 있으면 올리지 않고 알리기만 해요.
- 올린 뒤 `/health`·웹 첫 화면·로그인·컨테이너 6개 상태를 3분 안에 확인하고, 실패하면 직전 이미지로 되돌린 뒤 PR 작성자를 불러요.
- 문서(`Docs/`·`.md`)만 바뀐 머지는 올리되 알림을 남기지 않아요.
- 이건 개발·시연용 팀 서버 이야기예요. 기획서 NFR-13의 '자동 운영 배포는 하지 않는다'는 그대로이고, 운영 배포는 `cd.yml` 수동 실행이에요.

DB 모드는 설정 검사 → `alembic upgrade head` → 데모 시드 → API 순서로 시작해요.
시드는 기존 행을 덮어쓰지 않아요. `mock`은 DB 초기화를 건너뛰고 메모리 데이터를 써요.
두 모드 모두 DB 컨테이너가 함께 뜨고, API가 healthy이면 웹이 시작해요.

### 5-3. 주의
- 루트 `compose.yaml`에 `infra/team-server/compose.server.yaml`을 겹쳐 api·web·db를 실행해요. 서버 설정은 API·웹을 loopback 포트에서만 받고 DB 호스트 포트를 없애요.
- 기존 80/443 앞단·인증서는 스크립트가 바꾸지 않아요. 앞단이 `/health`·`/api/v1/...`를 그대로 API에 전달하도록 연결해요. 앞단이 별도 컨테이너라면 그 컨테이너의 localhost와 호스트가 다르므로 연결 방식을 먼저 확인해요.
- API는 한 프로세스·한 컨테이너로 유지해요. 팀 서버는 `COMPOSE_PROFILES=worker`로 worker·redis·beat를 함께 띄우고, `RUN_IN=worker`로 요청 처리와 알림장 초안 작업을 worker에 넘겨요.
- `db` 데이터는 `postgres_data` 볼륨에 저장됩니다. `docker compose down -v`는 **DB 데이터를 삭제**하므로 운영에서 사용 금지.

### 5-4. 요청 처리 AI 켜기·끄기

학부모 문의에 답변 초안을 쓰는 자료 AI·검사 AI는 `ANSWER_WRITER=graph`일 때만 모델을 불러요(`apps/api/app/modules/documents/answer.py`의 `graph_enabled`). 값이 없거나 `stub`이면 모델 없이 대역 문장으로 카드를 만들어요. 알림장 초안(`DAILY_NOTE_WRITER`)은 이 값과 따로 켜고 꺼요. `REQUEST_AGENT`는 기본값(`agent_stub`)을 그대로 둬요. 아래 시험을 이 기본값으로 돌렸기 때문이에요. `graph_agent`는 그래프가 도는 동안 체크포인트용 DB 연결을 하나씩 잡고 있어서, 아래 시험으로는 안전하다고 보장할 수 없어요.

**켜기 전에 확인할 것**

| 확인 | 방법 | 통과 기준 |
|---|---|---|
| 모델 호출을 잠금 밖에서 하고 3분에 끊는지 | `tools/test_db.sh`(`tests/integration/db/test_request_lock_timeout.py` 포함) | 모두 통과 |
| 모델을 기다리는 동안 다른 교사가 조회할 수 있는지 | 같은 파일의 `test_teacher_can_read_while_model_waits` | 카드 상세·목록 200, 요청 행이 잠겨 있지 않음 |
| 마감 뒤 교사가 손댄 카드를 늦은 결과가 덮지 않는지 | 같은 파일의 `test_late_draft_keeps_teacher_decision`(수정 승인·거절) | 카드·상태·근거·이력·알림 그대로 |
| 모델 키와 모델 이름 | `.env.server`의 `OPENAI_API_KEY`, `LLM_MODEL_DEFAULT`. 역할별 `LLM_MODEL_DOCUMENT`·`LLM_MODEL_CHECKER`는 비워 두면 기본값을 써요. 키가 컨테이너에 들어갔는지는 `exec worker sh -c '[ -n "$OPENAI_API_KEY" ] && echo 있음'`처럼 키 값을 찍지 않는 명령으로 확인해요 | 키가 있고 모델이 팀에서 정한 값 |
| 켠 직후 대표 문의 1건 | 학부모 계정으로 문의 한 건을 보내고 담임 받은함을 봐요 | 3분 안에 카드가 생기고, 그동안 담임 화면이 느려지지 않음 |

**켜는 법.** `.env.server`에 `ANSWER_WRITER=graph`를 넣고 api·worker만 다시 만들어요. 이미지는 다시 빌드하지 않고 db·redis도 건드리지 않아요. beat는 정해진 시각에 작업을 넘기기만 하고 답변 초안을 쓰지 않아서, beat의 값은 옛것이어도 괜찮아요. 다만 api가 다시 뜨는 몇 초 동안은 요청이 실패할 수 있어요.

```bash
compose=(docker compose --env-file infra/team-server/.env.server -f compose.yaml -f infra/team-server/compose.server.yaml)
"${compose[@]}" up -d --no-build --no-deps api worker
"${compose[@]}" exec worker printenv ANSWER_WRITER   # graph
curl "$API_BASE_URL/health"
```

**이상 신호.** 켠 뒤 아래 신호 가운데 하나라도 나빠지면 바로 꺼요. 나빠졌는지는 평소 값과 비교해야 알 수 있어요. 그러니 켜기 전에 아래 명령을 한 번 돌려 값을 적어 두고, 켠 뒤에 같은 명령으로 다시 재요. 아래 로그인은 데모 계정(`teacher01`)이에요. 데모 시드를 끈 서버(`SEED_DEMO=false`)라면 실제 담임 계정으로 바꿔요.

| 신호 | 보는 법 |
|---|---|
| 담임 화면이 느리거나 500 | 받은함 `curl`의 응답 시간, api 로그의 500 개수 |
| `ai_timeout` 카드가 몰림 | 첫 번째 SQL의 `ai_timeout`·`ai_failed` 요청 수(최근 1시간) |
| DB 연결이 늘고 줄지 않음 | 두 번째 SQL의 `idle in transaction`과 전체 연결 수 |

```bash
token=$(curl -s "$API_BASE_URL/api/v1/auth/login" -H 'Content-Type: application/json' \
  -d '{"login_id":"teacher01","password":"demo1234"}' | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -s -o /dev/null -w '%{http_code} %{time_total}s\n' -H "Authorization: Bearer $token" "$API_BASE_URL/api/v1/cards"
"${compose[@]}" logs --since 10m api | grep -c '" 500'
"${compose[@]}" exec db psql -U yuchion -d yuchion -c "SELECT detail->>'handoff_reason' AS reason, count(DISTINCT request_id) FROM events WHERE detail ? 'handoff_reason' AND created_at > now() - interval '1 hour' GROUP BY 1"
"${compose[@]}" exec db psql -U yuchion -d yuchion -c "SELECT state, count(*) FROM pg_stat_activity WHERE datname = current_database() GROUP BY 1"
```

**끄는 법.** `.env.server`의 값을 `ANSWER_WRITER=stub`으로 되돌리고 켤 때와 같은 `up` 명령을 다시 돌려요. `printenv`에 `stub`이 나오고 `/health`가 200이면 꺼진 거예요.

- 이미 만든 카드는 그대로 남아요. 모델이 쓴 초안·근거·검사 결과가 카드에 저장돼 있으니, 담임은 평소처럼 승인하거나 고치거나 거절하면 돼요. 끈다고 학부모에게 저절로 나가는 답은 없어요.
- worker를 다시 만들면 그때 처리 중이던 요청은 끊기지만 사라지지는 않아요. 요청은 접수할 때 이미 저장되기 때문이에요. 접수하고 5분이 지나도 카드가 없는 요청은 5분마다 도는 점검에서 한 번 다시 들어가고, 이때는 대역으로 처리돼요. 다시 들어가고도 5분 동안 카드가 없으면 초안 없는 미배정 카드(`card_missing`)로 넘어가요.
- 끈 뒤 새로 들어온 문의 카드에는 지금처럼 대역 초안 문장이 들어가요.

**7-1 이미지 되돌리기와 다른 점.** AI 끄기는 코드와 이미지는 그대로 두고 환경값 하나만 바꿔요. 그래서 모델 때문에 생긴 문제(느림, 3분 초과, DB 연결 증가, 비용)라면 이것부터 해요. 7-1의 `:prev`는 직전 배포의 코드로 돌아가는 방법이라, 새 배포가 뜨지 않거나 코드 오류로 500이 날 때 써요. 다만 `:prev`로 되돌려도 `.env.server`는 바뀌지 않아요. 그래서 `ANSWER_WRITER=graph`가 남아 있으면 AI는 켜진 채예요. 되돌린 판이 `ab58b7c`보다 앞선 코드라면 AI를 먼저 꺼요. 모델 호출을 잠금 밖으로 옮긴 게 `ab58b7c`라서, 그 전 코드는 아직 잠금 안에서 모델을 부르기 때문이에요.

### 5-5. 팀 서버에서 켜 두는 값

기본값은 모두 대역이라, 값을 안 넣으면 실제 모델·그래프 없이 돌아요. 팀 서버는 아래를 켜 두고 확인해요(협업 그래프만 표에 적은 이유로 꺼 둬요). 하나라도 꺼져 있으면 그 부분은 실제와 다르게 돌아요.

| 값 | 켠 상태 | 꺼져 있으면 |
|---|---|---|
| `DAILY_NOTE_WRITER` | `graph` | 알림장 초안이 대역 문장 |
| `ANSWER_WRITER` | `graph` | 문의·민원 답변 초안이 대역 문장 |
| `LLM_MODEL_SUPERVISOR` | 모델 이름(지금 `gpt-6-luna`) | 위험·주제를 낱말 규칙만으로 나눠요. 돌려 말한 위험 글을 놓칠 수 있어요 |
| `REQUEST_AGENT` | `app.modules.requests.graph_agent:run_request` | 그래프·체크포인트·승인 대기(`interrupt`) 없이 대역 입구로 처리 |
| `LAW_GO_KR_OC` | 신청 ID | 법령 조문 근거 없음 |
| `REQUEST_COLLAB_GRAPH` | `1` (11/26부터, #356 머지 뒤) | 기존 요청 그래프(감독 → 자료 → 검사 한 줄)로 돌아가요. 자료 충돌·근거 부족으로 사람에게 넘길 때 카드에 근거·충돌 표시가 안 남던 문제(#349)는 #356에서 고쳐서 켰어요 |
| `EMBEDDING_MODEL` | `BAAI/bge-m3` | 자료를 낱말 점수로만 찾아요 |
| `LANGSMITH_TRACING`·`LANGSMITH_API_KEY` | `true`와 키(11/25부터) | 추적 없음. 기능은 그대로 돌아요 |

값을 바꾼 뒤에는 5-4처럼 api·worker만 다시 만들고 `printenv`로 들어갔는지 봐요. 그다음 학부모 계정으로 문의·권한 밖 요청·위험 민원·상담을 한 건씩 넣어 카드와 원장 보고가 생기는지 확인하고, 확인용 요청은 지워요.

LangSmith에는 모델에 보낸 글이 그대로 남아요. 문의·민원 글은 모델에 보내기 전에 민감한 내용을 가리므로 추적에도 가린 글이 남고, 알림장은 선생님 메모가 그대로 남아요. 요청 그래프 단계에는 요청·카드 ID만 남아요. 추적은 기능별로 한 묶음이에요: `요청 처리`(요청 하나의 분류·답변·검사·승인 대기), `알림장 초안`(반 하나의 아이 전체 작성·검사), `문의 답변 초안`. 묶음 안의 모델 호출은 `역할:모델`(예: `SUPERVISOR:gpt-6-luna`) 이름으로 보여요.

임베딩은 이미지에 패키지가 있어야 해요. `.env.server`에 `INSTALL_EMBEDDING=1`과 `EMBEDDING_MODEL=BAAI/bge-m3`를 넣고 api 이미지를 다시 빌드한 뒤, 빈 조각의 벡터를 채워요. 모델은 api와 worker가 각각 한 번씩 메모리에 읽어요(프로세스마다 약 2GB).

```bash
"${compose[@]}" build api && "${compose[@]}" up -d --no-deps api worker beat
"${compose[@]}" exec -T api python -m db.seeds.embed
```

## 6. 배포 확인

API 기준 주소를 `API_BASE_URL`, 웹 주소를 `WEB_BASE_URL`로 정해요.
API 기준 주소는 `/health`·`/api/v1/...` 앞까지예요. 경로 접두사가 있다면 앞단도 똑같이 연결해요.

```bash
tools/smoke.sh "$API_BASE_URL"
# 필요하면 SMOKE_LOGIN_ID·SMOKE_PASSWORD·SMOKE_NOTE_DATE·SMOKE_TIMEOUT을 지정해요.
```

smoke는 health → 담임 로그인 → 반 아이 목록 → 알림장 초안 생성 → succeeded 상태 →
아이별 알림장 목록을 확인해요. 실패하면 0이 아닌 종료 코드를 돌려줘요.
기본값은 `teacher01`·`demo1234`·한국 날짜 오늘·시간 제한 180초예요.
실제 그래프로 검사한다면 `SMOKE_TIMEOUT`을 모델 대기 시간에 맞게 늘려요.
모든 출력에는 `[TEST]`가 붙고 토큰·비밀번호는 출력하지 않아요.

**이 검사는 초안을 만들어요.** 가상 데이터가 있는 데모 환경에서 실행해요.
같은 반·날짜 입력이 있으면 기존 입력을 조회하므로 새 생성까지 보려면 빈 날짜를 골라요.
확인·보내기는 실행하지 않아요. mock·DB 모두 같은 스크립트를 써요.

| 확인 항목 | 방법 | 기대 결과 |
|---|---|---|
| API 상태 | `curl "$API_BASE_URL/health"` | `{"status":"ok"}` |
| 웹 접속 | 브라우저로 `$WEB_BASE_URL` | 첫 화면 표시 |
| 원장 화면 (T53 구현 후) | 같은 웹 URL에서 원장 계정으로 로그인 | 원장 화면이 표시되고 역할별 접근이 적용됨 |
| 핵심 흐름 | `tools/smoke.sh "$API_BASE_URL"` | 로그인·아이 목록·초안 상태·알림장 목록 통과 |
| 리소스 | `docker stats --no-stream`, `uptime`, `free -h` | CPU·메모리 사용량 기록 (T30 기록 대상, 아래 실측) |

**리소스 실측 (T30, 2026-11-26 15:50 KST, `develop` 7ad4939).** 컨테이너 6개(api·worker·beat·web·db·redis)가 다 떠 있는 상태예요.

| 항목 | 쉬는 중 | 요청을 넣었을 때 |
| --- | --- | --- |
| 부하 평균(1·5·15분, vCPU 2개) | 0.19 · 0.36 · 0.42 | — |
| api 컨테이너 CPU | 0.2% | 15~30% (문의 1건 처리 중) |
| 메모리(서버 전체) | 1.1GiB / 7.6GiB | 큰 차이 없음 |

컨테이너별 메모리(16:52 `docker stats`)는 worker가 약 1GiB로 가장 크고, api 120MiB·db 62MiB·beat 46MiB·redis 7MiB·web 5MiB예요. vCPU 2개에 부하 평균이 0.5 아래이고 메모리도 6GiB 넘게 남아서, 지금 사양을 올릴 일은 없어요.

smoke는 웹·TLS·모바일을 검증하지 않아요. 현재 웹의 API 연결은 프론트 작업에서 따로 확인해요.
DB 모드의 미구현 문의·카드·상담·알림 API는 아직 501일 수 있어요.

## 7. 롤백 · 백업

### 7-1. 롤백 (코드)
현재 이미지 레지스트리(ECR)를 쓰지 않으므로 커밋 기준으로 되돌립니다.
배포 담당자가 백업·마이그레이션 호환성을 확인한 뒤 진행해요.
이미 스키마가 바뀌었다면 코드만 되돌려서 복구된다고 가정하지 않아요.
롤백에서는 `git pull`을 하는 배포 스크립트 대신 같은 Compose 옵션으로 직접 기동해요.

```bash
git log --oneline -5           # 정상이던 커밋 확인
git checkout <정상 커밋>
docker compose --env-file infra/team-server/.env.server \
  -f compose.yaml -f infra/team-server/compose.server.yaml up -d --build
tools/smoke.sh "$API_BASE_URL"
```
`TODO`: ECR 도입 시 이미지 태그 기준 롤백으로 변경

**바로 직전 판으로 되돌리기.** `deploy.sh`는 새로 빌드하기 전에 api·web 이미지의 지금 판을 `:prev` 태그로 남겨요. 새 판이 뜨지 않으면 다시 빌드하지 말고 그 태그를 원래 이름으로 돌려 기동해요. 스키마가 바뀐 배포였다면 위와 같이 호환성부터 확인해요. 아래 이미지 이름은 기본값(`API_IMAGE` 없음, 프로젝트 `yuchion-server`)이에요.

```bash
docker tag yuchion-api:prev yuchion-api:local
docker tag yuchion-server-web:prev yuchion-server-web:latest
docker compose --env-file infra/team-server/.env.server \
  -f compose.yaml -f infra/team-server/compose.server.yaml up -d --no-build
tools/smoke.sh "$API_BASE_URL"
```

### 7-2. DB·사진 백업 · 복원
배포하기 전에 먼저 `infra/backup/backup.sh`로 백업을 받아요. DB 덤프와 사진 볼륨, 그리고 만든 시각과 커밋, alembic 판이 `backups/<UTC 시각>/` 폴더 하나에 함께 들어가요.
보관 개수(`BACKUP_KEEP`, 기본 7)를 넘는 옛 폴더는 지워져요. 환경 파일과 Compose 옵션은 배포 스크립트와 같은 기본값을 써요.
복원은 배포 담당자가 대상 서버와 백업 폴더를 확인한 뒤에 진행해요. `restore.sh`를 `--yes` 없이 돌리면 할 일만 보여 줘요.
복원 순서와 복원 뒤에 다시 적용하는 법, 사진 정리는 [infra/backup/README.md](backup/README.md)를 봐요.

```bash
# 백업
infra/backup/backup.sh
# 복원: 할 일을 먼저 확인한 뒤 --yes로 실행해요.
infra/backup/restore.sh backups/<시각>
infra/backup/restore.sh backups/<시각> --yes
# 다른 환경 파일을 쓰면 백업은 첫 번째, 복원은 두 번째 인자로 넘겨요.
# infra/backup/backup.sh "$SERVER_ENV_FILE"
# infra/backup/restore.sh backups/<시각> "$SERVER_ENV_FILE" --yes
```

## 8. 모바일 앱 배포 (compose와 별개)

> 현재 `apps/web/package.json`에 Capacitor 패키지가 아직 없습니다. 설치 후 아래 절차를 확정합니다. `TODO`

### 8-1. 공통
- `VITE_API_BASE_URL`을 **운영 https 주소**로 지정해서 웹 빌드
- 앱 버전 번호 규칙: `TODO`
- 설치 채널·버전·날짜를 기록 (T72·T77 기록 대상)

### 8-2. Android (APK)
```bash
cd apps/web
npm run build
npx cap sync android
# Android Studio → Build → Generate Signed Bundle / APK
```
- 서명 키(keystore)는 **레포에 올리지 않음**, 보관 위치 `TODO`
- 배포: 서명 APK 공유 / Play 비공개 테스트 (승인 시)

### 8-3. iOS (TestFlight, 예정)
```bash
cd apps/web
npm run build
npx cap sync ios
# Xcode → Product → Archive → App Store Connect 업로드
```
- 배포: App Store Connect → TestFlight → 테스터 이메일 초대
- 필요: **Mac**(담당 `TODO`), **Apple Developer 계정**(연 $99, 명의 `TODO`), **HTTPS 서버**

## 9. 트러블슈팅

| 증상 | 확인할 것 |
|---|---|
| 외부에서 접속 안 됨 | 보안그룹 인바운드 포트, `docker compose ps` 상태 |
| 웹은 뜨는데 데이터가 안 나옴 | `VITE_API_BASE_URL`이 localhost로 빌드되지 않았는지 |
| 앱에서만 API 실패 (iOS) | 서버가 https인지 |
| api가 바로 종료됨 | `docker compose logs api`, `.env`의 `DATABASE_URL` |
| 메모리 부족으로 컨테이너 재시작 | `docker stats`, 인스턴스 사양 상향 검토 |

`TODO`: 실제 배포하면서 겪은 문제를 추가합니다.

## 10. 변경 이력

| 날짜 | 작성자 | 내용 |
|---|---|---|
| 2026-11-17 | `TODO` | 초안 작성 |
| 2026-11-20 | 태웅 | 기존 구조를 복원하고 환경변수·배포·확인·롤백 절차를 서버 Compose·스크립트에 맞췄어요. |
| 2026-11-23 | 태웅 | 7-2의 수동 `pg_dump`·`psql` 절차를 사진까지 받는 백업·복원 스크립트로 바꿨어요. |
| 2026-11-24 | 태웅 | 5-4에 요청 처리 AI(`ANSWER_WRITER`)를 켜는 조건, 켜고 끄는 법, 이상 신호를 더하고, Compose가 이 값을 api·worker에 넘기게 했어요. |
| 2026-11-24 | 태웅 | 5-5에 팀 서버에서 켜 두는 값(감독 모델·요청 그래프·법령 키·협업 그래프·임베딩)과 꺼졌을 때 달라지는 점을 적고, Compose가 `REQUEST_COLLAB_GRAPH`·`EMBEDDING_MODEL`·`LANGSMITH_TRACING`을 넘기게 했어요. |
| 2026-11-25 | 태웅 | 5-5에 LangSmith 추적을 켠 상태와 무엇이 남는지 추가 |
| 2026-11-25 | 태웅 | 5-5의 LangSmith 설명을 기능별 묶음(요청 처리·알림장 초안·문의 답변 초안)으로 고침 |
| 2026-11-26 | 태웅 | 1장 EC2 사양·주소·브랜치를 채우고, 5-2에 팀 서버 자동 반영, 5-5 협업 그래프 켬(#356 뒤), 6장에 CPU·메모리 실측(T30)을 더함 |
