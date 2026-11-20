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
입구는 T13 3.19의 입력을 받아 아이별 `child_id`·`content`·`open_checks` 목록을 돌려줘요.
아이 결과가 빠지거나 형식이 잘못되면 그 아이만 `draft_failed`로 저장해요.
입구 전체가 실패하면 아이별 저장 없이 작업을 `failed`로 남겨요.

알림장 상태 이벤트는 연결 열이 생기는 0003에서 더해요. 지금 발송은 `note_sent` 알림을
`pending`으로 저장하고 `deliver_after`를 계산해요. 알림 발송기는 다음 워커 항목에서 연결해요.
기본 백그라운드 작업은 프로세스 재시작 때 복구하지 않아요. 워커 전환 전 시연용 실행 방식이에요.
