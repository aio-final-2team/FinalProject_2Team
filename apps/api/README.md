# apps/api

FastAPI 애플리케이션입니다. 태웅 담당의 인증·요청·상담·카드·이력 API를 구현합니다.

`DATA_BACKEND` 기본값은 `mock`이에요. `db`는 PostgreSQL의 계정과 관계를 읽어요.
DB 주소는 `DATABASE_URL`로 받아요. 마이그레이션·시드는 별도로 실행해요.
DB 모드는 `JWT_SECRET`에 32바이트 이상의 별도 키가 필요해요. 값이 없거나 mock 기본값·
`.env.example`의 예시 값이면 기동을 중단해요. mock의 개발용 기본값은 그대로 쓸 수 있어요.

| 범위 | mock | db |
| --- | --- | --- |
| 로그인·내 정보(API 1·2) | 구현 | argon2·JWT·token_version 구현 |
| 기관·반 배정 기간·카드 재배정·보호자 관계 | 구현 | 범위 함수와 404 거부 이력 구현 |
| 알림장·반 아이 목록(API 22~26·30) | 구현 | 초안·조회·수정·확인·반 전체 발송과 보호자 알림 행 구현 |
| 요청·카드·상담·자료·알림 등 나머지 API | 구현 | 다음 항목에서 차례로 연결해요 |

아직 연결하지 않은 DB API는 인증·역할·상세 경로의 범위를 검사한 뒤 공통 오류
`501 NOT_IMPLEMENTED`로 답해요. 역할이 다르면 403, 범위 밖이면 404예요.
범위 거부는 별도 트랜잭션으로 기록해 404 응답 뒤에도 `permission_denied` 이력이 남아요.
카드 결정의 세부 역할 검사는 범위 함수에 있고, DB 결정 API를 연결할 때 함께 써요.

인증·알림장 HTTP 시험은 mock·DB 두 모드로 돌아요. `tools/test_db.sh`가 전용 임시 DB에서
마이그레이션·기관 경계·범위·인증·알림장 시험을 실행하고 컨테이너를 지워요.

DB 초안은 입력을 `queued`로 저장하고 같은 프로세스의 BackgroundTasks에서 실행해요.
`running`을 거쳐 `succeeded` 또는 `failed`가 돼요. `DAILY_NOTE_WRITER`는
`모듈:함수` 형식이고 기본값은 `app.modules.daily_notes.stub_writer:write`예요.
`DAILY_NOTE_WRITER=graph`로 고르면 영민님 그래프의 `draft_daily_notes(payload)`를 불러요.
이 설정은 DB 초안 runner에 적용돼요. mock은 기존 대역 동작을 유지해요.
그래프는 `OPENAI_API_KEY`와 `LLM_MODEL_DOCUMENT`·`LLM_MODEL_CHECKER`를 읽어요.
역할별 모델 값이 비면 `LLM_MODEL_DEFAULT`를 써요. 값은 `.env.example`을 참고해요.
입구는 T13 3.19의 입력을 받아 아이별 `child_id`·`content`·`open_checks` 목록을 돌려줘요.
아이 결과가 빠지거나 형식이 잘못되면 그 아이만 `draft_failed`로 저장해요.
입구 전체가 실패하면 아이별 저장 없이 작업을 `failed`로 남겨요.
입력은 UUID 문자열·ISO 날짜만 써서 JSON으로 바로 주고받을 수 있어요.
확인 항목의 `c1` 같은 내부 ID는 DB 저장 때 새 UUID로 바꾸고, 없는 `request_id`는 null로 남겨요.
수정·확인 요청의 `resolved_checks`에는 조회 응답의 ID를 보내요.
그래프 연결 시험은 가짜 writer·checker를 주입하며 실제 모델은 부르지 않아요.

지금은 **API 프로세스 하나**로 실행해요. 여러 worker나 API 복제본을 함께 띄우면 안 돼요.
앱 시작 때 남은 `running`을 `queued`로 되돌리고 모든 `queued` 입력을 다시 실행해요.
기동을 기다리는 동안 초안을 전부 만들지는 않아요. 복구 작업도 뒤에서 차례로 실행해요.
writer는 `DAILY_NOTE_WRITER_TIMEOUT`초(기본 120초) 안에 답해야 해요.
시간이 지나면 기존 `failed`·`UPSTREAM_UNAVAILABLE` 경로로 끝내고 늦은 결과는 저장하지 않아요.
writer 스레드를 강제 종료하지는 않으므로 외부 호출 자체의 시간 제한도 writer에서 설정해야 해요.

오늘 날짜로 보호자 요청 누락을 시연하려면 전용 데모 DB에 마이그레이션을 적용한 뒤
저장소 루트에서 아래 명령을 실행해요. `DATABASE_URL`은 먼저 데모 DB로 설정해요.

```sh
PYTHONPATH=apps/api python -m db.seeds.demo --refresh-note-requests
```

이 옵션은 가상 요청 22개의 `created_at`만 현재 시각으로 맞춰요. 고정 날짜가 필요한 시험이나
원본 날짜별 시연에서는 옵션 없이 시드해요. GR-11도 옵션을 쓰면 오늘 접수된 요청이 돼요.
다른 요청·계정·본문은 바꾸지 않아요. 옵션 실행 뒤 오늘 날짜로 새 초안을 만들고 확인해요.
이미 만든 입력에는 다시 반영하지 않으니 기존 초안이 없는 날짜·데모 DB에서 시작해요.

알림장 상태 이벤트는 연결 열이 생기는 0003에서 더해요. 지금 발송은 `note_sent` 알림을
`pending`으로 저장하고 `deliver_after`를 계산해요. 알림 발송기는 다음 워커 항목에서 연결해요.

알려진 한계:

- 알림장이 0개인 반을 보내면 `sent_count=0`이고 묶음 카드는 `pending`으로 남아요.
- 같은 날 반을 옮긴 아이는 `(child_id, note_date)` 중복으로 묶음 전체가 실패할 수 있어요. 발송 차단의 `open_checks`에서 DB는 `request_id: null`을 포함하고 mock은 키를 생략할 수 있어요.
