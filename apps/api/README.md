# apps/api

FastAPI 애플리케이션이에요. 저장소 루트에서 Docker로 바로 띄워요.

```sh
docker compose up
```

처음에는 이미지도 만들어요. 코드를 바꾼 뒤에는 `docker compose up --build`로 다시 만들어요.
`.env`가 없어도 기본 `mock`으로 떠요.
API는 `http://localhost:8000`, 화면은 `http://localhost:5173`이에요.
데모 로그인은 `teacher01` / `demo1234`예요. DB는 `localhost:15432`에서 접속해요.
`API_PORT`·`POSTGRES_PORT`로 호스트 포트를 바꿀 수 있어요. 컨테이너끼리는 `db:5432`를 써요.
`API_PORT`를 바꾸면 화면이 쓰는 `VITE_API_BASE_URL`도 같은 API 주소로 맞춰요.

DB 모드는 다음 순서로 켜요.

```sh
cp .env.example .env
# .env의 DATA_BACKEND를 db로 바꾸고, 아래 명령으로 만든 값을 JWT_SECRET에 넣어요.
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
docker compose up --build
```

Compose는 루트 `.env`를 자동으로 읽고, 셸에 같은 변수가 있으면 셸 값을 먼저 써요.
`DATA_BACKEND`·`JWT_SECRET`·`DAILY_NOTE_WRITER`와 API 설정을 컨테이너에 전달해요.
DB 모드의 시작 순서는 설정 검사 → `alembic upgrade head` → 데모 시드 → uvicorn이에요.
`SEED_DEMO`는 기본 true이고, false면 DB 기동 때 데모 시드만 건너뛰어요. 마이그레이션은 그대로 실행해요.
마이그레이션이나 시드가 실패하면 API를 시작하지 않아요. 시드는 기존 행을 덮어쓰지 않아요.
mock에서는 마이그레이션·시드를 실행하지 않아요. API는 DB에 접속하지 않고 모의 데이터를 써요.
Compose의 DB 서비스는 두 모드에서 함께 떠요. `docker compose down`은 DB 볼륨을 유지해요.
DB 계정·비밀번호를 바꿀 때는 `.env`의 `POSTGRES_*`와 `DATABASE_URL`을 함께 맞춰요.
이미 만들어진 DB 볼륨의 계정·비밀번호는 환경 변수를 바꿔도 자동으로 바뀌지 않아요.

워커를 쓰려면 `.env`에 `DATA_BACKEND=db`·별도 `JWT_SECRET`·`RUN_IN=worker`를 넣고 실행해요.

```sh
docker compose --profile worker up --build
```

기본 `RUN_IN=api`는 기존 BackgroundTasks 실행을 유지해요. worker 프로필은 Redis·Celery worker·Beat를 더해요.
API가 마이그레이션·시드를 끝내고 정상 응답한 뒤 worker·Beat가 시작해요. 두 서비스는 DB 초기화를 반복하지 않아요.
`CELERY_BROKER_URL` 기본값은 Compose 내부 Redis 주소예요. Redis 포트는 호스트에 열지 않아요.
Redis는 appendonly와 전용 볼륨을 써요. API·worker는 같은 DB·작성기·에이전트·근무 시간·모델 설정을 받아요.
worker는 `threads`로 실행하고 `WORKER_CONCURRENCY`(기본 4)만큼 동시에 처리해요.
알림장 초안은 `notes`, 요청·발송·점검은 `default` 큐로 보내고 worker가 두 큐를 읽어요.
API 이미지를 한 번 빌드해 worker·Beat도 함께 써요. 두 서비스는 종료되면 자동 재시작하고 worker는 ping으로 상태를 확인해요.
설정이 맞지 않으면 worker·Beat 시작 때 경고해요. worker 모드 API는 시작 때 브로커를 한 번 확인하고, 실패해도 경고를 남긴 뒤 계속 떠요.
mock은 메모리를 프로세스끼리 공유하지 않으므로 기존 API 안 대역만 쓰고, 워커 주기 작업은 DB를 열지 않아요.

`DATA_BACKEND` 기본값은 `mock`이에요. `db`는 PostgreSQL의 계정과 관계를 읽어요.
DB 주소는 `DATABASE_URL`로 받아요. Docker 밖에서는 마이그레이션·시드를 직접 실행해요.
DB 모드는 `JWT_SECRET`에 32바이트 이상의 별도 키가 필요해요. 값이 없거나 mock 기본값·
`.env.example`의 예시 값이면 기동을 중단해요. mock의 개발용 기본값은 그대로 쓸 수 있어요.

| 범위 | mock | db |
| --- | --- | --- |
| 로그인·내 정보(API 1·2) | 구현 | argon2·JWT·token_version 구현 |
| 기관·반 배정 기간·카드 재배정·보호자 관계 | 구현 | 범위 함수와 404 거부 이력 구현 |
| 알림장·반 아이 목록(API 22~26·30) | 구현 | 초안·조회·수정·확인·반 전체 발송과 보호자 알림 행 구현 |
| 원본·이력·다시 만들기·내 기억(API 31~33) | 구현 | 0003 원본 보존·아이별 이력·미확인 재생성·개인 기억 조회/삭제 |
| 요청 생성·목록·상세·스트림·대화·확인(API 3~7·9) | 구현 | 요청 저장·대역 분류/카드·이력·알림 행 구현 |
| 투약·귀가(T46, API 34~36, 팀 확인 전 초안) | 구현 | 등록/미등록 인계자·누락 경고·판 검사·정정 후 재확인·확인/완료·이력/알림 원자 저장 |
| 자료 목록(API 28) | 구현 | 알림장 출처 확인용 읽기 구현 |
| 받은함·카드 상세/SSE·결정·재분류·지시·재배정·원장 현황(API 12~16·18·19·21) | 구현 | 행 잠금·판 검사·승인/이력/알림을 한 트랜잭션으로 저장 |
| 알림 목록·읽음(API 10·11) | 구현 | 본인 알림·노출 시각·첫 읽음 시각 보존 |
| 민원 반복·고위험 원장 보고(T31) | 구현 | 같은 반·30일·주제 집계와 동시 분류·기한·알림 시각 검증 |
| 상담 후보·시간 선택/확정(API 8·17, T35) | 구현 | 근무 시간·바쁜 일정·담임/상담실 충돌 계산, 동시 확정·알림 행 구현 |
| 상담 종료·지연 알림(T48, API 37 [제안] v0.6) | 구현 | 담임 지연 입력·시각별 알림/대체 시간 갱신·당일/3시간 상한, 종료 입력·화면·예약 변경은 후속 |
| 거절 이유 기억·규칙 제안/결정(API 20, T39) | 구현 | 개인 기억·세 번째 제안·주인 결정·승인 전 미적용 구현 |
| 워커·서비스 안 알림(T26) | API 안 대역 유지 | Celery·Beat·중복 발송 잠금·최대 3회 시도/백오프 구현 |
| 피드·앨범·사진 공개 범위(T54, API 38~49 [제안] v0.7) | 구현 | 칸별 권한·파일 검사/삭제·즉시 사진 범위 적용 구현 |
| 자료 올리기/상세(API 27·29) | 구현 | 제목 단위 조각·충돌 판정·2MiB 제한·같은 바이트 중복 처리·기관/반 범위 검사 구현 |

업무 API 49개(기준 v0.8, develop `24258f2`)는 모두 DB 모드에서 동작해요. 501로 막아 둔 API는 없어요.
그중 34~49번 16개는 계약을 팀이 확인하기 전인 제안이에요. API별 상태는 [API 설계 문서](../../Docs/Step2/API_설계_문서.md) 2장 표에 있어요.
`GET /health`는 별도예요. 투약·귀가와 상담 지연 입력은 **팀 확인 전 초안**을 유지해요.
기본 요청 에이전트는 낱말 대역이고, 알림장만 `DAILY_NOTE_WRITER=graph`로 실제 그래프를 고를 수 있어요.
최종 시험 수·결정 이유·후속 범위는 [백엔드 구현 기록](../../Docs/Step3/백엔드_구현_기록.md)에 모았어요.

구현한 API는 범위 밖이면 404예요. 범위 거부는 별도 트랜잭션으로 기록해
404 응답 뒤에도 `permission_denied` 이력이 남아요.
카드 결정은 범위 검사 뒤 요청 → 카드 순서의 `FOR NO KEY UPDATE`로 직렬화해요.
별도 연결의 권한 거부 이력은 이 잠금 중에도 바로 저장돼요.
열린 원장 보고가 있으면 담임의 재분류로는 escalated를 내리지 않아요.
원장의 일반 재분류는 보고 카드를 닫고 연결 이력을 남겨요. 지시 뒤 회신 승인·발송은 별도예요.
거절한 옛 회신 카드로 완료할 수 없고, 반 없는 규칙 제안 카드의 classroom은 null이에요.

요청 상세는 현재 담임·대체 담임의 배정 기간과 카드 재배정·기관·보호자 범위를 검사해요.
DB에서는 전체 대화와 상태 표시 이름만 담은 진행 기록, 상담 후보·예약, 반려 이유와 보류 예정일을 읽어요.
회신 뒤에는 승인된 카드의 출처를 읽어요. 초안은 카드에 저장하고 공개 대화에 넣지 않아요.
투약·귀가는 T46 팀 확인 전 초안 v0.6으로 열었어요. 학부모 자기 요청 조회·대화·스트림과 교직원 실제 확인·완료를 지원해요.
자료 목록은 교직원만 봐요. 원 전체 자료와 현재 담당 반 자료를, 원장은 기관 전체를 읽어요.
교직원은 `visibility`의 세 값 모두 읽어요. 학부모의 요청 출처는 `parents`·`all`만 보여요.
자료 적용일이 비어 있으면 생성한 한국 날짜를 읽기 기본값으로 써요. DDL의 빈 날짜를 바꾸지는 않아요.
기존 데모 DB의 빈 요청 제목·첫 보호자 메시지는 시드를 다시 실행하면 채워져요.

인증·알림장·요청 흐름·받은함·카드 결정·알림·자료 목록 HTTP 시험은 mock·DB 두 모드로 돌아요. `tools/test_db.sh`가
전용 임시 DB에서 마이그레이션·기관 경계·범위 시험도 실행하고 컨테이너를 지워요.

## 요청 실행

DB 요청은 요청·첫 메시지·created 이력을 한 트랜잭션에서 저장하고 202로 접수해요.
같은 (requester_id, client_request_id)로 재전송하면 새 메시지·작업 없이 기존 요청과 현재 상태를 200으로 줘요.
`RUN_IN=api`면 FastAPI BackgroundTasks가 같은 API 프로세스에서 요청 대역을 불러요.
`RUN_IN=worker`면 저장을 커밋한 뒤 Celery에 요청 UUID만 보내요.
직접 실행할 때 REQUEST_AGENT=모듈:함수로 입구를 골라요. 기본값은
app.modules.requests.agent_stub:run_request이고 인자는 요청 UUID 하나예요.
입구는 카드 저장과 요청 상태 변경을 한 트랜잭션에서 처리해야 해요.
Compose도 `REQUEST_AGENT`를 API·worker에 같이 전달해요. 기본 입구는 두 실행 모드에서 같아요.

대역은 모의 낱말 분류와 카드 만들기를 DB로 옮긴 코드예요. 실제 모델·외부 API는 부르지 않아요.
근거를 찾았다고 꾸미지 않고 card_evidence는 비우며 draft.no_evidence를 남겨요.
DB 상담 후보는 근무 시간·바쁜 일정·담임/상담실 예약·유효한 학부모 체크에서 계산해요.
시간 선택·담임 확정 API도 DB에 연결했어요. 자세한 계산 범위는 [상담 모듈](app/modules/consultations/README.md)을 봐 주세요.
위험 분류는 두 모드가 같은 낱말 대역을 써요. 실제 감독 AI의 분류 품질은 별도로 평가해요.
요청 이력과 notifications 행은 상태 변경과 같은 트랜잭션에 저장해요.
알림은 pending·dedupe_key·deliver_after를 채워요. 목록·읽음은 같은 기관의 본인 알림만 보여요.
Beat는 1분마다 발송 작업을 넣어요. 앱 안 알림 행을 sent로 바꾸고 외부 알림은 보내지 않아요.
T48 상담 점검도 1분마다 실행해요. 담임에게 종료 10분 이내 알림을, 명시된 지연의 영향을 받는
예약에는 담임·학부모 대체 시간 제안을 한 번 남겨요. 실제 지연은 시간 경과로 추측하지 않아요.
[제안] v0.6 `POST /consultations/{booking_id}/delay`로 그 반의 예약 담임이 expected_end_at을 기록해요.
시작한 상담의 현재·원래 종료보다 뒤이며 같은 KST 날짜·원래 종료 + 3시간 이내여야 해요(0009).
값이 바뀌면 알림·대체 시간을 다시 계산하고 옛 제안은 superseded 이력을 남겨요.
종료 알림은 근무 밖에도 즉시예요. 발송 기록만 held, 목록 노출은 유지해요.
실제 종료 입력·화면·예약 변경/취소는 후속 계약이에요. 자세한 조건·한계는 [상담 모듈](app/modules/consultations/README.md)을 봐 주세요.
행 잠금·SKIP LOCKED와 유니크 dedupe_key로 동시에 실행해도 한 번만 처리해요.
발송은 총 3회까지 시도해요. 실패하면 60초·120초 뒤에 다시 시도하고 세 번째 실패는 failed로 남겨요.
`next_attempt_at`만 바꿔 원래 노출 시각·읽은 시각을 유지해요. Beat 시각 차이를 고려해 조회에 5초 여유를 두되 deliver_after·근무 시작 시각보다 일찍 보내지 않아요. 실패 이유는 고정 코드만 남기고 tool_failed 이력을 기록해요.
최종 실패는 연결 카드에 notify_failed를 남겨 기존 상세 경고로 보여요.
비활성 수신자는 재시도 없이 failed로 남겨요. 성공 시 attempts를 올리고 sent_at을 처음 한 번 기록해요.
발송 시점에도 근무 시간을 다시 검사해 늦어진 주기 작업·재시도가 퇴근 뒤 일반 알림을 보내지 않아요.

학부모 스트림은 저장된 이력에서 단계만 읽고 완료 상태에서 done을 보내요.
진행 중에는 짧게 다시 읽으며 최대 5분 후 공통 error로 닫아요. 초안·카드·내부 실패 이유는 보내지 않아요.
DB 읽기만 스레드에서 하고 poll 대기는 비동기로 기다려 다른 API의 스레드를 계속 쓸 수 있어요.
입구가 예외를 내면 요청을 보존하고 초안 없는 미배정 카드로 넘겨요(ai_failed).
실행기는 입구를 3분(API 6.1)까지만 기다리고, 넘으면 같은 초안 없는 미배정 카드로 넘겨요(ai_timeout).
늦게 끝난 실행은 저장 직전 요청 잠금 안 재확인(상태·카드 유무)에서 버려져요.
감독·자료·검사 모델과 공공 API는 요청 행 잠금 밖에서 부르고, 잠금 트랜잭션은 재확인과 저장만 해요.
중간에 프로세스가 멈춘 경우 app.modules.requests.runner.sweep_missing_cards(now)로
5분 넘게 received·classified·assigned이고 카드가 없으면 처리를 한 번 다시 넣고 agent_requeued 이력만 남겨요.
그 뒤 5분이 더 지나도 카드가 없을 때만 인계해요(card_missing). 재전달은 요청 잠금 안에서 한 번만 정하고 커밋 뒤 실행해요.
투약·귀가는 사람이 확인하는 별도 흐름이라 AI 카드 생성·누락 카드 점검에서 제외해요.
DB 시드의 보호자 문의 9건은 받은함 대상이에요. `RUN_IN=api`에서는 자동 점검을 돌리지 않아
시드 문의는 접수됨·카드 없음으로 남아요. 새로 접수한 요청은 BackgroundTasks에서 처리해요.
`RUN_IN=worker`에서는 Beat의 5분 주기 점검이 접수 후 5분 넘게 카드가 없는 시드 문의를
한 번 다시 전달해요. 기본 대역이 정상 실행되면 9건 모두 담임의 `pending` 회신 초안 카드가 돼요.
미배정 데모는 입구 예외(`ai_failed`)나 재전달 뒤에도
5분 넘게 카드가 없는 경우(`card_missing`)를 써요.
담당 없는 인계 카드가 생기면 같은 기관 원장에게 new_card 알림을 한 번 남겨요.
투약·귀가는 학부모 자신의 요청 목록·상세·대화·스트림에 포함돼요.
교직원은 별도 `/care-requests` 목록에서 확인·완료해요. 상세 계약은 T13 3.27의 팀 확인 전 초안이에요.
Beat는 5분마다 누락 카드 점검과 알림장 복구를 실행해요. 지난 주기 작업은 점검 290초·발송과 상담 알림 55초 뒤 만료돼요. T13의 점검 주기도 5분으로 맞췄어요.
큐 전달이 실패해도 접수 행은 남아요. 요청은 점검에서 한 번 재전달한 뒤 계속 카드가 없으면 인계하고 queued 알림장은 다시 전달해요.
추가 대화와 확인은 요청 행을 먼저 잠가요. 민원 회신 뒤 추가 글은 확인을 지우고
회신 카드를 pending으로 돌리며 version을 올려요. 확인 재시도는 처음 시각과 알림을 유지해요.
범위 함수의 connection 인자로 호출 쪽 트랜잭션을 쓰고, 404 거부 이력만 별도로 커밋해요.

민원은 같은 기관·반의 최근 30일·같은 주제를 세요. 보낸 보호자나 처리 상태가 달라도 합산하고,
`other`는 합산하지 않아요. 세 번째부터 담임 회신 카드와 원장 보고 카드를 함께 남겨요.
DB에서는 같은 기관·반·주제의 분류를 트랜잭션 자문 잠금으로 직렬화해 동시 접수 때 보고가 빠지지 않아요.
생성 판단과 받은함·카드 상세는 같은 집계 함수를 써요.
긴급 네 종류와 판단 필요는 초안 없이 두 카드를 만들고 담임·원장에게 알림 행을 남겨요.
판단 필요는 사람이 다시 분류해야 회신할 수 있고, 긴급도 담임이 직접 작성·승인하기 전에는 보내지 않아요.
두 카드의 기한은 접수 시각 기준으로 같아요. 일반은 주말·공휴일을 뺀 24시간,
긴급·판단 필요는 휴일에도 2시간이에요. 기한 초과는 원장 현황의 지연으로만 세며 자동 보고하지 않아요.
퇴근 뒤 교직원 알림은 기본 아이 안전만 즉시예요. `IMMEDIATE_RISK_CATEGORIES`로 긴급 종류를 바꿔요.
나머지 긴급·판단 필요와 일반 보고는 `HOLIDAYS`·`WORK_HOURS`에 맞춰 다음 근무 시작으로 미뤄요.

## 받은함과 카드 결정

DB 받은함은 staff_inbox 뷰를 읽어요. 현재 담당 반·배정 기간과 본인 재배정을 적용한 뒤
기존 필터·종류 건수·긴급 우선 정렬·쪽 나누기를 유지해요.
0004는 발송한 민원 회신을 처리 완료 전까지 받은함에 남겨요.
학부모 확인 전에는 in_progress, 확인 뒤에는 needs_review, 처리 완료 뒤에는 done이에요.
거절한 옛 초안은 done을 유지해요. 0001은 바꾸지 않았어요.

결정은 요청 행 → 같은 요청의 카드 UUID 순서로 SELECT FOR UPDATE를 걸어요.
같은 카드 판의 기존 결정은 ALREADY_DECIDED, 다른 판은 CARD_VERSION_CONFLICT예요.
승인 기록·공개 회신·상태·이력·알림을 함께 저장하고 실패하면 전부 되돌려요.
회신 승인 뒤 approved → sent 순서로 이력을 남겨요. 민원 회신 승인·완료는 담임이 해요.
원장은 보고 지시와 재배정을 할 수 있어요. 다시 분류는 기존 모의 규칙을 유지해요.
거절 후 새 초안 카드는 초안 문장·검사 결과 없이 만들고 no_evidence를 남겨요(API 5.7 초안 없는 카드).
일반 승인은 409라 담임이 직접 써서 edit_approve로 보내요.
상담 재제안도 DB 일정으로 계산해요. 거절·반려는 결정한 담임의 개인 기억으로 저장해요.
지우지 않은 같은 이유 코드가 세 건 이상이면 규칙 제안 카드 하나를 만들어요.
규칙을 거절한 뒤에는 그 결정 이후의 새 기억 세 건이 있어야 다시 제안해요.
기억에는 출처 요청의 반 아이 이름을 낱말·조사 경계에서 가려요. 반이 없으면 같은 기관 전체를 봐요.
제안 저장 실패는 카드 거절을 막지 않아요.
주인의 켜기·거절은 규칙·카드·결정·이력을 한 트랜잭션에서 바꿔요.
자동 대역은 시간·말투를 추론하지 않아요. 구체적인 규칙 추출과 적용 범위는 [기억 모듈](app/modules/memories/README.md)을 봐 주세요.

원장 현황의 숫자는 director_overview, 재배정 기록은 기관 내 events에서 읽어요.
eval_runs는 기관 칸이 없는 공통 평가 기록이며 최근 20건을 보여요.
교직원 SSE는 저장 이력의 단계와 현재 카드 초안을 재생해요. 실시간 모델 토큰은 아직 없어요.
요청 없는 카드도 상세·SSE로 읽고 done.request_status는 null이에요.
알림 목록·읽음은 본인 기관·수신자·deliver_after를 검사하고 첫 read_at을 보존해요.
DB 조회는 pending을 sent로 바꾸지 않아요. 발송·재시도는 별도 워커 작업이 처리해요. 목록·읽음 조회는 발송 상태를 바꾸지 않아요.

## 로컬 검사

Python 3.12 이상과 가상환경을 준비한 뒤 저장소 루트에서 실행해요.

```sh
uv venv .venv
uv pip install --python .venv/bin/python -r apps/api/requirements-dev.txt
tools/check.sh
tools/test_db.sh
```

`tools/check.sh`는 ruff 기본 규칙(E4·E7·E9·F)과 mock 전체 시험을 차례로 실행해요.
기존 미사용 import·늦은 import·짧은 변수·lambda 지적은 pyproject에 파일별 예외로 뒀어요.
일괄 포맷은 하지 않아요.
DB 시험 변수가 셸에 남아 있어도 check는 mock만 실행해요. DB 검사는 별도 명령이에요.
두 스크립트의 모든 출력에는 `[TEST]`가 붙어요. DB 검사는 Docker가 필요해요.

## 알림장 코드 읽는 순서

`POST /daily-notes/drafts` 요청 하나를 아래 순서로 따라가요.

1. `app/api/routes/resources.py`의 `draft_notes`에서 요청을 받아요. 본문은 `app/api/schemas/actions.py`에서 검사해요.
2. `app/core/auth.py`가 토큰·계정을 보고, `app/backend.py`가 mock 또는 DB 구현을 골라요.
3. DB의 `app/modules/daily_notes/notes.py`가 `app/core/scope.py`로 담임의 반·배정 기간을 검사해요.
4. 같은 모듈이 `app/core/db.py`의 트랜잭션 안에서 SQL로 입력·묶음 카드를 저장해요.
5. `app/modules/daily_notes/runner.py`가 뒤에서 초안을 만들고 아이별 알림장을 SQL로 저장해요.

표 정의와 변경 순서는 `migrations/README.md`를 봐요.

## 초안 실행과 데모

DB 초안은 입력을 `queued`로 저장해요. `RUN_IN=api`는 같은 프로세스의 BackgroundTasks,
`RUN_IN=worker`는 Celery 태스크에서 같은 runner를 실행해요.
`running`을 거쳐 `succeeded` 또는 `failed`가 돼요. `DAILY_NOTE_WRITER`는
`모듈:함수` 형식이고 기본값은 `app.modules.daily_notes.stub_writer:write`예요.
`DAILY_NOTE_WRITER=graph`로 고르면 영민님 그래프의 `draft_daily_notes(payload)`를 불러요.
이 설정은 DB 초안 runner에 적용돼요. mock은 기존 대역 동작을 유지해요.
그래프는 `OPENAI_API_KEY`와 `LLM_MODEL_DOCUMENT`·`LLM_MODEL_CHECKER`를 읽어요.
역할별 모델 값이 비면 `LLM_MODEL_DEFAULT`를 써요. 값은 `.env.example`을 참고해요.
`NOTE_DRAFT_CONCURRENCY`(기본 5)도 그래프에 전달해요. 동시 실행은 이 설정을 지원하는 그래프에서 적용돼요.
입구는 T13 3.19의 입력을 받아 아이별 `child_id`·`content`·`open_checks` 목록을 돌려줘요.
아이 결과가 빠지거나 형식이 잘못되면 그 아이만 `draft_failed`로 저장해요.
입구 전체가 실패하면 아이별 저장 없이 작업을 `failed`로 남겨요.
입력은 UUID 문자열·ISO 날짜만 써서 JSON으로 바로 주고받을 수 있어요.
확인 항목의 `c1` 같은 내부 ID는 DB 저장 때 새 UUID로 바꾸고, 없는 `request_id`는 null로 남겨요.
수정·확인 요청의 `resolved_checks`에는 조회 응답의 ID를 보내요.
그래프 연결 시험은 가짜 writer·checker를 주입하며 실제 모델은 부르지 않아요.

지금은 **API·worker·Beat 각각 하나**로 실행해요. API 안 실행 모드는 API 재시작 때
남은 `running`을 `queued`로 되돌리고 모든 `queued` 입력을 다시 실행해요.
worker 모드의 API 재시작·5분 점검은 작성기 시간 제한을 넘긴 `running`만 되돌려요.
진행 중 worker 작업은 유지해요. queued 중복 전달은 runner의 원자적 상태 검사로 한 실행만 가져가요.
기동을 기다리는 동안 초안을 전부 만들지는 않아요. 복구 작업도 뒤에서 차례로 실행해요.
writer는 `DAILY_NOTE_WRITER_TIMEOUT`초(기본 300초) 안에 답해야 해요.
시간이 지나면 기존 `failed`·`UPSTREAM_UNAVAILABLE` 경로로 끝내고 늦은 결과는 저장하지 않아요.
writer 스레드를 강제 종료하지는 않으므로 외부 호출 자체의 시간 제한도 writer에서 설정해야 해요.

오늘 날짜로 보호자 요청 누락을 시연하려면 전용 데모 DB에 마이그레이션을 적용한 뒤
저장소 루트에서 아래 명령을 실행해요. `DATABASE_URL`은 먼저 데모 DB로 설정해요.

```sh
PYTHONPATH=apps/api python -m db.seeds.demo --refresh-note-requests
```

이 옵션은 가상 요청 22개와 각 요청의 최초 보호자 메시지 `created_at`을 함께 바꿔요.
추가 대화는 그대로 둬요. 고정 fixture 20개는 가장 늦은 한국 날짜를
오늘로 옮기고 요청 사이 날짜 간격·접수 시각을 유지해요. 예를 들어 원본 11/20은 오늘,
11/19의 GR-11은 어제에 남아요. 고정 날짜가 없는 하늘·노을 예시 두 개는 현재 시각으로 맞춰요.
원본 날짜별 시연에서는 옵션 없이 시드해요. 다른 요청·계정·본문은 바꾸지 않아요.
옵션 실행 뒤 오늘 날짜로 새 초안을 만들고 확인해요.
이미 만든 입력에는 다시 반영하지 않으니 기존 초안이 없는 날짜·데모 DB에서 시작해요.

0003부터 선생님이 받은 마지막 AI 초안은 `daily_notes.ai_original`에 보존해요. 교사 수정·확인·발송으로는 바꾸지 않고 미수정 초안을 재생성할 때 갱신해요. 기존 행은 적용 시점의 내용으로 채워요.
수정·확인·발송·초안 저장은 `events.daily_note_id`로 아이별 이력을 남겨요.
지금 발송은 `note_sent` 알림을
`pending`으로 저장하고 `deliver_after`를 계산해요. 워커가 보낼 시각 이후 sent로 바꿔요.

`POST /daily-notes/drafts/{input_id}/regenerate`는 저장 입력으로 draft·needs_check만 다시 만들어요.
ready와 교사 수정본(content ≠ ai_original 또는 daily_note_edited 이력)은 그대로 두고, sent가 하나라도 있으면 409예요.
응답은 RegenerateResponse로 kept_edited(접수 시 보존한 미확인 수정본 수)를 더해요. 다른 초안 API 응답은 그대로예요.
failed와 시간 제한을 넘긴 queued·running은 재접수해요. 제한 안의 queued·running은 현재 상태를 돌려주며 작성기를 다시 부르지 않아요.
worker의 멈춘 실행 복구는 작성기 제한 시간에 60초를 더해 판단해요.
DB는 입력 행의 PostgreSQL xmin을 실행 판으로 써서 이전 작업의 늦은 성공·실패를 버려요.
새 초안은 기존 알림장 ID를 보존하고 content와 ai_original을 함께 바꿔요. 실행 중 교사 수정·확인도 저장 직전에 다시 검사해요.
반 묶음 카드 draft.draft_started_at은 접수·실행 시각, draft.regenerated_by와 새 drafted 이력 detail.regenerated_by는 재생성 요청자예요.
내용이 실제로 바뀔 때만 daily_note_edited를 남겨요. 확인 취소는 기존 returned로 ready→draft, 검사 해소는 checked로 needs_check→draft를 남겨요.
`GET /memories?kind=tone`은 담임 본인의 기억만 읽어요. DELETE /memories/{id}는 deleted_at을 채우고 본문·structured를 비워요.
기억 AI의 말투 추출·규칙 생성은 이번 백엔드에 없으며, 말투 예시는 시드하지 않아요.

알려진 한계:

- worker·Beat는 `RUN_IN=worker`일 때만 DB 주기 작업을 해요. API 안 실행 모드의 기존 알림 조회는 유지하지만 예약 발송은 worker 모드로 켜야 해요.
- 두 큐는 같은 worker의 스레드 수를 나눠 써요. 모든 스레드가 긴 작업에 차면 다른 작업이 늦어질 수 있어요. 전용 worker·복제본·작성 중 heartbeat는 별도 설계가 필요해요.

- 시간 초과는 대기·결과 저장만 끝내요. 실행 중인 writer 스레드는 멈추지 않아서 모델 호출이 계속될 수 있어요. 호출별 제한·취소는 writer 쪽에서 처리해야 해요.
- 알림장이 0개인 반을 보내면 `sent_count=0`이고 묶음 카드는 `pending`으로 남아요.
- 같은 날 반을 옮긴 아이는 `(child_id, note_date)` 중복으로 묶음 전체가 실패할 수 있어요. 발송 차단의 `open_checks`에서 DB는 `request_id: null`을 포함하고 mock은 키를 생략할 수 있어요.
- 0003 이전 알림장의 ai_original은 적용 시점 content로 채워요. 이미 보낸 행의 최종본과 실제 AI 원본을 구분할 수 없어 학습 자료로 쓸 때 제외·검토가 필요해요.
- events의 알림장 FK는 자동 삭제하지 않아요. 시연 초기화에서 알림장을 지우려면 해당 이력을 먼저 지워야 해요. 현재 삭제 API는 없어요.
- 모의 반 묶음 카드 타임라인은 card_id로 이력을 모으므로 아이별 daily_note_sent는 표시되지 않아요. 보호자 알림은 생성돼요.

### 투약·귀가 시연 — 팀 확인 전 초안

[제안] 학부모가 POST /requests에 유형 medication·pickup과 원문을 보내요. FR-16·AC-09에 맞춰 미등록 인계자·투약 누락을 표시해요.
등록 인계자는 pickup_guardian_id, 미등록이면 pickup_name·pickup_relation을 보내요. 각 문자열은 100자 이하예요.
이름만 있거나 기존 원문만 있는 귀가도 받아요. 상세 care와 교직원 목록의 unregistered_pickup=true로 경고해요.
투약 medication_name·medication_dose·medication_time이 없거나 공백이면 missing_fields에 표시해요.
AI로 원문을 해석해 채우지 않아요. 누락은 422로 막지 않고 교직원이 확인해요.
GET /children/{id}/pickup-guardians는 현재 활성 등록 인계자를 보여요.
GET /care-requests는 교직원 목록이며 version·unregistered_pickup·missing_fields를 포함해요.
sort는 다른 목록과 같은 created_at·updated_at 오름/내림차순이에요.
POST /requests/{id}/care-decisions에 decision=confirm·complete, 교직원이 본 care.version(필수)을 보내요.
등록 인계자면 같은 UUID를 다시 보내고, 미등록이면 생략해요. 미등록 confirm은 별도 확인 이력과 원장 알림 1건을 남겨요.
확인 당시 인계자를 보존하므로 이후 비활성·연결 해제가 complete를 막지 않아요.
version은 최초 1·보호자 추가 글마다 +1이에요. 확인 뒤 정정·취소 글이 오면 received·confirmed_at=null로 돌아가요.
담당자에게 알리고 교직원이 새 대화 전체를 읽고 다시 확인해요. 옛 판 결정은 CARD_VERSION_CONFLICT예요.
원문·구조화 입력은 보존하고 자동 취소하지 않아요. 새 글·결정은 요청 잠금 안에서 이력·알림과 함께 저장해요.
귀가 알림은 근무 밖·주말에도 즉시이며 실패 재시도도 미루지 않아요. 투약 교직원 알림은 기존 근무 시간을 따라요.
알림장 medication·pickup 줄의 읽기 전용 request_status는 현재 상태예요. 원문·AI 원본은 바꾸지 않아요.
목록은 한 연결에서 출처 요청 상태를 한 번에 읽어요. T46은 새 DDL을 더하지 않아요. 현재 head 0010의 새 표·칸은 T54예요.
팀 확인 전 초안의 상세 필드·오류·결정은 T13 3.27·T10 v0.17을 따라요.

## [제안] v0.7 피드·앨범

API 38~49는 [T13 3.29](../../Docs/Step2/API_설계_문서.md)의 칸·사진 권한을 써요.
MEDIA_DIR은 파일 저장 폴더이며 직접 실행 기본값은 var/media예요. Compose API는 기본 /media에 전용 볼륨을 붙여요.
mock은 MEDIA_DIR/mock만 쓰고 초기화 때 그 폴더만 비워요. DB 파일은 그대로 둬요.
칸 권한을 몸통보다 먼저 검사하고 전체 업로드는 51MiB까지예요(넘으면 413). 파일 10개·일반 필드 2개까지 받아요.
가상 jpeg·png·webp만 첫 바이트로 검사하고 5MiB까지 받아요. 공개 정적 주소 없이 인증 파일 API만 써요.
글 생성은 multipart의 body·files·child_ids(JSON 배열 문자열)예요. 본문만 보낼 수도 있어요.
반 칸은 그 반 보호자만 쓰고, 교직원은 403과 권한 거부 이력이에요. 원 칸은 같은 기관 모두 써요.
사진 공개 범위는 기본 family이고 읽을 때 현재 값을 적용해요. 숨긴·지운 글은 파일도 404예요.
데모는 같은 UUID로 반 글 2개·원 글 2개·단색 PNG 5장과 family·class·org 예시를 넣어요.
T50이 붙기 전에는 올린 사람이 아이를 직접 표시해요. 팀 확인·화면 연결은 후속이에요.
