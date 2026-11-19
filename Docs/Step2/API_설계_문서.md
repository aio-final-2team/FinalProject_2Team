# 유치온 API 설계 문서 (T13)

문서 버전 v0.3 | 작성 상태: 모의 API 대조·11/18 피드백 2·3·4번 반영, 시험 기록 연결

| 항목 | 내용 |
| --- | --- |
| 작업 | T13 API 설계 문서(FastAPI·Function Calling 도구 계약)·모의 API (#170) |
| 작성 | 태웅 · 검토 인혜 |
| 기준 문서 | 기획서 1117판 3장 FR-01~FR-13 · T04 흐름·권한 명세(PR #234) · [입출력 계약표](입출력_계약표_초안.md) v0.8(T10 회의 11/18 합의 v0.7 + 이 문서 3.7의 화면용 칸) · [DB 스키마 설계서](DB_스키마_설계서.md) v0.7 |
| 따른 가이드 | 강사님 'API 설계 문서 작성법' 11/18 수정본. 1~6장이 가이드의 '문서에 들어가는 여섯 가지' 순서다 |

이 문서는 T10 계약표에서 합의한 필드·권한·오류를 엔드포인트와 도구 단위로 펼친 것이다. 계약표와 이 문서가 다르면 계약표를 먼저 고치고 두 문서의 판을 같이 올린다. 구현이 시작되면 FastAPI의 `/docs`와 대조해 판을 올린다(계약표 1.1 규칙 1). 이 판(v0.3)은 API 29개 전부의 상세 명세, 화면이 쓰는 조회 응답 칸(3.7), 도구 전체의 실패 처리, 업무 흐름(5.7), 실행 규칙과 대표 사례 대조(6.7)를 담는다. 모의 API와 생성물 `contracts/openapi.yaml`을 붙였으며, 쓰는 법과 데모 계정은 [모의 API 안내](../../contracts/mock_api/README.md)에 있다.

**목차.** 1. 공통 정보와 인증 · 2. API 목록 · 3. 엔드포인트 상세 명세 · 4. 검증과 권한 규칙 · 5. Tool 정의와 호출 흐름 · 6. 실행 규칙 · 7. API 필드와 DB 컬럼 대응 · 8. 설정값 · 부록 A. 예시 ID · 변경 이력

**가이드 최종 제출 전 체크리스트와 이 문서**

| 체크리스트(가이드 33쪽) | 이 문서 |
| --- | --- |
| 구현할 API가 모두 목록 표에 있고 요구사항 ID와 연결된다 | 2장(29개, 요구사항 열) |
| 서버 주소·인증·오류 형식·/docs·변경 이력이 있다 | 1장, 끝의 변경 이력 |
| 구현할 API마다 상세 명세와 필드 명세 표가 있다 | 3장(29개 전부) |
| 형식 오류(422)와 권한·승인 오류(403)를 나눠 적었다 | 4.1 |
| 202를 쓰는 API는 작업 상태·결과·실패 조회가 있다 | 6.3 |
| Tool마다 성공·실패 출력과 실패 후 처리가 있다 | 5.2, 5.4, 5.7 |
| 타임아웃·재시도·중복 실행 방지 규칙이 있다 | 6.1, 6.2, 6.4, 6.7 |
| ID 형식이 같고, 필드와 DB 컬럼의 대응이 분명하다 | 1.5, 5.7, 6.7, 7장 |

## 1. 공통 정보와 인증

### 1.1 서버 주소와 자동 문서

| 항목 | 값 |
| --- | --- |
| 개발 서버 | `http://localhost:8000/api/v1` (`compose.yaml`의 `api` 서비스) |
| 배포 서버 | `https://<배포 도메인>/api/v1` (AWS EC2, T36 첫 배포 때 확정해 이 칸을 고침) |
| 자동 문서 | `http://localhost:8000/docs`, `http://localhost:8000/openapi.json`(버전 접두어 없이 앱 맨 위에 있음). 저장소에는 `/openapi.json`에서 뽑은 `contracts/openapi.yaml`을 생성물로 둔다 |
| 상태 확인 | `GET /health` (인증 없음, 버전 접두어 없음) |
| 모의 API | API 29개가 메모리 데모 데이터로 응답한다. 다시 켜면 초기화된다. 실행·계정·흐름은 [모의 API 안내](../../contracts/mock_api/README.md) 참고 |

### 1.2 인증

| 항목 | 내용 |
| --- | --- |
| 발급 | `POST /api/v1/auth/login`에 `login_id`·`password`를 보내면 서버가 JWT access token을 발급한다. 수명 12시간. Supabase Auth는 쓰지 않는다(DB 설계서 5.1·5.2) |
| 전달 | `Authorization: Bearer <access_token>`. 쿠키는 쓰지 않는다(Android 앱과 웹이 같은 API를 씀) |
| 검증 | 서명(`JWT_SECRET`)·만료·토큰 판(`users.token_version`과 같은지)·계정 사용 여부(`users.is_active`)를 본 뒤, 역할·기관·반으로 권한을 검사한다(4장) |
| 오류 | 401 `UNAUTHENTICATED`: 토큰 없음·만료·서명 틀림·판이 낮음 / 403 `FORBIDDEN_ROLE`: 누구인지는 알지만 역할상 못 하는 일 / 404 `NOT_FOUND`: 다른 기관·다른 반 자료(있는지도 알리지 않음) |

토큰에는 `sub`(계정 ID), `org`(기관 ID), `role`(`parent`·`teacher`·`director`), `ver`(토큰 판), `iat`(발급 시각), `exp`(만료)만 넣는다. 반 소속과 아이 관계는 토큰에 넣지 않고 요청마다 DB에서 확인한다. 소속이 바뀌어도 토큰을 다시 받을 필요가 없게 하기 위해서다.

### 1.3 공통 헤더

| 헤더 | 방향 | 내용 |
| --- | --- | --- |
| `Authorization` | 요청 | `Bearer <access_token>`. 로그인·`/health`만 빼고 필수 |
| `X-Request-ID` | 요청·응답 | 화면이 요청마다 만들어 보낸다. 없으면 서버가 만든다. 응답 헤더로 같은 값을 돌려주고, 오류의 `trace_id`·도구 호출·이력(`events.detail.trace_id`)에 같은 값을 남긴다 |
| `Content-Type` | 요청 | `application/json`. 자료 올리기만 `multipart/form-data` |

가이드 예시의 `request_id`(추적 ID)를 이 서비스에서는 `trace_id`라고 부른다. 이 서비스에서 `request_id`는 학부모 요청(`requests.id`)을 뜻하기 때문이다(계약표 1.1 규칙 6).

### 1.4 공통 오류 형식

모든 API가 같은 형식으로 오류를 돌려준다. 200에 오류를 담아 보내지 않는다.

```json
{
  "error": {
    "code": "CARD_VERSION_CONFLICT",
    "message": "다른 사람이 먼저 카드를 처리했어요. 새로고침해 주세요.",
    "trace_id": "6b0f1c2e-9a7d-4c1e-8f3a-2d5b7e9c1a40",
    "details": { "current_version": 3 }
  }
}
```

| HTTP | `code` | 언제 | 누가 검사 |
| --- | --- | --- | --- |
| 401 | `UNAUTHENTICATED` | 토큰 없음·만료·무효 | 인증 의존성 |
| 403 | `FORBIDDEN_ROLE` | 역할상 못 하는 일(학부모가 카드 결정, 담임이 원장 보고 카드 결정) | 서버 권한 검사 |
| 404 | `NOT_FOUND` | 없거나, 다른 기관·다른 반·남의 자료 | 서버 범위 검사 |
| 409 | `CARD_VERSION_CONFLICT` | 화면이 본 카드 판이 지금 판과 다름(`details.current_version`) | 서버 |
| 409 | `ALREADY_DECIDED` | 같은 카드 판에 이미 결정이 있음 | 서버 + DB 유니크 |
| 409 | `INVALID_TRANSITION` | T04 전이 규칙에 없는 상태 변경(예: 회신 전 처리 완료, 보류 아닌 카드 재개) | 서버 |
| 409 | `REASON_REQUIRED` | 학부모 미확인 민원을 이유 없이 처리 완료(계약표 6장 ⑦) | 서버 + DB 트리거 |
| 409 | `SLOT_TAKEN` | 같은 상담실·담임의 겹치는 시간이 이미 확정됨 | DB 배제 제약 |
| 409 | `SLOT_NOT_CHOSEN` | 학부모가 체크하지 않은 후보로 확정 | 서버 |
| 409 | `NOTE_BATCH_BLOCKED` | 반에 아직 확인 안 된 알림장이 있음(`details.blocked[]`) | 서버 |
| 422 | `VALIDATION_FAILED` | 입력 형식·허용 값·길이·함께 와야 하는 칸이 어긋남(`details.fields[]`) | Pydantic |
| 500 | `INTERNAL_ERROR` | 서버 내부 오류. 내부 내용은 응답에 넣지 않고 로그에만 남김 | — |
| 503 | `UPSTREAM_UNAVAILABLE` | 모델·외부 API 장애. 요청은 저장되고 나중에 다시 처리 | 서버 |

400은 쓰지 않는다. 필수 정보가 빠진 요청은 오류가 아니라 요청 상태 `needs_info`로 정상 응답에 담는다(계약표 1.1 규칙 4). FastAPI 기본 422 응답은 예외 처리기에서 위 형식으로 바꿔 돌려준다. `message`는 서버의 기본 한국어 문장이고, 화면에 띄울 문구는 화면이 `code`별로 정한다(계약표 1.1 규칙 9).

### 1.5 공통 규칙

| 항목 | 규칙 |
| --- | --- |
| 경로 | 모두 `/api/v1`로 시작. 자원은 복수 명사, 실행은 하위 경로 `POST`(예: `/cards/{card_id}/decisions`). 소문자와 하이픈만 |
| 목록 | `?page=1&size=20&sort=-created_at` → `{ "items": [...], "total": 37, "page": 1, "size": 20 }`. `size` 기본 20·최대 100 |
| 시각 | ISO 8601, 한국 시간 오프셋 포함(`2026-12-01T15:00:00+09:00`). 날짜만이면 `YYYY-MM-DD` |
| ID | DB 설계서 2.0 ID 형식 표와 같다. 기관·반·계정·아이·요청·카드·문서·상담실·상담 예약·자동 규칙·원에 남은 답·알림장은 UUID 문자열, 대화 메시지·문서 조각·결정 기록·이력·상담 후보(`slot_id`)·알림은 정수 |
| 시간 구간 | DB의 `tstzrange`는 API에서 `{ "start": "...", "end": "..." }`로 주고받는다 |
| 성공 코드 | 조회 200 · AI 처리 접수 202 · 그 밖의 생성 201 · 결정·확정 같은 실행 200 · 삭제 204(MVP에 없음) |

## 2. API 목록

인증 열의 '자기 것'·'우리 반'은 4.2의 범위 규칙을 뜻한다. 상세 열은 29개 API의 3장 절 번호를 가리킨다.

| # | 메서드 | 경로 | 인증·역할 | 설명 | 성공 | 요구사항 | 상세 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | POST | `/api/v1/auth/login` | 없음 | 로그인, 토큰 발급 | 200 | FR-01 | 3.8 |
| 2 | GET | `/api/v1/me` | JWT | 내 정보·내 아이(학부모)·담당 반(교직원) | 200 | FR-01 | 3.8 |
| 3 | POST | `/api/v1/requests` | 학부모 | 요청 만들기(AI 처리 접수) | 202 | FR-02, FR-03 | 3.1 |
| 4 | GET | `/api/v1/requests` | 학부모(자기 것) | 내 요청 목록 | 200 | FR-02 | 3.9 |
| 5 | GET | `/api/v1/requests/{request_id}` | 학부모(자기 것) · 교직원(우리 반) | 요청 상세·대화·진행 기록 | 200 | FR-02, FR-11 | 3.2, 3.7 |
| 6 | GET | `/api/v1/requests/{request_id}/stream` | 학부모(자기 것) | AI 진행 스트림(SSE) | 200 | NFR-10 | 3.2 |
| 7 | POST | `/api/v1/requests/{request_id}/messages` | 학부모(자기 것) | 대화 이어 쓰기 | 201 | FR-02 | 3.10 |
| 8 | POST | `/api/v1/requests/{request_id}/slot-choices` | 학부모(자기 것) | 상담 가능 시간 체크 | 200 | FR-05 | 3.4 |
| 9 | POST | `/api/v1/requests/{request_id}/confirm` | 학부모(자기 민원) | 민원 회신 '확인했어요' | 200 | FR-07 | 3.5 |
| 10 | GET | `/api/v1/notifications` | JWT(자기 것) | 알림 목록 | 200 | FR-12 | 3.11 |
| 11 | POST | `/api/v1/notifications/{notification_id}/read` | JWT(자기 것) | 알림 읽음 | 200 | FR-12 | 3.11 |
| 12 | GET | `/api/v1/cards` | 담임·원장 | 받은함(필터 6개·종류 필터·필터별 건수) | 200 | FR-09 | 3.12, 3.7 |
| 13 | GET | `/api/v1/cards/{card_id}` | 담임(우리 반)·원장 | 카드 상세(초안·근거·반복 수·이력) | 200 | FR-04, FR-07, FR-09, FR-11 | 3.13, 3.7 |
| 14 | GET | `/api/v1/cards/{card_id}/stream` | 담임(우리 반)·원장 | 카드 AI 진행 스트림(초안 글자 포함) | 200 | NFR-10 | 3.13 |
| 15 | POST | `/api/v1/cards/{card_id}/decisions` | 담임(우리 반)·원장 | 카드 결정(승인·거절·보류·재개·반려·처리 완료·원장님께 올리기) | 200 | FR-05~FR-09 | 3.3 |
| 16 | POST | `/api/v1/cards/{card_id}/reclassify` | 담임(우리 반)·원장 | 민원 위험 등급 다시 분류 | 200 | FR-03, FR-07 | 3.14 |
| 17 | POST | `/api/v1/cards/{card_id}/bookings` | 담임(우리 반) | 상담 확정 | 200 | FR-05 | 3.4 |
| 18 | POST | `/api/v1/cards/{card_id}/instructions` | 원장·원감 | 원장 보고 지시 | 200 | FR-07 | 3.15 |
| 19 | POST | `/api/v1/cards/{card_id}/reassign` | 원장·원감 | 담당 재배정 | 200 | FR-09, FR-19 | 3.16 |
| 20 | POST | `/api/v1/memory-rules/{rule_id}/decision` | 규칙 주인 | 개인 규칙 제안 켜기·거절 | 200 | FR-06 | 3.17 |
| 21 | GET | `/api/v1/overview` | 원장·원감 | 원장 현황(미배정·대기·지연·완료·학부모 미확인 완료) | 200 | FR-09, FR-19 | 3.18 |
| 22 | POST | `/api/v1/daily-notes/drafts` | 담임 | 알림장 초안 만들기(AI 처리 접수) | 202 | FR-10 | 3.19 |
| 23 | GET | `/api/v1/daily-notes/drafts/{input_id}` | 담임(우리 반) | 알림장 초안 진행 상태 | 200 | FR-10 | 3.19 |
| 24 | GET | `/api/v1/daily-notes` | 학부모(내 아이, 보낸 것) · 담임(우리 반) | 알림장 보기 | 200 | FR-10 | 3.20, 3.7 |
| 25 | PATCH | `/api/v1/daily-notes/{note_id}` | 담임(우리 반) | 알림장 고치기·확인 | 200 | FR-10 | 3.21 |
| 26 | POST | `/api/v1/daily-notes/send` | 담임(우리 반) | 반 알림장 한 번에 보내기 | 200 | FR-10 | 3.6 |
| 27 | POST | `/api/v1/documents` | 원장·담임 | 자료 올리기(적재 접수) | 202 | FR-13 | 3.22 |
| 28 | GET | `/api/v1/documents` | 교직원 | 자료 목록 | 200 | FR-13 | 3.23 |
| 29 | GET | `/api/v1/documents/{document_id}` | 교직원 | 자료 상세·적재 상태 | 200 | FR-13 | 3.23 |

SSE 두 개(6·14)는 실시간 진행 화면(NFR-10)이 쓰므로 넣었다. 투약·귀가(T46)와 최종 기능(FR-14 이후)은 그 작업에서 이 표에 더한다.

## 3. 엔드포인트 상세 명세

API 29개를 가이드의 여덟 칸으로 쓴다(계약표 1.1 규칙 8). 고정 예시 ID는 부록 A의 데모 ID다. 필드 표의 '빈값'은 `""`이나 `null`을 받아도 되는지다. 3.8 이후 예시는 주요 응답 필드와 목록 첫 항목만 줄여 보인다. 토큰과 새로 발급한 ID는 `…`로 줄이고, 경로의 `{card_id}`·`{input_id}`·`{note_id}`는 앞선 응답에서 받은 값을 쓴다.

### 3.1 요청 만들기 — `POST /api/v1/requests`

| 칸 | 내용 |
| --- | --- |
| ① 호출 목적 | 학부모가 안내 문의·상담·민원을 보낸다. 서버는 요청을 저장하고 바로 202를 돌려준 뒤, 감독 AI 분류부터 카드 생성까지를 뒤에서 처리한다(FR-02, FR-03) |
| ② 요청 헤더 | `Authorization`(필수), `X-Request-ID`(권장), `Content-Type: application/json` |
| ③ 경로·쿼리 | 없음 |
| ④ 요청 본문 | 아래 필드 표 |
| ⑤ 검증·권한 | 형식은 Pydantic(422). 역할이 학부모가 아니면 403. `child_id`가 내 아이(`child_guardians`)가 아니면 404. `previous_request_id`는 내 요청이고 끝난 상태(`completed`·`rejected`)여야 하며, 아니면 404 또는 409 `INVALID_TRANSITION` |
| ⑥ 정상 응답 | 202 + 요청 ID·상태·스트림 주소. 같은 `client_request_id`로 다시 보내면 200 + 처음 만든 요청 |
| ⑦ 오류 응답 | 아래 오류 표 |
| ⑧ 실행 규칙 | 저장만 하고 바로 답한다(10초 안). 중복 제출은 `(requester_id, client_request_id)` DB 유니크로 막는다. AI 처리가 실패해도 요청은 남고, 재시도 뒤에도 실패하면 사람 카드로 넘긴다(6.3) |

**요청 본문 필드**

| 필드 | 위치 | 타입 | 필수 | 빈값 | 제약 | 설명 |
| --- | --- | --- | --- | --- | --- | --- |
| `client_request_id` | 본문 | string | 필수 | 불가 | 8~64자, 화면이 만든 UUID 권장 | 같은 제출을 두 번 받지 않기 위한 키 |
| `type` | 본문 | string | 필수 | 불가 | `inquiry`·`consultation`·`complaint` | 요청 유형. `medication`·`pickup`은 T46에서 연다 |
| `body` | 본문 | string | 필수 | 불가 | 1~2,000자 | 질문·요청 내용 |
| `child_id` | 본문 | string(UUID) | 필수 | 불가 | 내 아이 | 대상 아이. 반은 서버가 아이에서 정한다 |
| `previous_request_id` | 본문 | string(UUID) | 선택 | `null` 가능 | 내 요청, 끝난 상태 | 끝난 요청을 다시 열 때 이전 요청(T04 2.1) |

```http
POST /api/v1/requests
Authorization: Bearer <JWT>
X-Request-ID: 6b0f1c2e-9a7d-4c1e-8f3a-2d5b7e9c1a40
Content-Type: application/json

{
  "client_request_id": "c1a7e0d2-5b3f-4e8a-9c61-0f2d4b6a8e10",
  "type": "complaint",
  "body": "등원 버스가 이번 주에만 세 번 20분씩 늦었어요.",
  "child_id": "00000000-0000-4000-8000-000000000501",
  "previous_request_id": null
}
```

```http
HTTP/1.1 202 Accepted
X-Request-ID: 6b0f1c2e-9a7d-4c1e-8f3a-2d5b7e9c1a40

{
  "request": {
    "id": "00000000-0000-4000-8000-000000000702",
    "status": "received",
    "stream_url": "/api/v1/requests/00000000-0000-4000-8000-000000000702/stream"
  }
}
```

**정상 응답 필드**

| 필드 | 타입 | 항상 | 설명 |
| --- | --- | --- | --- |
| `request.id` | string(UUID) | 예 | 요청 ID |
| `request.status` | string | 예 | 처음엔 `received`. 같은 키 재전송(200)이면 지금 상태 |
| `request.stream_url` | string | 예 | AI 진행 스트림 주소(3.2) |

**오류**

| HTTP | `code` | 조건 |
| --- | --- | --- |
| 401 | `UNAUTHENTICATED` | 토큰 문제 |
| 403 | `FORBIDDEN_ROLE` | 교직원이 호출 |
| 404 | `NOT_FOUND` | `child_id`가 내 아이가 아님, `previous_request_id`가 내 요청이 아님 |
| 409 | `INVALID_TRANSITION` | `previous_request_id`가 아직 끝나지 않은 요청 |
| 422 | `VALIDATION_FAILED` | 허용 밖 `type`, `body` 길이 초과, 필수 칸 없음 |

### 3.2 요청 상세·스트림 — `GET /api/v1/requests/{request_id}`, `GET …/stream`

| 칸 | 내용 |
| --- | --- |
| ① 호출 목적 | 학부모가 자기 요청의 상태·대화·진행 기록·상담 후보를 본다. 교직원도 카드 화면에서 같은 요청을 본다(FR-02, FR-11). 스트림은 AI 처리 단계를 실시간으로 보여 준다(NFR-10) |
| ② 요청 헤더 | `Authorization`(필수), `X-Request-ID`. 스트림은 `Accept: text/event-stream`, 토큰을 헤더로 보내야 해서 `EventSource` 대신 `fetch` 스트림으로 읽는다 |
| ③ 경로·쿼리 | `request_id`(경로, UUID, 필수) |
| ④ 요청 본문 | 없음 |
| ⑤ 검증·권한 | 학부모는 자기 요청만, 담임은 우리 반 요청(대체 담임은 기간 안)과 재배정받은 카드의 요청만, 원장은 원 전체. 범위 밖이면 404 |
| ⑥ 정상 응답 | 200. 학부모에게는 위험 등급·보류 이유·도구 호출·처리한 교직원을 넣지 않고, 처리 이력은 학부모용 요약만 준다(계약표 2.1, T04 7.1). 반려 이유와 답변 출처는 준다(3.7) |
| ⑦ 오류 응답 | 401, 404, 422(UUID 형식이 아님) |
| ⑧ 실행 규칙 | 조회라 재시도해도 된다. 스트림이 끊기면 상세를 다시 불러 상태를 맞춘 뒤 다시 연결한다 |

```json
{
  "request": {
    "id": "00000000-0000-4000-8000-000000000701",
    "type": "consultation",
    "title": "아이 친구 관계 상담",
    "status": "needs_info",
    "status_label": "시간을 골라 주세요",
    "missing_fields": [],
    "hold_until": null,
    "parent_confirmed_at": null,
    "created_at": "2026-12-01T09:10:00+09:00",
    "updated_at": "2026-12-01T09:10:20+09:00"
  },
  "messages": [
    { "id": 41, "sender_type": "user", "body": "아이 친구 관계로 상담하고 싶어요.", "created_at": "2026-12-01T09:10:00+09:00" }
  ],
  "timeline": [
    { "label": "접수됨", "at": "2026-12-01T09:10:00+09:00" },
    { "label": "시간을 골라 주세요", "at": "2026-12-01T09:10:20+09:00" }
  ],
  "consultation": {
    "slots": [
      { "id": 9001, "period": { "start": "2026-12-02T15:00:00+09:00", "end": "2026-12-02T15:30:00+09:00" }, "room": "상담실", "status": "proposed" },
      { "id": 9002, "period": { "start": "2026-12-02T16:00:00+09:00", "end": "2026-12-02T16:30:00+09:00" }, "room": "상담실", "status": "proposed" },
      { "id": 9003, "period": { "start": "2026-12-03T15:00:00+09:00", "end": "2026-12-03T15:30:00+09:00" }, "room": "상담실", "status": "proposed" }
    ],
    "booking": null
  }
}
```

| 필드 | 타입 | 항상 | 설명 |
| --- | --- | --- | --- |
| `request.status` | string | 예 | 기획서 6장 공통 상태 11개 중 하나 |
| `request.status_label` | string | 예 | T04 2장 표시 이름(학부모용·교직원용이 다름) |
| `request.missing_fields[]` | string[] | 예 | `needs_info`일 때 물어볼 항목. 없으면 빈 목록 |
| `request.hold_until` | date | 아니오 | 보류 예정일. 보류 이유는 학부모에게 주지 않음 |
| `request.parent_confirmed_at` | datetime | 아니오 | 민원 '확인했어요' 시각 |
| `messages[]` | 목록 | 예 | 대화. `sender_type`은 `user`(사람)·`agent`(AI)·`system` |
| `timeline[]` | 목록 | 예 | 학부모용은 상태가 바뀐 단계만 표시 이름으로 |
| `consultation` | 객체 | 아니오 | 상담 요청일 때만. 후보 최대 3개와 확정 예약 |

**스트림 이벤트**(계약표 3장): `stage`(`classifying`·`searching`·`drafting`·`checking`) · `done`(`request_status`) · `error`(1.4 형식). 학부모 스트림에는 답변 글자(`token`)와 카드(`card`)를 보내지 않는다. 담임 승인 전 초안이 학부모에게 나가지 않게 하기 위해서다.

```text
event: stage
data: {"stage": "classifying", "at": "2026-12-01T09:10:01+09:00"}

event: done
data: {"request_status": "needs_info"}
```

### 3.3 카드 결정 — `POST /api/v1/cards/{card_id}/decisions`

| 칸 | 내용 |
| --- | --- |
| ① 호출 목적 | 담임·원장이 받은함 카드에 결정을 내린다. AI가 만든 초안은 이 결정을 거쳐야만 학부모에게 나간다(FR-05~FR-09, NFR-03) |
| ② 요청 헤더 | `Authorization`(필수), `X-Request-ID`(권장), `Content-Type: application/json` |
| ③ 경로·쿼리 | `card_id`(경로, UUID, 필수) |
| ④ 요청 본문 | 아래 필드 표. 화면이 본 카드 `version`을 꼭 보낸다 |
| ⑤ 검증·권한 | 형식·함께 와야 하는 칸은 Pydantic(422). 역할·범위·카드 종류는 서버(403·404). 판·전이·학부모 확인은 서버(409) |
| ⑥ 정상 응답 | 200 + 바뀐 카드·요청 상태. 다음 카드가 생기면 `next_card_id` |
| ⑦ 오류 응답 | 아래 오류 표 |
| ⑧ 실행 규칙 | 같은 카드 판에 결정은 하나만 저장된다(`approvals (card_id, card_version)` 유니크). 응답이 끊기면 카드 상세로 상태를 확인한 뒤 다시 보낸다. 같은 판으로 다시 보내면 409 `ALREADY_DECIDED`라 두 번 처리되지 않는다 |

**요청 본문 필드**

| 필드 | 위치 | 타입 | 필수 | 빈값 | 제약 | 설명 |
| --- | --- | --- | --- | --- | --- | --- |
| `version` | 본문 | integer | 필수 | 불가 | 1 이상 | 화면이 본 카드 판 |
| `decision` | 본문 | string | 필수 | 불가 | `approve`·`edit_approve`·`reject`·`hold`·`resume`·`dismiss`·`complete`·`escalate` | 결정. 원장 지시(`instruct`)는 18번 API |
| `reason_code` | 본문 | string | `reject`·`dismiss`면 필수 | 불가 | 계약표 6장 ① 8개 | 거절·반려 이유 |
| `reason_text` | 본문 | string | `hold`·`reason_code = other`면 필수, `complete`인데 학부모 미확인이면 필수 | 불가 | 1~500자 | 보류 이유·기타 이유·마무리한 방법 |
| `hold_until` | 본문 | date | `hold`면 필수 | 불가 | 오늘 이후 | 보류 예정일 |
| `edited_content` | 본문 | object | `edit_approve`면 필수 | 불가 | 초안과 같은 모양 | 담임이 고친 내용 |

```http
POST /api/v1/cards/00000000-0000-4000-8000-000000000802/decisions
Authorization: Bearer <JWT>
X-Request-ID: 0e7d4a51-2c3b-4f6e-9a18-5b7c9d0e1f23

{
  "version": 2,
  "decision": "complete",
  "reason_text": "전화로 설명드리고 마무리함"
}
```

```json
{
  "card": { "id": "00000000-0000-4000-8000-000000000802", "status": "done", "version": 3 },
  "request": { "id": "00000000-0000-4000-8000-000000000702", "status": "completed" },
  "next_card_id": null
}
```

**결정마다 바뀌는 것**

| `decision` | 카드 | 요청 | 이력(`events.action`) | 알림 |
| --- | --- | --- | --- | --- |
| `approve`·`edit_approve` | `approved` → 발송 뒤 `done` | `approved` → `sent_or_booked` | `approved`, `sent` | 학부모 `sent_or_booked` |
| `reject` | `rejected`, 같은 요청에 새 초안 카드 | `awaiting_review` → `assigned`, 새 초안이 나오면 다시 `awaiting_review` | `rejected` | 없음(이유는 기억 AI 재료) |
| `hold` | `on_hold` + `hold_until` | `on_hold` | `held` | 학부모 `on_hold`(예정일만) |
| `resume` | `pending` | `on_hold` → `awaiting_review` | `resumed` | 없음 |
| `dismiss` | `rejected` | `rejected` | `dismissed` | 학부모 `rejected` |
| `complete` | `done` | `sent_or_booked` → `completed`(민원만) | `completed` | 학부모 `completed` |
| `escalate` | 원장 보고 카드(`director_report`)가 새로 생김 | `escalated` | `escalated` | 원장 `director_report` |

**오류**

| HTTP | `code` | 조건 |
| --- | --- | --- |
| 403 | `FORBIDDEN_ROLE` | 학부모가 호출, 담임이 원장 보고 카드에 결정 |
| 404 | `NOT_FOUND` | 다른 기관·다른 반 카드 |
| 409 | `CARD_VERSION_CONFLICT` | `version`이 지금 판과 다름(`details.current_version`) |
| 409 | `ALREADY_DECIDED` | 같은 판에 이미 결정이 있음 |
| 409 | `INVALID_TRANSITION` | 민원이 아닌데 `complete`, 회신 전 `complete`, 보류가 아닌데 `resume` |
| 409 | `REASON_REQUIRED` | 학부모가 '확인했어요'를 안 눌렀는데 `reason_text` 없이 `complete` |
| 422 | `VALIDATION_FAILED` | 허용 밖 `decision`·`reason_code`, `reject`인데 `reason_code` 없음, `hold`인데 `hold_until` 없음 |

`REASON_REQUIRED`는 422가 아니라 409다. 요청의 학부모 확인 여부를 DB에서 봐야 알 수 있는 조건이라, 본문 형식만 보는 Pydantic 검사(422)와 섞지 않는다(가이드 19쪽).

### 3.4 상담 시간 체크·확정 — `POST …/requests/{request_id}/slot-choices`, `POST …/cards/{card_id}/bookings`

| 칸 | 내용 |
| --- | --- |
| ① 호출 목적 | 학부모가 후보 1~3개 중 가능한 시간을 체크하고(`slot-choices`), 담임이 그중 하나로 확정한다(`bookings`). 확정 전에는 예약이 아니다(FR-05, T04 합의 1) |
| ② 요청 헤더 | `Authorization`(필수), `X-Request-ID`(권장) |
| ③ 경로·쿼리 | `request_id` 또는 `card_id`(경로, UUID, 필수) |
| ④ 요청 본문 | 아래 필드 표 |
| ⑤ 검증·권한 | 체크는 요청한 학부모만, 확정은 그 반 담임만(원장은 대신 확정하지 않음). 범위 밖이면 404, 역할이 다르면 403 |
| ⑥ 정상 응답 | 체크: 200 + 후보 상태, 요청 `awaiting_review`. 확정: 200 + 예약 |
| ⑦ 오류 응답 | 아래 오류 표 |
| ⑧ 실행 규칙 | 체크한 시간은 24시간 잡아 둔다. 지나면 후보를 `proposed`로 돌리고 담임에게 `slot_hold_expired` 알림(계약표 6장 ⑥). 같은 상담실·담임의 겹치는 시간은 DB 배제 제약이 한 건만 받는다(DB 설계서 9.1 F1-7) |

**필드**

| 필드 | 위치 | 타입 | 필수 | 빈값 | 제약 | 설명 |
| --- | --- | --- | --- | --- | --- | --- |
| `slot_ids[]` | 체크 본문 | integer[] | `none_fit`이 아니면 필수 | 불가 | 1~3개, 그 요청의 지금 회차 후보 | 가능한 시간 |
| `none_fit` | 체크 본문 | boolean | 선택 | — | 기본 `false` | 맞는 시간이 없음 → 후보를 다시 계산 |
| `preferred_times` | 체크 본문 | string | `none_fit`이면 필수 | 불가 | 1~200자 | 원하는 시간 설명 |
| `version` | 확정 본문 | integer | 필수 | 불가 | 1 이상 | 상담 후보 카드 판 |
| `slot_id` | 확정 본문 | integer | 필수 | 불가 | 학부모가 체크한 후보 | 확정할 시간 |
| `booking.id` | 확정 응답 | string(UUID) | 항상 | 불가 | — | 예약 ID |
| `booking.room` | 확정 응답 | string | 항상 | 불가 | — | 상담실 이름 |
| `booking.period` | 확정 응답 | object | 항상 | 불가 | `start` < `end` | 상담 시간 |

```http
POST /api/v1/requests/00000000-0000-4000-8000-000000000701/slot-choices
{ "slot_ids": [9001, 9003] }

HTTP/1.1 200 OK
{ "slots": [ { "id": 9001, "status": "chosen_by_parent" }, { "id": 9003, "status": "chosen_by_parent" } ],
  "request": { "id": "00000000-0000-4000-8000-000000000701", "status": "awaiting_review" } }
```

```http
POST /api/v1/cards/00000000-0000-4000-8000-000000000801/bookings
{ "version": 1, "slot_id": 9001 }

HTTP/1.1 200 OK
{ "booking": { "id": "00000000-0000-4000-8000-000000000901", "room": "상담실",
               "period": { "start": "2026-12-02T15:00:00+09:00", "end": "2026-12-02T15:30:00+09:00" } },
  "request": { "id": "00000000-0000-4000-8000-000000000701", "status": "sent_or_booked" } }
```

**오류**

| HTTP | `code` | 조건 |
| --- | --- | --- |
| 403 | `FORBIDDEN_ROLE` | 교직원이 체크, 학부모·원장이 확정 |
| 404 | `NOT_FOUND` | 남의 요청, 다른 반 카드, 그 요청 후보가 아닌 `slot_id` |
| 409 | `INVALID_TRANSITION` | 시간을 고를 단계(`needs_info`)가 아닌데 체크 |
| 409 | `SLOT_NOT_CHOSEN` | 학부모가 체크하지 않은 후보로 확정 |
| 409 | `SLOT_TAKEN` | 그 사이 같은 상담실·담임 시간이 확정됨 → 담임 화면이 후보 다시 내기를 안내 |
| 409 | `CARD_VERSION_CONFLICT` | 확정할 때 카드 판이 다름 |
| 422 | `VALIDATION_FAILED` | `slot_ids` 0개·4개 이상, `none_fit`인데 `preferred_times` 없음 |

### 3.5 민원 '확인했어요' — `POST /api/v1/requests/{request_id}/confirm`

| 칸 | 내용 |
| --- | --- |
| ① 호출 목적 | 학부모가 민원 회신을 읽고 '확인했어요'를 누른다. 담임 받은함의 '확인 필요'로 올라가 담임이 처리 완료를 누를 차례가 된다(FR-07, T04 합의 2) |
| ② 요청 헤더 | `Authorization`(필수), `X-Request-ID`(권장) |
| ③ 경로·쿼리 | `request_id`(경로, UUID, 필수) |
| ④ 요청 본문 | 없음 |
| ⑤ 검증·권한 | 요청한 학부모만. 민원이 아니거나 회신 전(`sent_or_booked`가 아님)이면 409 |
| ⑥ 정상 응답 | 200 + `request { status, parent_confirmed_at }`. 상태는 `sent_or_booked` 그대로 |
| ⑦ 오류 응답 | 401, 403(교직원), 404(남의 요청), 409 `INVALID_TRANSITION`(민원 아님·회신 전) |
| ⑧ 실행 규칙 | 다시 눌러도 처음 시각을 유지하고 200을 돌려준다(멱등). 담임에게 `parent_confirmed` 알림을 한 번만 보낸다(`dedupe_key`) |

```json
{ "request": { "id": "00000000-0000-4000-8000-000000000702", "status": "sent_or_booked",
               "parent_confirmed_at": "2026-12-01T19:02:00+09:00" } }
```

### 3.6 알림장 보내기 — `POST /api/v1/daily-notes/send`

| 칸 | 내용 |
| --- | --- |
| ① 호출 목적 | 담임이 그날 반 알림장을 한 번에 보낸다. 아이 한 명이라도 확인이 안 끝났으면 아무것도 보내지 않는다(FR-10, T04 합의 6) |
| ② 요청 헤더 | `Authorization`(필수), `X-Request-ID`(권장), `Content-Type: application/json` |
| ③ 경로·쿼리 | 없음 |
| ④ 요청 본문 | `classroom_id`(UUID, 필수, 우리 반), `note_date`(date, 필수, 오늘 또는 지난날) |
| ⑤ 검증·권한 | 그 반 담임만(대체 담임은 기간 안). 원장은 보내지 않는다 |
| ⑥ 정상 응답 | 200 + `sent_count`. 아이마다 `daily_notes.status = sent`, 학부모에게 `note_sent` 알림 |
| ⑦ 오류 응답 | 403, 404, 409 `NOTE_BATCH_BLOCKED`(`details.blocked[] { note_id, child_id, open_checks[] }`), 422 |
| ⑧ 실행 규칙 | 한 트랜잭션에서 반 전체를 잠그고 확인한 뒤 보낸다. 이미 보낸 알림장은 다시 보내지 않고 `sent_count`에서 뺀다 |

```json
{ "error": { "code": "NOTE_BATCH_BLOCKED", "message": "확인이 안 끝난 알림장이 있어요.",
             "trace_id": "…", "details": { "blocked": [ { "note_id": "…", "child_id": "00000000-0000-4000-8000-000000000502",
             "open_checks": [ { "id": "c1", "item_key": "supplies", "problem": "준비물 날짜가 식단표와 달라요" } ] } ] } } }
```

### 3.7 화면이 쓰는 조회 응답 칸

T12 화면 지도(성주, PR #254)를 계약표 v0.7과 대조했을 때 화면에는 있는데 계약표에 없던 칸이다(#254 리뷰). 계약표 2장에도 같은 이름으로 더했다(계약표 v0.8). 모두 서버가 조회할 때 채우고, 새 DB 칸은 없다.

**로그인·내 정보** (`POST /auth/login`, `GET /me`)

| 필드 | 타입 | 누구 | 설명 | DB |
| --- | --- | --- | --- | --- |
| `user.classroom_ids[]` | string[](UUID) | 담임 | 오늘 볼 수 있는 반. 대체 담임은 기간 안인 반만. 원장·원감·학부모는 빈 목록 | `classroom_staff`(`valid_from`~`valid_to`) |
| `children[] { id, display_name, classroom_id }` | 목록 | 학부모 | 내 아이(이미 계약표에 있던 칸의 모양) | `child_guardians` → `children` |

**받은함 목록** (`GET /api/v1/cards`)

쿼리 파라미터. 화면의 종류 필터(전체·긴급·민원·상담·문의)는 카드 종류(`kind`)가 아니라 요청 유형으로 받는다. `kind`는 `reply_draft`·`director_report` 같은 카드 종류라 화면의 '종류'와 뜻이 다르기 때문이다.

| 파라미터 | 타입 | 필수 | 값 | 설명 |
| --- | --- | --- | --- | --- |
| `filter` | string | 선택 | `unassigned`·`needs_review`·`uncertain`·`on_hold`·`in_progress`·`done` | 받은함 필터 6개(T04 2.2). 없으면 끝나지 않은 카드 전부 |
| `request_type` | string | 선택 | `complaint`·`consultation`·`inquiry`·`all` | 종류 필터 '민원·상담·문의'. `all`이나 없으면 '전체' |
| `risk_level` | string | 선택 | `urgent` | 종류 필터 '긴급' |
| `kind` | string | 선택 | 카드 종류 6개 | 카드 종류로 거를 때(원장 보고만 보기 등) |
| `assignee` | string | 선택 | `me` | 내 담당만 |
| `page`·`size` | integer | 선택 | 기본 1·20, `size` 최대 100 | 목록 규칙(1.5) |

`counts {}`는 상태 필터 6개의 건수이고, `request_type`·`risk_level`을 준 경우 그 조건 안에서 센다. `type_counts { all, complaint, consultation, inquiry }`는 종류별 건수이고, `filter`를 준 경우 그 상태 필터 안에서 센다. 두 필터가 함께 걸리는 화면(T12 T-01)에서 칩마다 숫자를 붙일 수 있게 둘 다 준다. 필터와 건수는 서버가 계산한다.

| 더한 필드(`items[]`) | 타입 | 언제 | 설명 | DB |
| --- | --- | --- | --- | --- |
| `request_id` | string(UUID) | 요청이 있는 카드 | 알림장 묶음·규칙 제안 카드는 `null` | `cards.request_id` |
| `risk_category` | string | 긴급 민원만 | 긴급 사유 4가지(`child_safety`·`staff_attack`·`legal_external`·`privacy_leak`) | `requests.risk_category` |
| `repeat_count` | integer | 민원만 | 같은 반·최근 30일·같은 주제 민원 수. `topic_key = other`면 `null` | 조회 때 셈(`requests_repeat_idx`) |
| `check { passed, issue_count }` | 객체 | 검사가 끝난 카드 | 검사 AI 결과 요약. 검사를 못 했으면 `null` | `cards.check_result` |
| `parent_choice_count` | integer | 상담 후보 카드 | 학부모가 체크한 시간 수(지금 회차) | `consultation_slots`(`status = chosen_by_parent`) 개수 |
| `classroom { id, name }` | 객체 | 항상 | 반 이름. 원장 화면에서 반을 구분하려고 준다 | `requests.classroom_id` → `classrooms.name` |

**카드 상세** (`GET /api/v1/cards/{card_id}`)

| 더한 필드 | 타입 | 언제 | 설명 | DB |
| --- | --- | --- | --- | --- |
| `card.summary` | string | AI가 만든 카드 | AI 요약(`create_card`의 `summary`) | `cards.draft->>'summary'` |
| `evidence[].is_current` | boolean | 근거가 있을 때 | 근거 문서가 지금 판이면 참. 옛 판(`superseded`)·충돌 확인 대기(`conflict_pending`)·적용 기간이 지난 문서면 거짓 | `documents.status`·`effective_to` |
| `warnings[]` | string[] | 항상(없으면 빈 목록) | 화면 경고. `stale_evidence`(옛 판 근거가 있음) · `no_evidence`(근거 없음) · `law_unchecked`(법령 확인 못 함) · `check_unavailable`(검사 못 함) · `notify_failed`(교직원 알림을 못 만듦) | `evidence[].is_current`, 자료 AI 결과(`cards.draft`), `cards.check_result` |
| `parent_choices[] { slot_id, period, room, chosen_at, hold_expires_at }` | 목록 | 상담 후보 카드 | 학부모가 체크한 시간. `hold_expires_at` = `chosen_at` + 24시간(계약표 6장 ⑥) | `consultation_slots`(`chosen_by_parent`) |
| `rule { id, reason_code, rule_text, status }` | 객체 | `kind = rule_proposal` | 개인 규칙 제안 내용. 켜기·거절은 20번 API | `cards.subject_id` → `memory_rules` |
| `director_instruction { text, by, at }` | 객체 | 원장 지시가 있는 담임 카드 | 원장 지시 메모 | 같은 요청의 원장 보고 카드에 남은 `approvals`(`decision = instruct`)의 `reason_text`·`decided_by`·`created_at` |

**요청 상세(학부모)** (`GET /api/v1/requests/{request_id}`, 3.2에 더함)

| 더한 필드 | 타입 | 언제 | 설명 | DB |
| --- | --- | --- | --- | --- |
| `consultation.slots[] { id, period, room, status }` | 목록 | 상담 요청 | 후보 시각과 장소(3.2에 이미 있음). 방식(대면·화상)은 MVP가 상담실 대면 하나라 칸을 두지 않고, 화상상담(FR-18, 최종)에서 `mode`를 더한다 | `consultation_slots`, `rooms.name` |
| `request.hold_until` | date | 보류 중 | 보류 예정일(3.2에 이미 있음). 이유는 주지 않음 | `cards.hold_until` |
| `rejection { reason_code, reason_text }` | 객체 | 반려된 요청 | 반려 이유. T04 2장 학부모 표시 '처리할 수 없는 요청이에요 (이유)'에 쓴다. 담임 화면은 반려할 때 이 글이 학부모에게 보인다고 알려야 한다 | `approvals`(`decision = dismiss`) |
| `sources[] { document_title, location, effective_from }` | 목록 | 회신이 나간 문의·민원 | 답변 출처. 학부모에게 공개된 문서(`visibility`가 `parents`·`all`)만 | 승인된 카드의 `card_evidence` → `document_chunks` → `documents` |

**알림장** (`GET /api/v1/daily-notes`의 `content`, `open_checks[]`)

`daily_notes.content`(`jsonb`)의 모양을 정한다. 화면은 줄마다 값과 출처를 보여 줄 수 있다.

```json
{
  "items": [
    { "key": "day", "label": "오늘 하루", "value": "블록 놀이와 바깥 산책을 했어요.", "source": { "type": "teacher_input" } },
    { "key": "meal", "label": "식사", "value": "점심 카레라이스를 다 먹었어요.",
      "source": { "type": "document", "document_id": "…", "document_title": "12월 식단표" } },
    { "key": "supplies", "label": "준비물", "value": "내일 실내화", "source": { "type": "teacher_input" } }
  ]
}
```

| 필드 | 값 | 설명 |
| --- | --- | --- |
| `items[].key` | `day`·`meal`·`medication`·`pickup`·`supplies` | 줄 종류. 투약·귀가 줄은 그 요청(T46)이 있을 때만 |
| `items[].source.type` | `teacher_input`·`document`·`request` | 담임 입력(`daily_note_inputs`), 원 자료(식단·일정), 학부모 요청(투약·귀가) |
| `items[].source.document_id`·`document_title` | — | `document`일 때 |
| `items[].source.request_id` | — | `request`일 때 |
| `open_checks[] { id, item_key, problem }` | — | 검사 AI가 짚은 확인 필요 항목과 그 줄. 알림장 고치기의 `resolved_checks[]`는 이 `id`를 보낸다 |

학부모가 받는 알림장(`sent`)에는 `open_checks`가 늘 빈 목록이다(DB 제약).

### 3.8 로그인·내 정보 — `POST /api/v1/auth/login`, `GET /api/v1/me`

| 칸 | 내용 |
| --- | --- |
| ① 호출 목적 | 로그인으로 토큰을 받고, 내 정보에서 현재 계정·담당 반·아이를 확인한다(FR-01). |
| ② 요청 헤더 | 로그인은 `Content-Type: application/json`, 내 정보는 `Authorization`(필수), `X-Request-ID`(권장). |
| ③ 경로·쿼리 | 없음. |
| ④ 요청 본문 | 로그인만 `login_id`·`password`. 내 정보는 없음. |
| ⑤ 검증·권한 | 로그인은 계정·비밀번호·사용 여부를 확인한다. 내 정보는 JWT 서명·만료·토큰 판·기관·역할·사용 여부를 확인한다. |
| ⑥ 정상 응답 | 200. 로그인은 `access_token`·`token_type`·`user`·`children`, 내 정보는 `user`·`children`. |
| ⑦ 오류 응답 | 아래 오류 표. |
| ⑧ 실행 규칙 | JWT는 HS256, 기본 수명 12시간이며 `iat`도 넣는다. 반·아이 관계는 조회 때 다시 구한다. |

| 필드 | 위치 | 타입 | 필수 | 빈값 | 제약 | 설명 |
| --- | --- | --- | --- | --- | --- | --- |
| `login_id` | 로그인 본문 | string | 필수 | 불가 | 1~64자 | 데모 계정은 모의 API README 참고 |
| `password` | 로그인 본문 | string | 필수 | 불가 | 1~128자 | 데모 전용 비밀번호는 `demo1234` |
| `access_token`·`token_type` | 로그인 응답 | string | 항상 | 불가 | JWT·`bearer` | 다음 요청의 인증에 사용 |
| `user` | 응답 | object | 항상 | 불가 | `id`·`role`·`display_name`·`org_id`·`classroom_ids[]` | 역할은 `parent`·`teacher`·`director` |
| `user.classroom_ids[]`·`children[]` | 응답 | 목록 | 항상 | 빈 목록 가능 | 역할별 값·아이 객체 모양은 3.7 참고 | 담임은 반, 학부모는 아이; 나머지는 빈 목록 |

```http
POST /api/v1/auth/login
{"login_id": "parent01", "password": "demo1234"}
HTTP/1.1 200 OK
{"user": {"id": "00000000-0000-4000-8000-000000000401", "role": "parent", "display_name": "하늘이 보호자", "org_id": "00000000-0000-4000-8000-000000000001", "classroom_ids": []}, "children": [{"id": "00000000-0000-4000-8000-000000000501", "display_name": "하늘", "classroom_id": "00000000-0000-4000-8000-000000000101"}], "access_token": "…", "token_type": "bearer"}
GET /api/v1/me
HTTP/1.1 200 OK
{"user": {"id": "00000000-0000-4000-8000-000000000401", "role": "parent", "display_name": "하늘이 보호자", "org_id": "00000000-0000-4000-8000-000000000001", "classroom_ids": []}, "children": [{"id": "00000000-0000-4000-8000-000000000501", "display_name": "하늘", "classroom_id": "00000000-0000-4000-8000-000000000101"}]}
```

| HTTP | `code` | 조건 |
| --- | --- | --- |
| 401 | `UNAUTHENTICATED` | 로그인 실패·비활성 계정, 내 정보의 토큰 문제 |
| 422 | `VALIDATION_FAILED` | 필수 칸·타입·허용 값·길이가 맞지 않음 |

### 3.9 내 요청 목록 — `GET /api/v1/requests`

| 칸 | 내용 |
| --- | --- |
| ① 호출 목적 | 학부모가 자기가 보낸 요청과 다음 할 일을 본다(FR-02). |
| ② 요청 헤더 | `Authorization`(필수), `X-Request-ID`(권장). |
| ③ 경로·쿼리 | 아래 쿼리 필드. |
| ④ 요청 본문 | 없음. |
| ⑤ 검증·권한 | 학부모만. 같은 기관·본인 요청을 고른 뒤 상태 조건을 적용한다. |
| ⑥ 정상 응답 | 200 + `items[]`·`total`·`page`·`size`. 해당 요청이 없으면 빈 목록. |
| ⑦ 오류 응답 | 아래 오류 표. |
| ⑧ 실행 규칙 | 조회 때 보류·상담 시간 만료를 반영한다. 정렬 뒤 쪽을 나눈다. |

| 필드 | 위치 | 타입 | 필수 | 빈값 | 제약 | 설명 |
| --- | --- | --- | --- | --- | --- | --- |
| `status` | 쿼리 | string | 선택 | 생략 가능 | 3.2의 요청 상태 11개 | 생략하면 모든 상태 |
| `page`·`size` | 쿼리 | integer | 선택 | 불가 | 기본 1·20, page ≥ 1, size 1~100 | 쪽 나누기 |
| `sort` | 쿼리 | string | 선택 | 불가 | `-created_at`(기본)·`created_at`·`-updated_at`·`updated_at` | 생성·변경 시각 순 |
| `items[].id`·`type`·`title`·`status`·`status_label`·`updated_at` | 응답 | UUID·string·datetime | 항상 | title은 null 가능 | 요청 유형 3개·상태 11개 | 본인 요청의 요약 |
| `items[].next_action` | 응답 | string | 항상 | null 가능 | 정보 보완·시간 선택·민원 회신 확인 | needs_info면 보완 또는 시간 선택, 미확인 민원 회신이면 확인 안내 |
| `items[].hold_until` | 응답 | date | 항상 | null 가능 | 보류 카드의 예정일 | 할 일·보류가 없으면 해당 칸은 null |
| `total`·`page`·`size` | 응답 | integer | 항상 | 불가 | 전체 건수·요청한 쪽·크기 | 목록 공통 칸 |

```http
GET /api/v1/requests?status=needs_info
HTTP/1.1 200 OK
{"total": 1, "page": 1, "size": 20, "items": [{"id": "00000000-0000-4000-8000-000000000701", "type": "consultation", "title": "아이 친구 관계 상담", "status": "needs_info", "status_label": "시간을 골라 주세요", "updated_at": "2026-11-18T10:00:00+09:00", "next_action": "시간을 골라 주세요", "hold_until": null}]}
```

| HTTP | `code` | 조건 |
| --- | --- | --- |
| 401 | `UNAUTHENTICATED` | 토큰 없음·만료·무효 |
| 403 | `FORBIDDEN_ROLE` | 허용하지 않은 역할 |
| 422 | `VALIDATION_FAILED` | 필수 칸·타입·허용 값·길이가 맞지 않음 |

### 3.10 대화 이어 쓰기 — `POST /api/v1/requests/{request_id}/messages`

| 칸 | 내용 |
| --- | --- |
| ① 호출 목적 | 학부모가 진행 중인 요청에 설명을 더한다(FR-02). |
| ② 요청 헤더 | `Authorization`(필수), `X-Request-ID`(권장), `Content-Type: application/json`. |
| ③ 경로·쿼리 | `request_id`(UUID, 필수). |
| ④ 요청 본문 | `body`(아래 표). |
| ⑤ 검증·권한 | 본인 요청만. `completed`·`rejected`는 409로 막는다. |
| ⑥ 정상 응답 | 201 + `message`. 다음 상태는 요청 상세(3.2)에서 확인한다. |
| ⑦ 오류 응답 | 아래 오류 표. |
| ⑧ 실행 규칙 | 민원 회신 뒤 추가 글이면 학부모 확인을 지우고 회신 카드를 pending으로 돌려 판을 1 올린다. 요청은 awaiting_review가 된다. 상담 이외 needs_info면 모의 분류를 다시 실행한다. |

| 필드 | 위치 | 타입 | 필수 | 빈값 | 제약 | 설명 |
| --- | --- | --- | --- | --- | --- | --- |
| `request_id` | 경로 | string(UUID) | 필수 | 불가 | 본인 요청 | 대화를 이을 요청 |
| `body` | 본문 | string | 필수 | 불가 | 1~2,000자 | 추가 설명; 모의 구현은 공백만인 글도 길이로 검사 |
| `message.id` | 응답 | integer | 항상 | 불가 | 서버 발급 | 메시지 ID |
| `message.sender_type`·`body`·`created_at` | 응답 | string·datetime | 항상 | 불가 | sender_type은 `user` | 저장한 글과 시각 |

```http
POST /api/v1/requests/00000000-0000-4000-8000-000000000702/messages
{"body": "버스 도착 시각을 더 알려드릴게요."}
HTTP/1.1 201 Created
{"message": {"id": 1071, "sender_type": "user", "body": "버스 도착 시각을 더 알려드릴게요.", "created_at": "2026-11-18T10:00:00+09:00"}}
```

| HTTP | `code` | 조건 |
| --- | --- | --- |
| 401 | `UNAUTHENTICATED` | 토큰 없음·만료·무효 |
| 403 | `FORBIDDEN_ROLE` | 허용하지 않은 역할 |
| 404 | `NOT_FOUND` | 없거나 기관·반·소유 범위 밖 |
| 409 | `INVALID_TRANSITION` | 끝난 요청에 글을 더함 |
| 422 | `VALIDATION_FAILED` | 필수 칸·타입·허용 값·길이가 맞지 않음 |

### 3.11 알림 목록·읽음 — `GET /api/v1/notifications`, `POST /api/v1/notifications/{notification_id}/read`

| 칸 | 내용 |
| --- | --- |
| ① 호출 목적 | 내 알림을 보고 읽은 시각을 남긴다(FR-12). |
| ② 요청 헤더 | `Authorization`(필수), `X-Request-ID`(권장). |
| ③ 경로·쿼리 | 목록은 page·size·sort, 읽음은 정수 notification_id. |
| ④ 요청 본문 | 없음. |
| ⑤ 검증·권한 | 모든 로그인 역할. 같은 기관·본인 알림 중 deliver_after가 지난 것만 보인다. 읽음도 이 범위에서 찾는다. |
| ⑥ 정상 응답 | 목록 200 + 쪽 나눈 items[], 읽음 200 + notification. |
| ⑦ 오류 응답 | 아래 오류 표. |
| ⑧ 실행 규칙 | 모의 발송기는 조회할 때 pending 알림을 sent로 바꾼다. 읽음을 반복해도 첫 read_at을 유지한다. 예약된 알림은 시각 전까지 목록·읽음 모두에서 제외한다. |

| 필드 | 위치 | 타입 | 필수 | 빈값 | 제약 | 설명 |
| --- | --- | --- | --- | --- | --- | --- |
| `page`·`size` | 쿼리 | integer | 선택 | 불가 | 기본 1·20, page ≥ 1, size 1~100 | 쪽 나누기 |
| `sort` | 쿼리 | string | 선택 | 불가 | `-created_at`(기본)·`created_at` | 내림차순·오름차순 |
| `notification_id` | 읽음 경로 | integer | 필수 | 불가 | 목록에서 받은 ID | 0 이하도 형식상 정수이며 없으면 404 |
| `items[].id`·`kind`·`title` | 목록 응답 | integer·string | 항상 | 불가 | kind는 알림 13종 | 알림 종류와 제목 |
| `items[].body`·`request_id`·`subject_type`·`subject_id` | 목록 응답 | string·UUID | 항상 | null 가능 | 알림장 알림은 subject_type=`daily_note` | 내용과 연결 대상 |
| `items[].read_at`·`deliver_after` | 목록 응답 | datetime | 항상 | read_at만 null 가능 | 한국 시간 포함 | 읽음·노출 시각; 읽음 응답 notification도 같은 모양 |
| `total`·`page`·`size` | 응답 | integer | 항상 | 불가 | 전체 건수·요청한 쪽·크기 | 목록 공통 칸 |

```http
GET /api/v1/notifications?size=1
HTTP/1.1 200 OK
{"total": 2, "page": 1, "size": 1, "items": [{"id": 1013, "kind": "needs_info", "title": "정보가 더 필요해요", "body": "시간을 골라 주세요", "request_id": "00000000-0000-4000-8000-000000000701", "subject_type": null, "subject_id": null, "read_at": null, "deliver_after": "2026-11-18T10:00:00+09:00"}]}
POST /api/v1/notifications/1013/read
HTTP/1.1 200 OK
{"notification": {"id": 1013, "kind": "needs_info", "read_at": "2026-11-18T10:00:00+09:00", "deliver_after": "2026-11-18T10:00:00+09:00"}}
```

| HTTP | `code` | 조건 |
| --- | --- | --- |
| 401 | `UNAUTHENTICATED` | 토큰 없음·만료·무효 |
| 404 | `NOT_FOUND` | 없거나 기관·반·소유 범위 밖 |
| 422 | `VALIDATION_FAILED` | 필수 칸·타입·허용 값·길이가 맞지 않음 |

### 3.12 받은함 — `GET /api/v1/cards`

| 칸 | 내용 |
| --- | --- |
| ① 호출 목적 | 담임·원장이 받은함 카드와 필터별 건수를 본다(FR-09). |
| ② 요청 헤더 | `Authorization`(필수), `X-Request-ID`(권장). |
| ③ 경로·쿼리 | 파라미터·화면용 더한 칸은 3.7 참고. sort는 받지 않는다. |
| ④ 요청 본문 | 없음. |
| ⑤ 검증·권한 | 담임은 현재 담당 반 또는 본인에게 배정된 카드, 원장은 같은 기관 전체를 본다. |
| ⑥ 정상 응답 | 200 + items[]·counts·type_counts·total·page·size. filter를 생략하면 done을 뺀다. |
| ⑦ 오류 응답 | 아래 오류 표. |
| ⑧ 실행 규칙 | 만료를 반영하고 긴급 우선 → due_at이 있는 카드 우선 → due_at 오름차순 → 카드 UUID 문자열 순으로 정렬한다. 기한 지난 완료 카드도 is_delayed 자체는 참일 수 있다. |

| 필드 | 위치 | 타입 | 필수 | 빈값 | 제약 | 설명 |
| --- | --- | --- | --- | --- | --- | --- |
| `filter`·`request_type`·`risk_level`·`kind`·`assignee`·`page`·`size` | 쿼리 | 3.7 참고 | 선택 | 생략 가능 | 3.7 참고 | 기본 size=20, 최대 100 |
| `items[].id`·`kind`·`status`·`version`·`title` | 응답 | UUID·string·integer | 항상 | 불가 | 카드 종류 6개, version ≥ 1 | status는 카드 내부 값 |
| `items[].status_label`·`request_type`·`urgency`·`is_urgent` | 응답 | string·boolean | 항상 | request_type·urgency는 null 가능 | is_urgent는 요청 risk_level=urgent 여부 | 표시 이름은 요청 상태 기준 |
| `items[].assignee`·`due_at`·`is_delayed`·`hold_until` | 응답 | object·datetime·boolean·date | 항상 | is_delayed 외 null 가능 | assignee={id, display_name}; due_at < 현재면 지연 | 화면용 더한 칸은 3.7 참고 |
| `counts` | 응답 | object(integer) | 항상 | 불가 | 필터 6개를 모두 넣고 없으면 0 | 역할·risk_level·kind·assignee·request_type 안에서, filter 적용 전에 카드 수를 셈 |
| `type_counts` | 응답 | object(integer) | 항상 | 불가 | all·complaint·consultation·inquiry | 역할·risk_level·kind·assignee·filter 안에서, request_type 적용 전에 셈 |
| `total`·`page`·`size` | 응답 | integer | 항상 | 불가 | 전체 건수·요청한 쪽·크기 | 목록 공통 칸 |

필터는 순서대로 하나만 고른다. ① 끝난 카드·요청은 `done`(회신 후 민원의 거절 아닌 reply_draft는 처리 완료 전까지 예외) ② 카드·요청 보류는 `on_hold` ③ 담당 없음은 `unassigned` ④ 위험 등급 uncertain은 `uncertain` ⑤ awaiting_review·escalated, 학부모 확인한 회신 민원, 요청 없는 카드는 `needs_review` ⑥ 나머지는 `in_progress`.
종류 건수도 요청 수가 아닌 카드 수다. `type_counts.all`은 요청 없는 카드까지 세므로 세 유형 건수의 합보다 클 수 있다. counts는 완료도 포함하고, type_counts는 filter가 없으면 완료를 뺀다.

```http
GET /api/v1/cards?filter=needs_review&request_type=complaint&page=3&size=1
HTTP/1.1 200 OK
{"items": [{"id": "00000000-0000-4000-8000-000000000802", "kind": "reply_draft", "version": 1, "request_type": "complaint", "is_urgent": false}], "counts": {"unassigned": 0, "needs_review": 3, "uncertain": 2, "on_hold": 1, "in_progress": 0, "done": 0}, "type_counts": {"complaint": 3, "consultation": 0, "inquiry": 0, "all": 4}, "total": 3, "page": 3, "size": 1}
```

| HTTP | `code` | 조건 |
| --- | --- | --- |
| 401 | `UNAUTHENTICATED` | 토큰 없음·만료·무효 |
| 403 | `FORBIDDEN_ROLE` | 허용하지 않은 역할 |
| 422 | `VALIDATION_FAILED` | 필수 칸·타입·허용 값·길이가 맞지 않음 |

### 3.13 카드 상세·교직원 스트림 — `GET /api/v1/cards/{card_id}`, `GET …/stream`

| 칸 | 내용 |
| --- | --- |
| ① 호출 목적 | 교직원이 초안·근거·위험·전체 이력을 보고, 스트림으로 단계·초안 글자·카드를 받는다(FR-04·07·09·11, NFR-10). |
| ② 요청 헤더 | `Authorization`(필수), `X-Request-ID`(권장). 스트림은 `Accept: text/event-stream`, fetch 스트림으로 읽는다. |
| ③ 경로·쿼리 | card_id(UUID, 필수). |
| ④ 요청 본문 | 없음. |
| ⑤ 검증·권한 | 담임은 담당 반 또는 본인 배정 카드, 원장은 같은 기관 전체. 학부모는 403, 범위 밖은 404. |
| ⑥ 정상 응답 | 상세는 200 + 아래 칸. 스트림은 200 text/event-stream, Cache-Control: no-cache. |
| ⑦ 오류 응답 | 아래 오류 표. |
| ⑧ 실행 규칙 | 조회 때 해당 요청의 만료를 반영한다. 모의 스트림은 classifying→searching→drafting→checking, text를 12자씩 token, card, done 순으로 재생한다. text가 없으면 token은 없고, 요청 없는 카드의 done.request_status는 null이다. 간격 기본 300ms, 매 연결 다시 재생한다. |

| 필드 | 위치 | 타입 | 필수 | 빈값 | 제약 | 설명 |
| --- | --- | --- | --- | --- | --- | --- |
| `card_id` | 경로 | string(UUID) | 필수 | 불가 | 권한 범위 안 | 상세·스트림 공통 |
| `card.id`·`kind`·`status`·`version`·`summary`·`draft`·`check_result`·`check_attempts` | 응답 | UUID·string·integer·object | 항상 | check_result만 null 가능 | draft는 객체, check_attempts는 검사 횟수 | summary 등 화면용 칸은 3.7 참고 |
| `request` | 응답 | object | 항상 | null 가능 | 3.2 요약 + body·risk_level·risk_category·repeat_count·classroom_id | 요청 없는 카드면 null |
| `evidence[]`·`warnings[]`·`parent_choices[]`·`rule`·`director_instruction` | 응답 | 목록·object | 항상 | rule·director_instruction은 null 가능 | 3.7 참고 | 근거·경고·선택 시간·규칙·원장 지시 |
| `timeline[]` | 응답 | object[] | 항상 | 빈 목록 가능 | id·action·request_id·card_id·agent_name·actor_type·actor_id·from_status·to_status·detail·created_at | 같은 요청의 이력 또는 해당 카드 이력, 저장 순서 |
| `stage`·`token`·`card`·`done` | SSE data | object | 이벤트별 | request_status는 null 가능 | {stage, at}·{text}·{id, status, version}·{request_status} | token·card는 교직원만 받음 |

```http
GET /api/v1/cards/00000000-0000-4000-8000-000000000802
HTTP/1.1 200 OK
{"card": {"id": "00000000-0000-4000-8000-000000000802", "kind": "reply_draft", "status": "pending", "version": 1, "summary": "등원 버스가 늦었어요", "draft": {"summary": "등원 버스가 늦었어요", "text": "(모의 초안) 말씀해 주셔서 감사합니다. 확인해서 다시 안내드릴게요.", "no_evidence": false}}, "warnings": [], "parent_choices": [], "rule": null, "director_instruction": null}
GET /api/v1/cards/00000000-0000-4000-8000-000000000802/stream
HTTP/1.1 200 OK
Content-Type: text/event-stream
event: token
data: {"text": "(모의 초안) 말씀해 "}

event: card
data: {"id": "00000000-0000-4000-8000-000000000802", "status": "pending", "version": 1}

event: done
data: {"request_status": "awaiting_review"}
```

| HTTP | `code` | 조건 |
| --- | --- | --- |
| 401 | `UNAUTHENTICATED` | 토큰 없음·만료·무효 |
| 403 | `FORBIDDEN_ROLE` | 허용하지 않은 역할 |
| 404 | `NOT_FOUND` | 없거나 기관·반·소유 범위 밖 |
| 422 | `VALIDATION_FAILED` | 필수 칸·타입·허용 값·길이가 맞지 않음 |

### 3.14 위험 등급 다시 분류 — `POST /api/v1/cards/{card_id}/reclassify`

| 칸 | 내용 |
| --- | --- |
| ① 호출 목적 | 교직원이 민원의 위험 등급을 일반 또는 긴급으로 다시 정한다(FR-03·07). |
| ② 요청 헤더 | `Authorization`(필수), `X-Request-ID`(권장), `Content-Type: application/json`. |
| ③ 경로·쿼리 | card_id(UUID, 필수). |
| ④ 요청 본문 | 아래 필드 표. |
| ⑤ 검증·권한 | 담임·원장만. 원장 보고 카드는 원장만. 요청이 민원이고 awaiting_review·escalated여야 하며, 판을 확인한다. uncertain만으로 제한하지 않는다. |
| ⑥ 정상 응답 | 200 + 교직원용 request. 응답에 card는 없으므로 새 판은 카드 상세에서 받는다. |
| ⑦ 오류 응답 | 아래 오류 표. |
| ⑧ 실행 규칙 | 일반이면 risk_category를 지우고 awaiting_review로, 긴급이면 원장 보고 카드를 확보하고 escalated로 바꾼다. 같은 요청 카드의 due_at을 접수 시각 기준으로 다시 계산하며 호출한 카드 판만 1 올린다. 초안은 새로 만들지 않는다. |

| 필드 | 위치 | 타입 | 필수 | 빈값 | 제약 | 설명 |
| --- | --- | --- | --- | --- | --- | --- |
| `card_id` | 경로 | string(UUID) | 필수 | 불가 | 권한 범위 안 | 위험 등급을 바꿀 카드 |
| `version` | 본문 | integer | 필수 | 불가 | 1 이상 | 화면이 본 카드 판 |
| `risk_level` | 본문 | string | 필수 | 불가 | `normal`·`urgent` | 새 등급 |
| `risk_category` | 본문 | string | 긴급이면 필수 | 일반은 null 가능 | `child_safety`·`staff_attack`·`legal_external`·`privacy_leak` | 일반이면 보내도 저장하지 않음 |
| `reason` | 본문 | string | 필수 | 불가 | 1~500자, 공백만 불가 | 처리 이유 |
| `request` | 응답 | object | 항상 | 불가 | 3.13 교직원 요청과 같은 모양 | risk_level·risk_category·status 등을 돌려줌 |

```http
POST /api/v1/cards/00000000-0000-4000-8000-000000000802/reclassify
{"version": 1, "risk_level": "normal", "reason": "일반 민원으로 확인함"}
HTTP/1.1 200 OK
{"request": {"id": "00000000-0000-4000-8000-000000000702", "risk_level": "normal", "risk_category": null, "status": "awaiting_review", "status_label": "확인 필요"}}
```

| HTTP | `code` | 조건 |
| --- | --- | --- |
| 401 | `UNAUTHENTICATED` | 토큰 없음·만료·무효 |
| 403 | `FORBIDDEN_ROLE` | 허용하지 않은 역할 |
| 404 | `NOT_FOUND` | 없거나 기관·반·소유 범위 밖 |
| 409 | `CARD_VERSION_CONFLICT`·`INVALID_TRANSITION` | 판 불일치(details.current_version)·민원 아님·상태가 맞지 않음 |
| 422 | `VALIDATION_FAILED` | 필수 칸·타입·허용 값·길이가 맞지 않음 |

### 3.15 원장 보고 지시 — `POST /api/v1/cards/{card_id}/instructions`

| 칸 | 내용 |
| --- | --- |
| ① 호출 목적 | 원장이 보고 카드에 지시를 남기고 담임에게 처리를 넘긴다(FR-07). |
| ② 요청 헤더 | `Authorization`(필수), `X-Request-ID`(권장), `Content-Type: application/json`. |
| ③ 경로·쿼리 | card_id(UUID, 원장 보고 카드). |
| ④ 요청 본문 | version·instruction. |
| ⑤ 검증·권한 | 역할 director만. 같은 기관의 director_report, 카드 pending·in_review, 요청 escalated여야 한다. 판·같은 판의 기존 결정을 확인한다. |
| ⑥ 정상 응답 | 200 + done 카드(판 +1)·awaiting_review 요청·next_card_id=null. |
| ⑦ 오류 응답 | 아래 오류 표. |
| ⑧ 실행 규칙 | 결정을 instruct로, 지시를 reason_text로 기록한다. 기존 회신 카드 상세의 director_instruction에 최신 지시가 붙는다. 회신 카드의 판·초안은 바꾸지 않으며 승인·발송은 별도다. |

| 필드 | 위치 | 타입 | 필수 | 빈값 | 제약 | 설명 |
| --- | --- | --- | --- | --- | --- | --- |
| `card_id` | 경로 | string(UUID) | 필수 | 불가 | 원장 보고 카드 | 3.3 원장 보고 결과나 받은함에서 받은 ID |
| `version` | 본문 | integer | 필수 | 불가 | 1 이상 | 화면이 본 카드 판 |
| `instruction` | 본문 | string | 필수 | 불가 | 1~500자, 공백만 불가 | 원장 지시 |
| `card.id`·`status`·`version` | 응답 | UUID·string·integer | 항상 | 불가 | status=`done` | 끝난 보고 카드와 새 판 |
| `request`·`next_card_id` | 응답 | object·UUID | 항상 | next_card_id는 null | request={id, status, parent_confirmed_at} | 요청 상태는 awaiting_review |

```http
POST /api/v1/cards/{card_id}/instructions
{"version": 1, "instruction": "운행 시각을 확인하고 보호자에게 안내해 주세요."}
HTTP/1.1 200 OK
{"card": {"id": "…", "status": "done", "version": 2}, "request": {"id": "00000000-0000-4000-8000-000000000702", "status": "awaiting_review", "parent_confirmed_at": null}, "next_card_id": null}
```

| HTTP | `code` | 조건 |
| --- | --- | --- |
| 401 | `UNAUTHENTICATED` | 토큰 없음·만료·무효 |
| 403 | `FORBIDDEN_ROLE` | 허용하지 않은 역할 |
| 404 | `NOT_FOUND` | 없거나 기관·반·소유 범위 밖 |
| 409 | `ALREADY_DECIDED`·`CARD_VERSION_CONFLICT`·`INVALID_TRANSITION` | 같은 판의 기존 결정·판 불일치·카드 종류나 상태 불일치 |
| 422 | `VALIDATION_FAILED` | 필수 칸·타입·허용 값·길이가 맞지 않음 |

### 3.16 담당 재배정 — `POST /api/v1/cards/{card_id}/reassign`

| 칸 | 내용 |
| --- | --- |
| ① 호출 목적 | 원장이 카드 담당자를 바꾸고 이유를 남긴다(FR-09·19). |
| ② 요청 헤더 | `Authorization`(필수), `X-Request-ID`(권장), `Content-Type: application/json`. |
| ③ 경로·쿼리 | card_id(UUID, 필수). |
| ④ 요청 본문 | assignee_id·reason. version은 받지 않는다. |
| ⑤ 검증·권한 | director만. 배정 대상은 같은 기관의 활성 teacher여야 한다. director_report 또는 done·rejected 카드는 재배정하지 못한다. |
| ⑥ 정상 응답 | 200 + card { assignee { id, display_name }, version }. |
| ⑦ 오류 응답 | 아래 오류 표. |
| ⑧ 실행 규칙 | 카드와 연결 요청의 담당을 바꾸고 카드 판을 1 올린다. unassigned 카드만 pending으로 바꾼다. 요청 상태·기한은 유지한다. 다른 반 교사에게도 배정 가능하며 이력에 from·to·reason을 남긴다. |

| 필드 | 위치 | 타입 | 필수 | 빈값 | 제약 | 설명 |
| --- | --- | --- | --- | --- | --- | --- |
| `card_id` | 경로 | string(UUID) | 필수 | 불가 | 처리 가능한 카드 | 배정할 카드 |
| `assignee_id` | 본문 | string(UUID) | 필수 | 불가 | 같은 기관의 활성 teacher | 새 담당자 |
| `reason` | 본문 | string | 필수 | 불가 | 1~500자, 공백만 불가 | 처리 이유 |
| `card.assignee` | 응답 | object | 항상 | 불가 | id(UUID)·display_name(string) | 새 담당자 |
| `card.version` | 응답 | integer | 항상 | 불가 | 이전 판 +1 | 다음 결정에 쓸 판 |

```http
POST /api/v1/cards/00000000-0000-4000-8000-000000000802/reassign
{"assignee_id": "00000000-0000-4000-8000-000000000202", "reason": "담당자 부재로 재배정함"}
HTTP/1.1 200 OK
{"card": {"assignee": {"id": "00000000-0000-4000-8000-000000000202", "display_name": "햇님반 선생님"}, "version": 3}}
```

| HTTP | `code` | 조건 |
| --- | --- | --- |
| 401 | `UNAUTHENTICATED` | 토큰 없음·만료·무효 |
| 403 | `FORBIDDEN_ROLE` | 허용하지 않은 역할 |
| 404 | `NOT_FOUND` | 카드 범위 밖·대상 없음·다른 기관·비활성·교사 아님 |
| 409 | `INVALID_TRANSITION` | 원장 보고·끝난 카드 |
| 422 | `VALIDATION_FAILED` | 필수 칸·타입·허용 값·길이가 맞지 않음 |

### 3.17 개인 규칙 제안 켜기·거절 — `POST /api/v1/memory-rules/{rule_id}/decision`

| 칸 | 내용 |
| --- | --- |
| ① 호출 목적 | 규칙 주인이 제안을 켜거나 거절한다(FR-06). |
| ② 요청 헤더 | `Authorization`(필수), `X-Request-ID`(권장), `Content-Type: application/json`. |
| ③ 경로·쿼리 | rule_id(UUID, 필수). |
| ④ 요청 본문 | decision. |
| ⑤ 검증·권한 | 로그인한 규칙 주인만. 같은 기관·주인 검사를 하며 다른 역할이라는 이유만으로 403을 내지는 않는다. proposed 상태만 결정한다. |
| ⑥ 정상 응답 | 200 + rule { id, status }. activate는 active, decline은 declined. |
| ⑦ 오류 응답 | 아래 오류 표. |
| ⑧ 실행 규칙 | 연결 제안 카드를 done으로 바꾸고 판을 1 올린다. 켜기는 approve, 거절은 reject로 결정·이력을 남긴다. 재요청은 409이며 모의 상담 후보에 규칙을 적용하지는 않는다. |

| 필드 | 위치 | 타입 | 필수 | 빈값 | 제약 | 설명 |
| --- | --- | --- | --- | --- | --- | --- |
| `rule_id` | 경로 | string(UUID) | 필수 | 불가 | 본인 규칙 | 카드 상세 rule.id |
| `decision` | 본문 | string | 필수 | 불가 | `activate`·`decline` | 켜기·거절 |
| `rule.id` | 응답 | string(UUID) | 항상 | 불가 | 요청한 규칙 ID | 결정 대상 |
| `rule.status` | 응답 | string | 항상 | 불가 | `active`·`declined` | 저장한 상태 |

```http
POST /api/v1/memory-rules/00000000-0000-4000-8000-000000000d01/decision
{"decision": "activate"}
HTTP/1.1 200 OK
{"rule": {"id": "00000000-0000-4000-8000-000000000d01", "status": "active"}}
```

| HTTP | `code` | 조건 |
| --- | --- | --- |
| 401 | `UNAUTHENTICATED` | 토큰 없음·만료·무효 |
| 404 | `NOT_FOUND` | 없거나 기관·반·소유 범위 밖 |
| 409 | `INVALID_TRANSITION` | proposed가 아닌 규칙, 같은 결정의 반복 포함 |
| 422 | `VALIDATION_FAILED` | 필수 칸·타입·허용 값·길이가 맞지 않음 |

### 3.18 원장 현황 — `GET /api/v1/overview`

| 칸 | 내용 |
| --- | --- |
| ① 호출 목적 | 원장이 기관 전체의 대기·지연·처리 결과와 재배정 이력을 본다(FR-09·19). |
| ② 요청 헤더 | `Authorization`(필수), `X-Request-ID`(권장). |
| ③ 경로·쿼리 | 없음. |
| ④ 요청 본문 | 없음. |
| ⑤ 검증·권한 | director만. 모든 집계는 같은 기관 안에서 한다. |
| ⑥ 정상 응답 | 200 + 아래 숫자 5개·reassignments[]·eval[]. |
| ⑦ 오류 응답 | 아래 오류 표. |
| ⑧ 실행 규칙 | 먼저 만료를 반영한다. 카드 단위 집계이며 completed_unconfirmed만 최근 30일 닫힌 done 카드의 요청 ID를 중복 없이 모아 민원·completed·학부모 미확인인 것을 센다. 모의 eval은 빈 목록이다. |

| 필드 | 위치 | 타입 | 필수 | 빈값 | 제약 | 설명 |
| --- | --- | --- | --- | --- | --- | --- |
| `unassigned` | 응답 | integer | 항상 | 불가 | 받은함 필터 unassigned인 카드 수 | 미배정 |
| `waiting`·`delayed` | 응답 | integer | 항상 | 불가 | pending·in_review·on_hold 수 / 그중 due_at이 지난 수 | 대기·지연 |
| `done_today` | 응답 | integer | 항상 | 불가 | status=done이고 closed_at의 한국 날짜가 오늘 | 오늘 닫은 카드 수; 요청 완료 수와 다름 |
| `completed_unconfirmed` | 응답 | integer | 항상 | 불가 | 위 실행 규칙; 최근 30일 | 학부모 미확인 완료 요청 수 |
| `reassignments[]` | 응답 | object[] | 항상 | 빈 목록 가능 | card_id·from(null 가능)·to·reason·at | 기관의 전체 재배정 이력, 저장 순서 |
| `eval[]` | 응답 | object[] | 항상 | 빈 목록 가능 | suite·requested_model·returned_model(null 가능)·passed·total·started_at | 평가 결과; 모의 값은 [] |

```http
GET /api/v1/overview
HTTP/1.1 200 OK
{"unassigned": 1, "waiting": 8, "delayed": 0, "done_today": 1, "completed_unconfirmed": 0, "reassignments": [], "eval": []}
```

| HTTP | `code` | 조건 |
| --- | --- | --- |
| 401 | `UNAUTHENTICATED` | 토큰 없음·만료·무효 |
| 403 | `FORBIDDEN_ROLE` | 허용하지 않은 역할 |

### 3.19 알림장 초안 만들기·진행 상태 — `POST /api/v1/daily-notes/drafts`, `GET …/drafts/{input_id}`

| 칸 | 내용 |
| --- | --- |
| ① 호출 목적 | 담임이 반 전체 알림장 초안을 만들고 작업 상태를 확인한다(FR-10). |
| ② 요청 헤더 | `Authorization`(필수), `X-Request-ID`(권장), `Content-Type: application/json`; 상태 조회는 본문 없음. |
| ③ 경로·쿼리 | 상태 조회만 input_id(UUID, 필수). |
| ④ 요청 본문 | 생성은 classroom_id·note_date·activities·supplies. |
| ⑤ 검증·권한 | teacher만, 현재 담당 반만. note_date는 오늘 또는 지난날. 같은 반·날짜가 있으면 입력 내용이 달라도 기존 작업을 돌려준다. |
| ⑥ 정상 응답 | 생성 202, 중복 200, 상태 조회 200. 모두 input_id·draft_status·error. |
| ⑦ 오류 응답 | 아래 오류 표. |
| ⑧ 실행 규칙 | 202 뒤 상태는 GET /daily-notes/drafts/{input_id}, 아이별 결과는 GET /daily-notes?classroom_id=&date=(3.20). 모의 생성은 즉시 succeeded, activities에 [실패]가 있으면 failed다. 실패도 작업·확인 카드를 남기지만 아이별 알림장은 없다. |

| 필드 | 위치 | 타입 | 필수 | 빈값 | 제약 | 설명 |
| --- | --- | --- | --- | --- | --- | --- |
| `input_id` | 조회 경로·응답 | string(UUID) | 조회·응답 필수 | 불가 | 접수 응답에서 받은 값 | 상태 조회 키 |
| `classroom_id` | 생성 본문 | string(UUID) | 필수 | 불가 | 현재 담당 반 | 초안을 만들 반 |
| `note_date` | 생성 본문 | date | 필수 | 불가 | YYYY-MM-DD, 오늘 또는 지난날 | 알림 날짜 |
| `activities` | 생성 본문 | string | 필수 | 불가 | 1~2,000자 | 오늘 활동 |
| `supplies` | 생성 본문 | string | 필수 | 빈 문자열 가능 | 최대 2,000자 | 준비물이 없어도 칸은 보냄 |
| `draft_status`·`error` | 응답 | string·object | 항상 | error는 null 가능 | queued·running·succeeded·failed; 오류는 {code, message} | 실패 조회도 200, 모의 오류 코드는 UPSTREAM_UNAVAILABLE |

```http
POST /api/v1/daily-notes/drafts
{"classroom_id": "00000000-0000-4000-8000-000000000101", "note_date": "2026-11-18", "activities": "블록 놀이와 산책을 했어요.", "supplies": "내일 실내화"}
HTTP/1.1 202 Accepted
{"input_id": "…", "draft_status": "succeeded", "error": null}
GET /api/v1/daily-notes/drafts/{input_id}
HTTP/1.1 200 OK
{"input_id": "…", "draft_status": "succeeded", "error": null}
```

| HTTP | `code` | 조건 |
| --- | --- | --- |
| 401 | `UNAUTHENTICATED` | 토큰 없음·만료·무효 |
| 403 | `FORBIDDEN_ROLE` | 허용하지 않은 역할 |
| 404 | `NOT_FOUND` | 없거나 기관·반·소유 범위 밖 |
| 422 | `VALIDATION_FAILED` | 필수 칸·타입·허용 값·길이가 맞지 않음 |

### 3.20 알림장 보기 — `GET /api/v1/daily-notes`

| 칸 | 내용 |
| --- | --- |
| ① 호출 목적 | 날짜별 아이 알림장을 본다. 담임은 반 전체 초안·확인 상태를, 학부모는 내 아이의 보낸 알림장을 받는다(FR-10). |
| ② 요청 헤더 | `Authorization`(필수), `X-Request-ID`(권장). |
| ③ 경로·쿼리 | date(필수), classroom_id(담임 필수), page·size·sort. |
| ④ 요청 본문 | 없음. |
| ⑤ 검증·권한 | 학부모는 내 아이·sent만. 담임은 현재 담당 반만. director는 기관 전체를 읽으며 반을 고를 수 있다. |
| ⑥ 정상 응답 | 200 + 쪽 나눈 items[]. 조건에 맞는 알림장이 없으면 빈 목록. |
| ⑦ 오류 응답 | 아래 오류 표. |
| ⑧ 실행 규칙 | 학부모에게 classroom_id를 주어도 내 아이·sent 조건을 먼저 적용한다. created_at으로 정렬 뒤 쪽을 나눈다. 모의 초안은 day·supplies·meal 세 줄이며 첫 아이에 준비물 확인 항목 c1을 넣는다. |

| 필드 | 위치 | 타입 | 필수 | 빈값 | 제약 | 설명 |
| --- | --- | --- | --- | --- | --- | --- |
| `date` | 쿼리 | date | 필수 | 불가 | YYYY-MM-DD, 미래 날짜 조회도 허용 | 알림 날짜 |
| `classroom_id` | 쿼리 | string(UUID) | 담임 필수 | 생략 가능 | 담임은 현재 담당 반 | 학부모·원장은 선택 |
| `page`·`size` | 쿼리 | integer | 선택 | 불가 | 기본 1·20, page ≥ 1, size 1~100 | 쪽 나누기 |
| `sort` | 쿼리 | string | 선택 | 불가 | `-created_at`(기본)·`created_at` | 내림차순·오름차순 |
| `items[].id`·`child_id`·`note_date`·`status` | 응답 | UUID·date·string | 항상 | 불가 | draft·needs_check·ready·sent | 아이별 알림장; 보낸 것만 학부모에게 노출 |
| `items[].content`·`open_checks[]` | 응답 | object·object[] | 항상 | 빈 목록 가능 | 줄·출처·확인 항목 모양은 3.7 참고 | items는 key·label·value·source를 가짐 |
| `items[].confirmed_at`·`sent_at` | 응답 | datetime | 항상 | null 가능 | 확인·발송 뒤 시각 | 아직 실행하지 않았으면 null |
| `total`·`page`·`size` | 응답 | integer | 항상 | 불가 | 전체 건수·요청한 쪽·크기 | 목록 공통 칸 |

```http
GET /api/v1/daily-notes?classroom_id=00000000-0000-4000-8000-000000000101&date=2026-11-18
HTTP/1.1 200 OK
{"items": [{"child_id": "00000000-0000-4000-8000-000000000503", "note_date": "2026-11-18", "status": "draft", "content": {"items": [{"key": "day", "label": "오늘 하루", "value": "블록 놀이와 산책을 했어요.", "source": {"type": "teacher_input", "document_id": null, "document_title": null, "request_id": null}}, {"key": "supplies", "label": "준비물", "value": "내일 실내화", "source": {"type": "teacher_input", "document_id": null, "document_title": null, "request_id": null}}, {"key": "meal", "label": "식사", "value": "점심: 카레라이스, 채소와 과일", "source": {"type": "document", "document_id": "00000000-0000-4000-8000-000000000b01", "document_title": "가상 식단표", "request_id": null}}]}, "open_checks": [], "confirmed_at": null, "sent_at": null}], "total": 2, "page": 1, "size": 20}
```

| HTTP | `code` | 조건 |
| --- | --- | --- |
| 401 | `UNAUTHENTICATED` | 토큰 없음·만료·무효 |
| 403 | `FORBIDDEN_ROLE` | 허용하지 않은 역할 |
| 404 | `NOT_FOUND` | 없거나 기관·반·소유 범위 밖 |
| 422 | `VALIDATION_FAILED` | date 누락·날짜/UUID/쪽 형식 오류·담임의 classroom_id 누락 |

### 3.21 알림장 고치기·확인 — `PATCH /api/v1/daily-notes/{note_id}`

| 칸 | 내용 |
| --- | --- |
| ① 호출 목적 | 담임이 아이별 알림장을 고치고 확인 항목을 해결한 뒤 발송 준비를 마친다(FR-10). |
| ② 요청 헤더 | `Authorization`(필수), `X-Request-ID`(권장), `Content-Type: application/json`. |
| ③ 경로·쿼리 | note_id(UUID, 필수). |
| ④ 요청 본문 | content·resolved_checks·confirm, 모두 선택. |
| ⑤ 검증·권한 | teacher와 현재 담당 반만. 문서·요청 출처도 범위를 검사한다. sent는 수정 불가. 없는 확인 ID와 미해결 항목을 남긴 confirm은 저장된 확인 항목과 대조해야 알 수 있어 서버가 409로 막는다(4.1). |
| ⑥ 정상 응답 | 200 + note. confirm=true이고 미해결 0개면 ready·confirmed_at을 남긴다. |
| ⑦ 오류 응답 | 아래 오류 표. |
| ⑧ 실행 규칙 | content를 보내면 전체 내용을 바꾼다. confirm=false(기본)이면 기존 확인을 지우고 미해결 유무에 따라 needs_check·draft로 되돌린다. 빈 본문도 기존 확인을 해제한다. 오류면 수정하지 않는다. |

| 필드 | 위치 | 타입 | 필수 | 빈값 | 제약 | 설명 |
| --- | --- | --- | --- | --- | --- | --- |
| `note_id` | 경로 | string(UUID) | 필수 | 불가 | 현재 담당 반 알림장 | 3.20 응답에서 받은 ID |
| `content` | 본문 | object | 선택 | null 가능 | items[]의 key·label·value·source는 3.7; 빈 items도 허용 | 생략·null이면 내용 유지 |
| `content.items[].key` | 본문 | string | 줄마다 필수 | 불가 | day·meal·medication·pickup·supplies | 줄 종류 |
| `content.items[].label`·`value` | 본문 | string | 줄마다 필수 | value만 빈 문자열 가능 | label은 1자 이상, value 길이 제한 없음 | 줄 이름과 내용 |
| `content.items[].source` | 본문 | object | 줄마다 필수 | 불가 | document면 document_id·document_title, request면 request_id 필수 | 출처 종류는 teacher_input·document·request |
| `resolved_checks[]` | 본문 | string[] | 선택 | 빈 목록 가능 | 기본 [], 현재 open_checks의 id만 | 해결한 확인 항목 |
| `confirm` | 본문 | boolean | 선택 | 불가 | 기본 false | 미해결 항목이 없어야 true 가능 |
| `note` | 응답 | object | 항상 | 불가 | 3.20 items[]와 같은 모양 | status·open_checks·confirmed_at 포함 |

```http
PATCH /api/v1/daily-notes/{note_id}
{"resolved_checks": ["c1"], "confirm": true}
HTTP/1.1 200 OK
{"note": {"child_id": "00000000-0000-4000-8000-000000000501", "status": "ready", "open_checks": [], "confirmed_at": "2026-11-18T10:00:00+09:00"}}
```

| HTTP | `code` | 조건 |
| --- | --- | --- |
| 401 | `UNAUTHENTICATED` | 토큰 없음·만료·무효 |
| 403 | `FORBIDDEN_ROLE` | 허용하지 않은 역할 |
| 404 | `NOT_FOUND` | 없거나 기관·반·소유 범위 밖 |
| 409 | `INVALID_TRANSITION` | sent 수정, 없는 resolved_checks ID, confirm인데 미해결 항목 있음(details.open_checks) |
| 422 | `VALIDATION_FAILED` | 형식·출처 필수 칸 |

### 3.22 자료 올리기 — `POST /api/v1/documents`

| 칸 | 내용 |
| --- | --- |
| ① 호출 목적 | 교직원이 자료 파일과 적용 범위를 올리고 적재 결과를 확인한다(FR-13). |
| ② 요청 헤더 | `Authorization`(필수), `X-Request-ID`(권장), `Content-Type: multipart/form-data; boundary=…`. |
| ③ 경로·쿼리 | 없음. |
| ④ 요청 본문 | 아래 multipart/form-data 필드 표. classroom_ids[]는 같은 이름으로 반복 전송한다. |
| ⑤ 검증·권한 | teacher·director만. 대상 반·이전 문서의 범위를 검사한다. 새 판의 이전 문서는 active여야 한다. |
| ⑥ 정상 응답 | 새 자료 202 + document, 같은 기관의 같은 바이트 자료는 200 + 기존 document. |
| ⑦ 오류 응답 | 아래 오류 표. |
| ⑧ 실행 규칙 | 접수 뒤 GET /documents/{document_id}(3.23)로 성공·실패를 확인한다. 모의 적재는 즉시 끝나며 UTF-8 치환 해독 후 500자씩 나눈다(빈 파일도 1조각). 파일명 [실패]는 ingest_status=failed·chunk_count=0. 새 판은 적재에 성공했을 때만 이전 자료를 superseded로 바꾼다. 실패하면 옛 판을 그대로 쓰고 supersedes_id도 비운다. |

| 필드 | 위치 | 타입 | 필수 | 빈값 | 제약 | 설명 |
| --- | --- | --- | --- | --- | --- | --- |
| `file` | 폼 | binary | 필수 | 빈 파일 허용 | 코드의 별도 확장자·형식·크기 제한 없음 | 파일명이 title, 없으면 자료 |
| `doc_type` | 폼 | string | 필수 | 불가 | notice·schedule·menu·policy·consult_timetable·law·public_data | 자료 유형 |
| `visibility` | 폼 | string | 필수 | 불가 | staff·parents·all | 공개 범위 |
| `classroom_ids[]` | 폼 | string[](UUID) | 선택 | 생략 가능 | 기본 [], 담임은 현재 담당 반 | 비우면 원 전체 |
| `effective_from` | 폼 | date | 필수 | 불가 | YYYY-MM-DD, 미래 날짜 허용 | 적용 시작일 |
| `replaces_document_id` | 폼 | string(UUID) | 선택 | 생략 가능 | 범위 안 active 문서 | 이전 판 |
| `document` | 응답 | object | 항상 | 불가 | 전체 칸은 3.23 참고 | ID·적재 상태·조각 수·error |

예시는 multipart 각 부분의 이름·값을 줄여 썼다. 시드 식단표와 바이트가 같아 200이다. 같은 기관의 파일 바이트 SHA-256만 비교하므로 이름·유형·공개 범위가 달라도 기존 자료를 반환한다. 중복 검사 뒤에 이전 판 상태를 검사한다.

```http
POST /api/v1/documents
Content-Type: multipart/form-data; boundary=demo
[file: filename="식단표.txt", Content-Type: text/plain, 내용="점심: 카레라이스, 채소와 과일"]
[doc_type=menu, visibility=all, effective_from=2026-11-18]
HTTP/1.1 200 OK
{"document": {"id": "00000000-0000-4000-8000-000000000b01", "title": "가상 식단표", "ingest_status": "succeeded", "effective_from": "2026-11-08", "chunk_count": 1}}
```

| HTTP | `code` | 조건 |
| --- | --- | --- |
| 401 | `UNAUTHENTICATED` | 토큰 없음·만료·무효 |
| 403 | `FORBIDDEN_ROLE` | 허용하지 않은 역할 |
| 404 | `NOT_FOUND` | 없거나 기관·반·소유 범위 밖 |
| 409 | `INVALID_TRANSITION` | 이전 문서가 active 아님 |
| 422 | `VALIDATION_FAILED` | 필수 칸·타입·허용 값·길이가 맞지 않음 |

### 3.23 자료 목록·상세 — `GET /api/v1/documents`, `GET /api/v1/documents/{document_id}`

| 칸 | 내용 |
| --- | --- |
| ① 호출 목적 | 교직원이 자료 목록과 자료별 적재 상태·오류를 본다(FR-13). |
| ② 요청 헤더 | `Authorization`(필수), `X-Request-ID`(권장). |
| ③ 경로·쿼리 | 목록은 page·size·sort, 상세는 document_id(UUID). |
| ④ 요청 본문 | 없음. |
| ⑤ 검증·권한 | teacher·director만. 같은 기관 안에서 원 전체 자료와 현재 담당 반이 대상인 자료를 본다. 원장은 반 제한 없이 본다. visibility 값으로 교직원 조회를 막지는 않는다. |
| ⑥ 정상 응답 | 목록 200 + items[]·total·page·size, 상세 200 + document. 적재 실패도 조회는 200. |
| ⑦ 오류 응답 | 아래 오류 표. |
| ⑧ 실행 규칙 | 생성 시각으로 정렬 뒤 쪽을 나눈다. 모의 구현은 superseded 자료도 목록에 남기고 conflicts는 항상 []다. status와 ingest_status는 별개이며 실패 파일도 status=active일 수 있다. |

| 필드 | 위치 | 타입 | 필수 | 빈값 | 제약 | 설명 |
| --- | --- | --- | --- | --- | --- | --- |
| `document_id` | 상세 경로 | string(UUID) | 필수 | 불가 | 조회 범위 안 | 접수 응답의 document.id |
| `page`·`size` | 쿼리 | integer | 선택 | 불가 | 기본 1·20, page ≥ 1, size 1~100 | 쪽 나누기 |
| `sort` | 쿼리 | string | 선택 | 불가 | `-created_at`(기본)·`created_at` | 내림차순·오름차순 |
| `document.id`·`title`·`doc_type`·`visibility`·`classroom_ids[]` | 상세 응답 | UUID·string·UUID[] | 항상 | 빈 classroom_ids 가능 | 목록 items[]도 같은 모양 | 자료 이름·종류·공개 범위·대상 반 |
| `document.effective_from`·`effective_to`·`supersedes_id` | 상세 응답 | date·UUID | 항상 | effective_to·supersedes_id는 null 가능 | 새 판에만 이전 문서 ID | 적용 기간·판 연결 |
| `document.status`·`ingest_status` | 상세 응답 | string | 항상 | 불가 | status는 모의 active·superseded; ingest_status는 queued·running·succeeded·failed | 사용 상태·적재 진행 |
| `document.chunk_count`·`conflicts[]`·`error` | 상세 응답 | integer·object[]·object | 항상 | error는 null 가능 | 조각 수; 오류는 {code, message} | 실패면 UPSTREAM_UNAVAILABLE; 충돌 판별은 모의 구현에 없음 |
| `total`·`page`·`size` | 응답 | integer | 항상 | 불가 | 전체 건수·요청한 쪽·크기 | 목록 공통 칸 |

```http
GET /api/v1/documents?size=1
HTTP/1.1 200 OK
{"items": [{"id": "00000000-0000-4000-8000-000000000b01", "title": "가상 식단표", "status": "active", "ingest_status": "succeeded"}], "total": 3, "page": 1, "size": 1}
GET /api/v1/documents/00000000-0000-4000-8000-000000000b01
HTTP/1.1 200 OK
{"document": {"id": "00000000-0000-4000-8000-000000000b01", "title": "가상 식단표", "doc_type": "menu", "visibility": "all", "classroom_ids": [], "effective_from": "2026-11-08", "effective_to": null, "status": "active", "ingest_status": "succeeded", "supersedes_id": null, "conflicts": [], "chunk_count": 1, "error": null}}
```

| HTTP | `code` | 조건 |
| --- | --- | --- |
| 401 | `UNAUTHENTICATED` | 토큰 없음·만료·무효 |
| 403 | `FORBIDDEN_ROLE` | 허용하지 않은 역할 |
| 404 | `NOT_FOUND` | 없거나 기관·반·소유 범위 밖 |
| 422 | `VALIDATION_FAILED` | 필수 칸·타입·허용 값·길이가 맞지 않음 |


## 4. 검증과 권한 규칙

### 4.1 형식 검사(422)와 서버 검사(403·404·409)를 나눈다

| 검사 | 어디서 | 실패하면 | 예 |
| --- | --- | --- | --- |
| 형식: 타입·허용 값·길이·날짜 형식 | Pydantic(`Literal`·`Field`) | 422 `VALIDATION_FAILED` | `type = "medication"`, `body` 2,001자 |
| 본문 안에서 함께 와야 하는 칸 | Pydantic `model_validator` | 422 | `hold`인데 `hold_until` 없음 |
| 역할 | 서버(인증 의존성) | 403 `FORBIDDEN_ROLE` | 학부모가 카드 결정 |
| 소유·범위(기관·반·내 아이) | 서버(DB 조회) | 404 `NOT_FOUND` | 다른 반 카드, 남의 아이 |
| 상태·판·DB 값이 필요한 조건 | 서버(DB 조회) + DB 제약 | 409 | 판이 다름, 회신 전 완료, 학부모 미확인 완료에 이유 없음 |

DB 값을 봐야 아는 조건은 Pydantic에 넣지 않는다. 승인·확인 여부를 본문 값만 믿고 통과시키지 않기 위해서다(가이드 21쪽).

```python
# schemas.py — 형식만 본다. 여기서 걸리면 422
class CardDecision(BaseModel):
    version: int = Field(ge=1)
    decision: Literal["approve", "edit_approve", "reject", "hold", "resume", "dismiss", "complete", "escalate"]
    reason_code: Literal["wrong_fact", "tone", "missing_info", "privacy", "policy",
                         "slot_unavailable", "room_unavailable", "other"] | None = None
    reason_text: str | None = Field(default=None, min_length=1, max_length=500)
    hold_until: date | None = None
    edited_content: dict | None = None

    @model_validator(mode="after")
    def fields_for_decision(self):
        if self.decision in {"reject", "dismiss"} and self.reason_code is None:
            raise ValueError("reason_code")
        if self.decision == "hold" and (self.hold_until is None or self.reason_text is None):
            raise ValueError("hold_until, reason_text")
        if self.reason_code == "other" and self.reason_text is None:
            raise ValueError("reason_text")
        return self
```

```python
# routes.py — 권한·범위·상태는 서버가 DB로 확인한다
@router.post("/cards/{card_id}/decisions")
def decide(card_id: UUID, body: CardDecision, user: User = Depends(current_staff)):
    card = load_card_in_scope(card_id, user)              # 다른 기관·반이면 404
    if card.kind == "director_report" and user.role != "director":
        raise ApiError(403, "FORBIDDEN_ROLE")
    if body.version != card.version:
        raise ApiError(409, "CARD_VERSION_CONFLICT", current_version=card.version)
    request = card.request
    if body.decision == "complete":
        if request.type != "complaint" or request.status != "sent_or_booked":
            raise ApiError(409, "INVALID_TRANSITION")
        if request.parent_confirmed_at is None and body.reason_text is None:
            raise ApiError(409, "REASON_REQUIRED")       # DB 트리거도 한 번 더 막음
    return apply_decision(card, request, body, user)     # 같은 판 두 번이면 DB 유니크 → 409 ALREADY_DECIDED
```

### 4.2 역할별 범위

| 역할 | 볼 수 있는 것 | 할 수 있는 것 |
| --- | --- | --- |
| 학부모 | 자기가 보낸 요청, 내 아이의 보낸 알림장, 자기 알림 | 요청 만들기·대화·시간 체크·'확인했어요'·알림 읽음 |
| 담임 | 우리 반 요청·카드(대체 담임은 `classroom_staff.valid_from~valid_to` 기간 안), 재배정받은 카드, 우리 반 알림장, 원 자료 | 카드 결정(원장 보고 카드 제외)·위험 등급 다시 분류·상담 확정·알림장·자료 올리기·자기 규칙 결정 |
| 원장·원감 | 원 전체 | 카드 결정(원장 보고 카드 포함)·원장 지시·재배정·원장 현황·자료 올리기 |

모든 조회와 변경은 토큰의 `org`로 먼저 거르고, 그다음 반·사람 범위를 본다. 범위 밖 자원은 403이 아니라 404로 답하고 `events`에 `permission_denied`로 남긴다(DB 설계서 4.4). 이 규칙은 AI 보안 가드레일 문서(T52)의 권한표와 같아야 한다.

## 5. Tool 정의와 호출 흐름

### 5.1 REST API와 Tool

| 구분 | REST API | Tool (Function Calling) |
| --- | --- | --- |
| 부르는 쪽 | 화면(앱·웹) | 에이전트(감독·자료·기억·검사 AI, 코드) |
| 부르는 법 | HTTP 메서드 + 경로 | 도구 이름 + JSON 인자 |
| 권한 | JWT의 역할·기관·반 | 에이전트별 허용 목록 + 요청한 사용자의 권한(5.3) |
| 이 문서에 적는 것 | 요청·응답·상태 코드(2·3장) | 입력·출력·실패 처리·실행 조건(5.4) |

에이전트가 만든 인자도 사용자 입력처럼 다룬다. 도구 안에서 REST API와 같은 Pydantic 검사와 범위 검사를 한 번 더 한다. 도구의 이름·인자는 계약표 4장과 팀 자체 30문항 v0.5가 기준이다.

### 5.2 공통 출력 형식

모든 도구는 성공과 실패를 같은 모양으로 돌려준다. 에이전트는 `ok`로 성공을 가르고, 실패면 `retryable`로 다시 부를지 정한다.

```json
{ "ok": true,
  "data": { "card_id": "00000000-0000-4000-8000-000000000802" },
  "trace_id": "6b0f1c2e-9a7d-4c1e-8f3a-2d5b7e9c1a40" }

{ "ok": false,
  "error": { "code": "UPSTREAM_UNAVAILABLE", "message": "법령 API가 10초 안에 응답하지 않음", "retryable": true },
  "trace_id": "6b0f1c2e-9a7d-4c1e-8f3a-2d5b7e9c1a40" }
```

`trace_id`는 그 요청을 만든 API 호출의 `X-Request-ID`와 같다. 도구 호출은 모두 `events`에 `tool_called` 또는 `tool_failed`로 남고, `detail`에 도구 이름·`trace_id`·걸린 시간·실패 코드를 넣는다.

**도구 실패 코드**

| `code` | `retryable` | 언제 |
| --- | --- | --- |
| `TOOL_TIMEOUT` | 참 | 도구가 30초 안에 끝나지 않음(6.1) |
| `UPSTREAM_UNAVAILABLE` | 참 | 모델·외부 API(법령·기상) 장애, 429·5xx |
| `SAVE_FAILED` | 참 | DB 저장이 일시적으로 실패(연결 끊김·잠금 대기 초과). 30문항 F04의 `save_failed` |
| `NOT_FOUND` | 거짓 | 대상이 없거나 이 요청의 기관·반 밖 |
| `VALIDATION_FAILED` | 거짓 | 인자 형식이 틀림(허용 밖 `doc_type`·`topic_key` 등) |
| `FORBIDDEN_SCOPE` | 거짓 | 이 에이전트에 허용되지 않은 도구, 또는 요청한 사용자가 못 하는 일 |
| `SLOT_TAKEN` · `SLOT_NOT_CHOSEN` | 거짓 | 상담 확정 충돌(3.4와 같음) |
| `INVALID_TRANSITION` | 거짓 | 지금 상태에서 할 수 없는 일(예: 끝난 요청에 카드 만들기) |

### 5.3 도구를 실행하기 전에 서버가 확인하는 네 가지

| 확인 | 방법 | 실패하면 |
| --- | --- | --- |
| ① 에이전트 허용 목록 | 5.4의 '부르는 AI' 열에 없는 도구는 부르지 못함. 이 열은 다섯 에이전트로 나눈 뒤(T43)부터 적용한다. 그 전 단일 에이전트(T29)는 에이전트가 하나라 `book_slot`을 뺀 도구를 모두 부른다(30문항이 `find_consult_slots`·`search_documents` 직접 호출을 채점) | `FORBIDDEN_SCOPE` |
| ② 요청한 사용자의 권한 | 학부모 요청에서 나온 호출은 그 학부모가 볼 수 있는 범위만. 교직원 쪽 도구(`book_slot`)는 담임의 확정 API에서만 부름 | `FORBIDDEN_SCOPE` |
| ③ 데이터 소유권 | 기관·반·학부모 ID는 모델 인자가 아니라 지금 요청에서 백엔드가 채움(계약표 4장 '(백엔드)' 값). 모델이 다른 ID를 넣어도 범위 밖이면 거부 | `NOT_FOUND` |
| ④ 사람 승인 상태 | 학부모에게 나가는 일(회신 발송·예약 확정·알림장 발송)은 도구로 하지 않는다. 담임의 결정 API가 승인 기록(`approvals`)을 남긴 뒤에만 일어난다 | 도구 목록에 없음 |

### 5.4 도구 목록과 실패 후 처리

계약표 4장의 '실패 코드' 칸을 채운 표다. '실패 후 처리'는 기본값이고, 에이전트별 세부 행동은 영민(T14)이 정한다(계약표 6장 ④). 기본값은 `retryable`이면 1번 다시 부르고, 그래도 실패하거나 `retryable`이 거짓이면 사람 카드로 넘기는 것이다.

| 도구 | 부르는 AI | 실행 조건 | 성공 `data` | 실패 코드 | 실패 후 처리(기본) |
| --- | --- | --- | --- | --- | --- |
| `route_request` | 감독 | 요청이 `received`·`classified` | 분류 결과를 저장 | `UPSTREAM_UNAVAILABLE`·`SAVE_FAILED`(참), `INVALID_TRANSITION`(거짓) | 1번 다시 → 실패면 담당 없는 사람 카드(받은함 '미배정') |
| `create_card` | 감독·자료 | 요청이 끝나지 않음 | `card_id` | `SAVE_FAILED`(참), `VALIDATION_FAILED`·`INVALID_TRANSITION`(거짓) | 1번 다시 → 실패면 학부모에게 '말씀하신 내용은 받았는데 선생님께 넘기는 중에 저장 오류가 났어요. 확인이 늦어질 수 있으니 급하시면 원으로 전화 주세요'라고 솔직히 안내('선생님께 전달했어요'라고 하지 않음, 30문항 YC-F04). 요청은 `POST /requests` 때 이미 저장돼 '내 요청' 화면에 '접수됨'으로 보이므로 '접수가 안 됐어요'라고도 하지 않음. 카드는 서버 점검 작업이 '미배정'으로 다시 올림(6.3) |
| `notify_staff` | 감독 | 카드가 있음 | `notification_id` | `SAVE_FAILED`(참), `NOT_FOUND`(거짓) | 1번 다시 → 실패해도 카드는 받은함에 남는다. 긴급·판단 필요 카드면 `warnings[]`에 `notify_failed`를 붙여 카드에서 눈에 띄게 하고 이력에 남김 |
| `search_documents` | 자료 | 요청 기관 자료만, 학부모면 원 전체 + 아이 반 자료 | `chunks[]` | `TOOL_TIMEOUT`·`UPSTREAM_UNAVAILABLE`(참), `VALIDATION_FAILED`·`NOT_FOUND`(거짓) | 1번 다시 → 실패하거나 근거가 없으면 추측하지 않고 담임 카드(`no_evidence`) |
| `get_law_article` | 자료 | 법령 이름·조문이 있음 | `text`, `source_url`, `fetched_at` | `UPSTREAM_UNAVAILABLE`(참), `NOT_FOUND`(거짓) | 1번 다시 → 실패면 법령 인용 없이 초안, 카드에 '법령 확인 못 함' 표시 |
| `get_memory` | 기억 | 주인이 요청 담당자 | `memories[]`, `active_rules[]` | `SAVE_FAILED`(참) | 1번 다시 → 실패면 기억 없이 진행 |
| `propose_rule` | 기억 | 같은 이유 코드 3번 | `rule_id`(이미 있으면 기존 ID) | `SAVE_FAILED`(참), `VALIDATION_FAILED`(거짓) | 1번 다시 → 실패면 제안 안 함(다음에 다시 셈) |
| `check_draft` | 검사 | 초안이 있는 카드·알림장 | 검사 결과를 저장 | `TOOL_TIMEOUT`·`UPSTREAM_UNAVAILABLE`(참) | 1번 다시 → 실패면 '검사 못 함' 표시하고 사람 카드 |
| `return_to_step` | 검사 | `check_attempts` < 2 | `attempt` | `INVALID_TRANSITION`(거짓, 3번째) | 3번째는 오류 대신 사람 카드로 넘김(FR-08) |
| `find_consult_slots` | 코드 | 상담 요청, 담임 일정이 있음 | `slots[]`(회차마다 최대 3개) | `TOOL_TIMEOUT`·`SAVE_FAILED`(참), `NOT_FOUND`(거짓) | 1번 다시 → 실패면 시간을 지어내지 않고 '지금 확인할 수 없음' 안내(30문항 YC-F01). 빈 목록이면 다른 날을 묻거나 담임 카드 |
| `request_consultation` | 감독 | 상담 요청이 `needs_info` | `slots[]`, `request_status` | `SAVE_FAILED`(참), `INVALID_TRANSITION`(거짓) | 1번 다시 → 실패면 학부모에게 화면에서 다시 고르게 안내 |
| `book_slot` | 코드 | 담임 확정 API 안에서만 | `booking_id` | `SLOT_TAKEN`·`SLOT_NOT_CHOSEN`(거짓), `SAVE_FAILED`(참) | 담임 화면에 409를 그대로 보여 주고 후보 다시 내기 안내 |
| `get_my_requests` | 감독 | 요청한 학부모 본인 것만 | `items[]` | `SAVE_FAILED`(참) | 1번 다시 → 실패면 '요청 목록 화면에서 확인' 안내 |
| `get_daily_note` | 감독 | 요청한 학부모의 아이, 보낸 알림장만 | `note` 또는 없음 | `NOT_FOUND`(거짓) | 없으면 '아직 안 보냄' 안내 |
| `find_saved_answer` | 감독 | 근거 문서가 모두 최신 | `saved_answer_id`, `similarity`, `sources_current` | `TOOL_TIMEOUT`(참) | 실패하면 원에 남은 답 없이 평소대로 처리 |

### 5.5 도구 정의 예시 — `create_card`

모델에게 보이는 정의다. 백엔드가 채우는 값(`request_id`·`kind`·`assignee_id`)은 정의에 넣지 않는다(계약표 4장). `description`은 모델이 언제 이 도구를 쓸지 판단하는 근거라 구체적으로 쓴다.

```json
{
  "name": "create_card",
  "description": "학부모 문의·민원을 담임(또는 원장) 받은함에 사람 확인 카드로 올린다. 자동 회신 대신 쓴다. 근거가 없거나 문서끼리 다르거나 위험해 보이면 반드시 이 도구로 사람에게 넘긴다.",
  "parameters": {
    "type": "object",
    "properties": {
      "request_type": { "type": "string", "enum": ["inquiry", "complaint"] },
      "topic_key": { "type": "string", "enum": ["safety", "meal", "teacher", "belongings", "fee", "pickup_bus",
                                                 "peer_conflict", "health_hygiene", "photo_record", "communication", "other"] },
      "summary": { "type": "string", "maxLength": 300 },
      "urgency": { "type": "string", "enum": ["normal", "urgent"] },
      "escalate_to_director": { "type": "boolean" }
    },
    "required": ["request_type", "topic_key", "summary", "urgency", "escalate_to_director"],
    "additionalProperties": false
  }
}
```

### 5.6 호출 흐름

요청 하나가 거치는 순서다. 모든 단계가 같은 `trace_id`를 이어 써서 로그와 LangSmith에서 한 번에 추적된다.

| 순서 | 누가 | 하는 일 | 쓰는 도구·API |
| --- | --- | --- | --- |
| 1 | 화면 → API | 인증, 입력 형식 검사, 요청 저장, 202 | `POST /requests` |
| 2 | 감독 AI | 유형·급한 정도·위험 등급·주제 분류, 빠진 정보 확인 | `route_request` |
| 3 | 자료 AI · 코드 · 기억 AI | 문의는 근거 검색과 초안, 상담은 후보 계산, 거절 이력은 기억 조회 | `search_documents`·`get_law_article`·`find_consult_slots`·`get_memory` |
| 4 | 검사 AI | 출처·날짜·대상·누락·민감정보 대조, 최대 2번 앞 단계로 돌려보냄 | `check_draft`·`return_to_step` |
| 5 | 감독 AI | 사람 확인 카드 생성, 긴급·3번째 반복 민원이면 원장 보고 | `create_card`·`notify_staff` |
| 6 | 흐름 멈춤 | 카드가 사람 결정을 기다림(LangGraph interrupt, 체크포인트는 `cards.graph_thread_id`) | — |
| 7 | 담임·원장 → API | 결정. 서버가 역할·범위·판·상태를 확인하고 승인 기록을 남김 | `POST /cards/{id}/decisions`·`bookings` |
| 8 | 서버 | 회신 발송·예약 확정·알림, 이력 기록 | `book_slot`(확정 API 안), 알림 발송기 |

### 5.7 업무 흐름 세 개 — 경로·도구·권한·DB 상태

**사람에게 넘기고 자동 답변하지 않는 기준.** 긴급(`risk_level = urgent`)·판단 필요(`uncertain`) 민원, 근거 없음(`no_evidence`), 문서 충돌, 검사 2번 실패, 권한 밖이면 학부모에게 나가는 답은 없고 초안 없는 사람 카드로 넘긴다. 권한 밖 자료는 읽지 않으며, 카드도 현재 사용자의 범위 안에서만 만든다. 학부모에게 나가는 모든 답은 담임 결정 API가 승인 기록(`approvals`)을 남긴 뒤에만 나간다(5.3 ④). 접수 안내·정보 되묻기는 답변 발송과 구분한다. 기존의 원에 남은 답 바로 응답(T04 합의 7)과의 차이는 시험 기록에 남겼다.

아래 API 경로 앞에는 모두 `/api/v1`을 붙인다. 도구의 전체 입력·출력은 계약표 4장, 실행 조건·실패 코드는 5.4를 따른다. 도구 호출은 설계 계약이며 모의 API는 같은 흐름을 메모리에서 흉내 낸다. DB 제약은 T09 설계 기준이다.

**문의 답변**

| 단계 | 누가 | API·도구 | 입력 → 출력 | 권한(누가 할 수 있나) | DB 상태 변화(`requests.status`·`cards.status`·제약) | 실패하면 |
| --- | --- | --- | --- | --- | --- | --- |
| 접수·분류 | 학부모·감독 AI | `POST /requests`, `route_request` | `client_request_id`, `type=inquiry`, `body`, `child_id` → `request { id, status, stream_url }` | 학부모 본인 아이, 기관·반은 서버가 채움 | 요청 `received → classified → assigned`, `(requester_id, client_request_id)` 유니크 | 역할 403 `FORBIDDEN_ROLE`, 남의 아이 404 `NOT_FOUND`. 같은 제출은 200 + 기존 요청 |
| 근거·검사 | 자료·검사 AI | `search_documents`, `check_draft` | `kindergarten_id`, `doc_type`, `query` → `chunks[]`; `card_id` → 검사 결과 | 기관·아이 반 자료만, AI 허용 목록(5.3 ①) | `cards.kind=reply_draft`, 카드 `pending`, `cards.draft`·`card_evidence`·`check_result` 저장 | 근거 없음·충돌·검사 실패면 위 기준으로 초안 없이 사람에게 넘김 |
| 사람 카드·알림 | 감독 AI | `create_card`, `notify_staff`, `GET /cards/{card_id}` | `request_type`, `topic_key`, `summary`, `urgency`, `escalate_to_director=false` → `card_id`; `card_id`, `reason` → `notification_id` | 담당 담임, 담당 없으면 미배정 | 요청 `awaiting_review`, 카드 `pending`(담당 없으면 `unassigned`), `cards.due_at` 저장 | 저장 실패는 6.3, 알림 실패는 5.4의 `notify_failed` 규칙 |
| 승인·회신 | 담임 | `POST /cards/{card_id}/decisions`, `GET /requests/{request_id}` | `version`, `decision=approve` 또는 `edit_approve`, `edited_content` → 카드·요청 상태, 학부모 회신 | 담임 승인 후 발송(5.3 ④) | 요청 `approved → sent_or_booked`, 카드 `approved → done`, `approvals (card_id, card_version)` 유니크 | 409 `CARD_VERSION_CONFLICT`·`ALREADY_DECIDED`. 본문 없는 승인 409 `INVALID_TRANSITION` |

**상담 예약**

| 단계 | 누가 | API·도구 | 입력 → 출력 | 권한(누가 할 수 있나) | DB 상태 변화(`requests.status`·`cards.status`·제약) | 실패하면 |
| --- | --- | --- | --- | --- | --- | --- |
| 접수·후보 | 학부모·감독 AI·코드 | `POST /requests`, `route_request`, `find_consult_slots` | `type=consultation`, `body`, `child_id` 등 → 요청; `teacher_id`, `date` → `slots[]`(최대 3개) | 본인 아이·담임 일정, 기관·반은 서버가 확인 | 요청 `received → classified → assigned → needs_info`, `consult_slots` 카드 `pending`, 후보 `proposed` | 후보 조회는 1번 다시. 그래도 실패하면 시간을 지어내지 않음(5.4) |
| 가능한 시간 체크 | 학부모·감독 AI | `POST /requests/{request_id}/slot-choices`; 대화에서는 `request_consultation` | 화면 `slot_ids[]`; 도구 `teacher_id`, `date`, `time`, `topic?` → `slots[]`, 요청 상태 | 요청한 학부모만. 예약 확정 권한은 없음 | 후보 `chosen_by_parent` + `chosen_at`, 요청 `awaiting_review`, 카드 `pending` 유지 | 맞는 시간 없으면 `none_fit` + `preferred_times`, 후보 다시 계산. 24시간 지나면 `proposed`로 풀림 |
| 담임 확정 | 담임·코드 | `POST /cards/{card_id}/bookings`, `book_slot` | `version`, `slot_id`; 도구 `slot_id`, `confirmed_by` → `booking_id`, API `booking { id, room, period }` | 그 반 담임만. 원장은 대신 확정 못 함 | `approvals` 저장 후 요청 `approved → sent_or_booked`, 카드 `done`, 예약·선택 후보 `confirmed`. 요청당 확정 예약 하나, 상담실·담임 시간 배제 제약 | 409 `SLOT_NOT_CHOSEN`·`SLOT_TAKEN`·`CARD_VERSION_CONFLICT`. 충돌이면 후보 다시 내기 안내 |

**긴급 민원 사람 인계**

| 단계 | 누가 | API·도구 | 입력 → 출력 | 권한(누가 할 수 있나) | DB 상태 변화(`requests.status`·`cards.status`·제약) | 실패하면 |
| --- | --- | --- | --- | --- | --- | --- |
| 분류·카드 두 장 | 학부모·감독 AI | `POST /requests`, `route_request`, `create_card` | `type=complaint` → `risk_level=urgent`, `risk_category`; `escalate_to_director=true` → `card_id` | 학부모 본인 아이, 위험 등급은 감독 AI 분류 후 사람이 판단 | 요청 `received → classified → assigned → escalated`, 초안 없는 `reply_draft` + `director_report` 카드 `pending`, 원장 보고 담당 필수 | 분류·저장 실패면 재시도 후 사람 인계(5.4·6.3). 자동 회신 없음 |
| 알림·상세 | 감독 AI·교직원 | `notify_staff`, `GET /cards`, `GET /cards/{card_id}` | `card_id`, `reason` → `notification_id`; 상세 `warnings[]`·`timeline[]` | 담임은 우리 반, 원장은 원 전체 | 요청 `escalated` 유지, 알림 `dedupe_key` 유니크·`deliver_after`(6.6) | 알림 실패해도 카드 유지, 긴급·판단 필요 카드에 `notify_failed`, 실패 이력 |
| 사람 지시·재분류 | 원장·담임 | `POST /cards/{card_id}/instructions`, `POST /cards/{card_id}/reclassify` | 지시 `version`, `instruction` → 상태; 재분류 `version`, `risk_level`, `risk_category`, `reason` → 요청 | 지시는 원장만, 다시 분류는 담임·원장(원장 보고 카드는 원장만) | 지시: `approvals.decision=instruct`, 원장 카드 `done`, 요청 `awaiting_review`. 판단 필요도 같은 인계 경로, 재분류 긴급이면 `escalated` | 403 `FORBIDDEN_ROLE`, 409 `INVALID_TRANSITION`·`CARD_VERSION_CONFLICT` |
| 직접 작성·승인 | 담임 | `POST /cards/{card_id}/decisions` | `version`, `decision=edit_approve`, `edited_content.text` → 회신 | 원장 지시 뒤에도 담임 승인 기록 필요 | 요청 `approved → sent_or_booked`, 회신 카드 `done` | 초안·직접 쓴 본문이 없거나 판단 필요가 남으면 409 `INVALID_TRANSITION` |

**도구 이름 대조.** API 5.4와 30문항 2장의 `search_documents`·`find_consult_slots`·`request_consultation`·`get_my_requests`·`create_card` 5개는 이름이 같다. T12(`origin/ju-t`)는 화면·API 필드로 적었고 도구 이름은 직접 쓰지 않는다. 따라서 세 문서의 이름이 모두 같다고 판정할 수 없으며, T12 화면과 API의 연결은 6.7에 적었다. 30문항에 없는 나머지 10개 도구도 이름 대조 대상이 없다.

## 6. 실행 규칙

### 6.1 타임아웃

| 대상 | 기준 | 넘으면 |
| --- | --- | --- |
| API 응답(조회·결정·접수) | 10초 | 503 `UPSTREAM_UNAVAILABLE` 또는 500. AI 처리는 202로 떼어 내서 이 시간에 들어가지 않음 |
| 모델 호출 1번 | 30초 | 재시도 대상(6.2) |
| 도구 호출 1번 | 30초(외부 법령·기상 API는 그 안에서 10초) | `TOOL_TIMEOUT`(`retryable` 참) |
| 요청 하나의 AI 처리 전체(2~5단계) | 3분 | 처리를 멈추고 초안 없는 사람 카드로 넘김. 넘긴 이유(`ai_timeout`)는 이력 `events.detail.handoff_reason`에 남김 |
| SSE 연결 | 처리 끝(`done`·`error`) 또는 5분 | 서버가 닫음. 화면은 상세를 다시 불러 맞춤 |

### 6.2 재시도

| 대상 | 다시 하는 것 | 다시 하지 않는 것 | 횟수·간격 |
| --- | --- | --- | --- |
| 모델 호출 | 타임아웃·429·5xx | 400·401·403·422(요청이 틀림) | 최대 2번, 1초 → 2초(지수 백오프) |
| 도구 호출 | `retryable = true` | `retryable = false` | 1번(계약표 6장 ④) |
| 알림 발송 | 발송 실패 | 받는 사람 없음 | 최대 3번(`notifications.attempts`, FR-12) |
| 화면의 결정·확정 | 응답이 끊김 | 4xx | 먼저 카드·요청 상세로 상태를 확인한 뒤 같은 `version`으로 1번. 이미 처리됐으면 409 `ALREADY_DECIDED`로 막힘 |

### 6.3 202로 접수하는 작업의 상태 조회

202는 "접수했지만 처리는 끝나지 않았다"는 뜻이다. 세 가지 모두 진행·성공·실패를 조회할 수 있다. 작업이 실패해도 조회 요청은 성공했으므로 200이고, 실패는 상태 값으로 알린다.

| 접수 API | 조회 | 진행 중 | 성공 | 실패 |
| --- | --- | --- | --- | --- |
| 요청 만들기 | `GET /requests/{id}` + 스트림 | `received`·`classified`·`assigned` | `needs_info`(학부모 차례) 또는 `awaiting_review`(카드 생김) | 재시도 뒤에도 실패하면 초안 없는 사람 카드로 넘기고 `awaiting_review`. 넘긴 이유(`ai_failed`)는 이력 `events.detail.handoff_reason`, 교직원 스트림에 `error` 이벤트. 요청은 버리지 않음 |
| 알림장 초안 | `GET /daily-notes/drafts/{input_id}` | `draft_status = queued·running` | `succeeded`. 아이별 초안은 `GET /daily-notes?classroom_id=&date=`로 받음(계약표 2.2) | `failed` + `error { code, message }`(이유는 `events`의 `tool_failed`) |
| 자료 올리기 | `GET /documents/{document_id}` | `ingest_status = queued·running` | `succeeded` + `chunk_count`(조각 수), 충돌이면 `status = conflict_pending` + `conflicts[]` | `failed` + `error { code, message }` |

**카드가 끝내 안 생긴 요청.** 요청은 `POST /requests`에서 먼저 저장되므로, AI가 카드 만들기(`create_card`)까지 실패하거나 처리 중에 멈춰도 요청은 남아 있다. 서버 점검 작업이 1분마다 진행 중 상태(`received`·`classified`·`assigned`)로 5분 넘게 카드가 없는 요청을 찾아, 초안 없는 카드를 담당 없이 만들고(받은함 '미배정') 요청을 `awaiting_review`로 바꾼다. 넘긴 이유 `card_missing`은 이력 `events.detail.handoff_reason`에 남긴다. 학부모 화면에는 그동안에도 '접수됨'이 보이고, 채팅 안내도 '받았지만 선생님 확인이 늦어질 수 있음'이라 화면과 말이 어긋나지 않는다. 모의 API는 이 점검 작업을 돌리지 않고, 실제 서버의 백그라운드 워커에서 돈다.

```json
{ "input_id": "00000000-0000-4000-8000-000000000a01", "draft_status": "failed",
  "error": { "code": "UPSTREAM_UNAVAILABLE", "message": "모델 응답이 없어 초안을 만들지 못했어요." } }
```

### 6.4 중복·동시 실행 방지

| 상황 | 막는 것 | 결과 |
| --- | --- | --- |
| 같은 요청을 두 번 제출 | `requests (requester_id, client_request_id)` 유니크 | 200 + 처음 요청 |
| 두 사람이 같은 카드를 동시에 결정 | 카드 `version` 비교 + `approvals (card_id, card_version)` 유니크 | 늦은 쪽 409 `CARD_VERSION_CONFLICT`·`ALREADY_DECIDED` |
| 같은 시간 상담 두 건 확정 | 상담실·담임 배제 제약, 요청당 확정 예약 하나 | 늦은 쪽 409 `SLOT_TAKEN` |
| 같은 알림 두 번 | `notifications.dedupe_key` 유니크 | 한 번만 저장·발송 |
| 같은 규칙 제안 두 번 | `memory_rules` 부분 유니크 | 기존 `rule_id` |
| 반 알림장을 두 사람이 동시에 보냄 | 한 트랜잭션에서 반 단위 잠금 | 먼저 보낸 쪽만 보냄, 늦은 쪽 `sent_count = 0` |

### 6.5 처리 기한(`due_at`) 계산

카드를 만들 때 서버가 계산해 `cards.due_at`에 넣는다(계약표 6장 ⑤, T10 회의 11/18). 시작은 요청 접수 시각이다.

1. 민원 긴급·판단 필요(2시간)는 시작에 2시간을 그냥 더한다. 주말·공휴일에도 센다.
2. 그 밖의 기한(민원 일반·상담 24시간, 문의 4시간)은 시간을 더하다가 토요일·일요일·공휴일에 걸리면 그날을 통째로 건너뛴다.
3. 알림장 묶음은 그날 17:00, 원장 보고는 원래 민원 카드와 같은 기한, 정보 요청·규칙 제안은 기한이 없다(`NULL`).

| 접수 | 기한 종류 | `due_at` |
| --- | --- | --- |
| 화 10:00 | 문의 4시간 | 화 14:00 |
| 금 18:00 | 민원 일반 24시간 | 월 18:00 (금 6시간 + 토·일 건너뜀 + 월 18시간) |
| 토 10:00 | 상담 24시간 | 화 00:00 (토·일 건너뜀 → 월 00:00부터 24시간) |
| 금 23:00 | 민원 긴급 2시간 | 토 01:00 |

공휴일 목록은 MVP 서버 설정(`.env`의 `HOLIDAYS`)으로 관리한다(8장). 기한과 알림은 같은 서버 설정(`HOLIDAYS`·`WORK_HOURS`)을 기준으로 삼는다. 다만 일반 기한은 평일의 시간을 밤에도 세며 `WORK_HOURS`로 자르지 않는다. 근무 시간은 교직원 알림을 미룰 때만 쓴다. 긴급·판단 필요 2시간은 공휴일에도 그대로 센다.

### 6.6 알림 발송 시각(`deliver_after`)

알림을 만들 때 서버가 계산해 `notifications.deliver_after`에 넣는다. 아래 표는 8장의 기본 설정일 때다. 발송기는 `status = 'pending' AND deliver_after <= now()`만 꺼낸다(계약표 6장 ⑬, T10 회의 11/18).

| 받는 사람 · 알림 | 근무 시간(평일 09:00~18:00, 공휴일 제외) 안 | 근무 시간 밖 |
| --- | --- | --- |
| 교직원 · 긴급 민원 중 아이 안전(`risk_category = child_safety`) | 바로 | 바로 |
| 교직원 · 그 밖의 긴급 민원(교직원 위협·법적 조치·개인정보)과 판단 필요 민원 | 바로 | 다음 근무 시작(09:00) |
| 교직원 · 그 밖의 알림(새 카드·보류 재개·잡아 둔 시간 풀림 등) | 바로 | 다음 근무 시작(09:00) |
| 학부모 · 모든 알림 | 바로 | 바로 |

근무 시간 밖 규칙은 교직원이 받는 알림에만 쓴다(기획서 FR-21 '퇴근 뒤 알림은 모아 두고 아이 안전·발열만 바로 보냄'). 학부모 알림은 학부모가 보낸 요청의 진행 소식이라 시간과 상관없이 바로 보낸다. 발열 같은 건강 알림은 투약·귀가(T46)에서 이 표에 더한다. 근무 시간과 바로 보내는 위험 종류는 MVP 서버 설정(`.env`의 `WORK_HOURS`·`IMMEDIATE_RISK_CATEGORIES`)으로 관리한다(8장). 기한과 같은 `HOLIDAYS`로 근무일을 고르고, `WORK_HOURS`의 시작 이상·끝 미만을 근무 시간으로 본다. 위험 종류 설정은 긴급일 때만 적용한다.

#### 6.6.1 공휴일·퇴근 뒤 알림과 지연 예시

아래는 `schedule.py`로 계산한 값이다. 시간대는 모두 한국 표준시(+09:00), 설정은 `HOLIDAYS=2025-12-25`, `WORK_HOURS=09:00-18:00`, `IMMEDIATE_RISK_CATEGORIES=child_safety`다. 12/25가 목요일인 2025년을 예시로 쓴다. 학부모 열은 그 접수 시각에 보낼 알림이 생겼다고 가정한 계산값이다. 이 표의 민원은 접수만으로 학부모 답변·알림을 만들지 않으며, 회신 알림은 승인·발송 시각에 다시 계산한다.

| 상황 | 접수 시각 | 요청 종류·위험 | 교직원 알림 `deliver_after` | 학부모 알림 | 처리 기한 `due_at` | 지연 표시가 켜지는 시각(`is_delayed = due_at < now()`) |
| --- | --- | --- | --- | --- | --- | --- |
| 금요일 퇴근 뒤 | 2025-12-19 금 18:30 | 민원 일반(`complaint`, `normal`) | 12/22 월 09:00 | 발생 즉시(가정: 12/19 18:30) | 12/22 월 18:30 | 12/22 18:30 초과부터 |
| 공휴일 전날 근무 중 | 2025-12-24 수 17:30 | 민원 일반(`complaint`, `normal`) | 12/24 수 17:30 | 발생 즉시(가정: 12/24 17:30) | 12/26 금 17:30 | 12/26 17:30 초과부터 |
| 공휴일 전날 퇴근 뒤 | 2025-12-24 수 18:30 | 민원 일반(`complaint`, `normal`) | 12/26 금 09:00 | 발생 즉시(가정: 12/24 18:30) | 12/26 금 18:30 | 12/26 18:30 초과부터 |
| 아이 안전 긴급, 근무 밖 | 2025-12-19 금 20:00 | 민원 긴급(`urgent`, `child_safety`) | 12/19 금 20:00 | 발생 즉시(가정: 12/19 20:00) | 12/19 금 22:00 | 12/19 22:00 초과부터 |
| 교직원 위협 긴급, 근무 밖 | 2025-12-19 금 20:00 | 민원 긴급(`urgent`, `staff_attack`) | 12/22 월 09:00 | 발생 즉시(가정: 12/19 20:00) | 12/19 금 22:00 | 12/19 22:00 초과부터 |

기한과 같은 시각에는 지연이 아니다. 마지막 사례는 알림이 오기 전에 지연이 켜진다. 이는 긴급 2시간과 교직원 알림 예외가 서로 다른 규칙이기 때문이다. `test_documented_holiday_notification_examples`가 표의 다섯 행과 기한 경계(같은 시각·1마이크로초 뒤)를 고정한다.

### 6.7 대표 사례 대조 — 화면·API·DB가 같은 상태로 보이는지

화면 ID·표시 이름은 T12(`origin/ju-t`, 2026-11-20 조회)를 따른다. API 경로는 `/api/v1`을 생략했다. DB 제약은 T09 설계 기준이며, 아래 시험은 메모리 모의 API 시험이다. 실제 DB 제약 시험은 T09 9.1을 따른다. 전체 실행 환경·결과와 문서 차이는 [T13 시험 기록](T13_시험기록_2026-11-20.md)에 남겼다. 시험 함수는 `tests/integration/api/test_flows.py`에 있다.

**상담 예약 중복 방지**

| 단계 | 화면(T12의 화면 ID·표시 이름) | API | DB(상태·제약) | 권한 | 시험(테스트 함수 이름) |
| --- | --- | --- | --- | --- | --- |
| 후보·체크 | P-04 요청 상세: 시간 체크 → 선생님 확인 중, T-02 카드 상세: 시간 확정 | `GET /requests/{request_id}`, `POST /requests/{request_id}/slot-choices` | 요청 `needs_info → awaiting_review`, 후보 `proposed → chosen_by_parent`, 카드 `pending` | 요청한 학부모만 체크 | `test_consultation_complete_booking_flow` |
| 담임 확정 | T-02 카드 상세: 확정, P-04 요청 상세: 예약 확정 | `POST /cards/{card_id}/bookings`, `version`·`slot_id` → `booking` | 요청 `approved → sent_or_booked`, 카드 `done`, 예약 `confirmed`, `approvals (card_id, card_version)` 유니크 | 그 반 담임만, 원장은 403 `FORBIDDEN_ROLE` | `test_consultation_complete_booking_flow` |
| 같은 시간 충돌 | T-02 카드 상세: 방금 다른 예약이 들어왔어요 · 후보를 다시 만들어요 | 같은 확정 API → 409 `SLOT_TAKEN` | 상담실·담임의 시간 배제 제약, 요청당 `confirmed` 예약 하나. 실패한 카드·후보 상태 유지 | 담임, 같은 범위 재검사 | `test_slot_collision_is_atomic_and_nonoverlap_is_allowed`(순차 충돌). 동시 예약 경합 시험 없음 |

**민원 처리 완료 — 학부모 확인 있음·없음**

| 단계 | 화면(T12의 화면 ID·표시 이름) | API | DB(상태·제약) | 권한 | 시험(테스트 함수 이름) |
| --- | --- | --- | --- | --- | --- |
| 회신·확인 | P-04 요청 상세: 답변 도착 → 확인함 · 선생님이 마무리하고 있어요, T-01 받은함: 확인 필요(처리 완료 대기) | 결정 `approve` 후 `POST /requests/{request_id}/confirm` | 요청 `sent_or_booked` 유지, `requests.parent_confirmed_at` 기록, 알림 `dedupe_key` 유니크 | 담임 승인, 요청한 학부모만 확인 | `test_complaint_approval_confirmation_completion` |
| 확인한 민원 완료 | T-02 카드 상세: 처리 완료, P-04 요청 상세: 완료 | `POST /cards/{card_id}/decisions`, `decision=complete`, `version=2` → `completed` | `approvals.decision=complete`, 요청 `completed`, 카드 `done` | 담임. 회신 전이면 409 `INVALID_TRANSITION` | `test_complaint_approval_confirmation_completion` |
| 미확인 민원 완료 | T-02 카드 상세: 학부모 확인 기다리는 중·처리 완료, 이유 글 필수 | 같은 결정 API, `reason_text` 필수. 없으면 409 `REASON_REQUIRED` | `parent_confirmed_at IS NULL`, `approvals.reason_text` 저장 후 `completed`, 카드 `done`. 트리거 `approvals_unconfirmed_complete_reason` | 담임이 이유를 남김 | `test_unconfirmed_complete_needs_reason_and_overview_counts` |
| 미확인 완료 구분 | D-03 원 현황: 학부모 미확인 완료(`completed_unconfirmed`), 남긴 이유 함께 표시(T53) | `GET /overview` → `completed_unconfirmed` | `director_overview.completed_unconfirmed`: 최근 30일 미확인 완료 민원을 요청별로 셈. 이유는 `approvals.reason_text` | 원장만, 담임은 403 `FORBIDDEN_ROLE` | `test_unconfirmed_complete_needs_reason_and_overview_counts`(건수·권한). 화면 이유 표시 시험 없음 |

**긴급 민원 사람 인계**

| 단계 | 화면(T12의 화면 ID·표시 이름) | API | DB(상태·제약) | 권한 | 시험(테스트 함수 이름) |
| --- | --- | --- | --- | --- | --- |
| 초안 없이 인계 | T-01 받은함: 긴급·확인 필요, T-02 카드 상세: AI 초안 없음, D-01 받은함: 원장 보고 | `POST /requests`, 카드 목록·상세 조회 | 요청 `escalated`, `reply_draft`·`director_report` 카드 `pending`, 위험 종류·원장 보고 담당 필수 | 담임은 우리 반, 원장은 원 전체 | `test_director_report_permission_instructions_reassign`(카드·권한). 초안 없음·승인 전 학부모 답 없음 전용 시험 없음 |
| 원장 지시 | D-02 카드 상세: 지시 남기기, T-02 카드 상세: 확인 필요 | `POST /cards/{card_id}/instructions`, `instruction`·`version` | `approvals.decision=instruct`, `reason_text`=지시, 원장 카드 `done`, 요청 `awaiting_review`, 이력 `instructed` | 원장만. 담임이 원장 보고 결정·지시하면 403 `FORBIDDEN_ROLE` | `test_director_report_permission_instructions_reassign` |
| 판단 필요 재분류 | T-02 카드 상세: 다시 분류 일반/긴급 → 확인 필요 또는 원장 보고 | `POST /cards/{card_id}/reclassify`, `risk_level`·`risk_category`·`reason`·`version` | 요청 `awaiting_review`, 긴급이면 다시 `escalated`, 보고 카드 중복 생성 안 함 | 담임·원장, 원장 보고 카드는 원장만 | `test_reclassify_uncertain_and_escalate` |
| 사람이 쓴 답 승인 | T-02 카드 상세: 직접 답 쓰기 → 승인하고 보내기, P-04 요청 상세: 답변 도착 | `POST /cards/{card_id}/decisions`, `decision=edit_approve`, `edited_content.text` | 승인 기록 뒤 요청 `sent_or_booked`, 회신 카드 `done` | 담임 승인(5.3 ④) | `test_explicit_escalation_and_edit_approval`(일반 민원의 수동 인계). 긴급 민원 회신까지 연결한 시험 없음 |

## 7. API 필드와 DB 컬럼 대응

이름이 다른 곳만 '대응'에 적었다. ID 형식은 DB 설계서 2.0과 같다. 3.7의 화면용 칸은 그 표의 'DB' 열에 적었다.

| API 필드 | DB 컬럼 | 대응 |
| --- | --- | --- |
| `request.id` · `request_id`(경로) | `requests.id` | UUID |
| `client_request_id` | `requests.client_request_id` | 같음 |
| `type` · `body` · `child_id` · `previous_request_id` | `requests.type` · `body` · `child_id` · `previous_request_id` | 같음 |
| `request.status` | `requests.status` | 같음 |
| `request.status_label` | — | 저장하지 않음. T04 2장 표시 이름을 역할에 맞춰 붙임 |
| `request.missing_fields[]` | `requests.missing_fields` | `jsonb` 목록 |
| `request.parent_confirmed_at` | `requests.parent_confirmed_at` | 같음 |
| `request.hold_until` | `cards.hold_until` | 요청의 보류 카드에서 가져옴 |
| 반(요청) | `requests.classroom_id` | API로 받지 않고 `children.classroom_id`에서 채움 |
| `messages[]` | `request_messages` | `sender_type`·`body`·`created_at` |
| `timeline[]` | `events` | `to_status`를 표시 이름으로 바꿈. 학부모용은 상태 변화만 |
| `card.version` · `version`(본문) | `cards.version` | 정수 |
| `decision` · `reason_code` · `reason_text` · `edited_content` | `approvals.decision` · `reason_code` · `reason_text` · `edited_content` | 같음. `approvals.card_version`에 본문 `version` |
| `hold_until`(본문) | `cards.hold_until` | `date` |
| `risk_level` · `risk_category` · `topic_key` | `requests.risk_level` · `risk_category` · `topic_key` | 같음 |
| `repeat_count` | — | 저장하지 않음. `requests_repeat_idx`로 조회 때 셈 |
| `due_at` · `is_delayed` | `cards.due_at` | `is_delayed = due_at < now()` |
| `evidence[].document_title` · `location` · `effective_from` · `quote` | `documents.title` · `document_chunks.location` · `documents.effective_from` · `card_evidence.quote` | `card_evidence → document_chunks → documents` |
| `slots[].id` · `slot_ids[]` · `slot_id` | `consultation_slots.id` | 정수 |
| `slots[].period` · `booking.period` | `consultation_slots.period` · `consultation_bookings.period` | `tstzrange` ↔ `{ start, end }` |
| `booking.room` | `rooms.name` | `consultation_bookings.room_id`로 이어 이름을 줌 |
| `draft_status` · `input_id` | `daily_note_inputs.draft_status` · `id` | 같음 |
| `notes[].status` · `content` · `open_checks[]` | `daily_notes.status` · `content` · `open_checks` | 같음 |
| `ingest_status` | `documents.ingest_status` | 같음 |
| `chunk_count` | — | 저장하지 않음. 그 문서의 `document_chunks` 개수 |
| 넘긴 이유(`ai_timeout`·`ai_failed`·`card_missing`, 분류 결과의 `handoff_reason`) | `events.detail->>'handoff_reason'` | 칸을 따로 두지 않고 이력에 넣음 |
| `notification.kind` · `read_at` | `notifications.kind` · `read_at` | 같음 |
| `completed_unconfirmed` 등 원장 현황 숫자 | `director_overview` 뷰 | 뷰의 칸 이름 그대로 |
| `trace_id` · `X-Request-ID` | `events.detail->>'trace_id'` | 칸을 따로 두지 않고 이력 `detail`에 넣음 |

## 8. 설정값

MVP 설정값은 서버 설정(`.env`)으로 관리한다. `.env.example`에는 이름과 기본값만 두고 비밀 값은 넣지 않는다.

공휴일은 모든 기관이 같고 1년에 한 번 바뀐다.
원장이 화면에서 고치는 기능은 MVP 범위 밖이다.
기관별 재량휴업일·근무 시간을 원장이 바꾸는 기능이 생기면 DB의 기관 설정 테이블로 옮기고, 그때 T09에 추가한다.

| 이름 | 기본값 | 뜻 |
| --- | --- | --- |
| `JWT_SECRET` | 개발용 기본 문자열(배포 때 반드시 바꿈) | 토큰 서명 키. 32바이트 이상 |
| `JWT_ACCESS_TTL_HOURS` | `12` | 토큰 수명 |
| `CORS_ORIGINS` | `http://localhost:5173` | 허용할 화면 출처. 쉼표로 여러 주소를 넣음 |
| `HOLIDAYS` | `""`(빈 문자열, 공휴일 목록 없음) | YYYY-MM-DD를 쉼표로 나열. 기한·교직원 알림 시각에 적용 |
| `WORK_HOURS` | `09:00-18:00` | 교직원 근무 시간. HH:MM-HH:MM, 시작 < 끝(같은 날). 시작 포함·끝 제외 |
| `IMMEDIATE_RISK_CATEGORIES` | `child_safety` | 근무 밖에도 즉시 보내는 긴급 위험 종류. child_safety·staff_attack·legal_external·privacy_leak 중 쉼표 목록 |
| `MOCK_STREAM_DELAY_MS` | `300` | 모의 SSE 이벤트 사이 간격(밀리초). 음수는 0으로 처리 |
| `LLM_MODEL_DEFAULT` | `gpt-6-luna` | 역할별 모델을 비워 두면 쓰는 모델(D27) |
| `LLM_MODEL_SUPERVISOR` | (비움) | 감독 AI 모델 |
| `LLM_MODEL_DOCUMENT` | (비움) | 자료 AI 모델 |
| `LLM_MODEL_MEMORY` | (비움) | 기억 AI 모델 |
| `LLM_MODEL_CHECKER` | (비움) | 검사 AI 모델 |
| `LLM_MODEL_CODE` | (비움) | 코드 AI 모델 |
| `OPENAI_API_KEY` | (비움) | 모델 호출 키. 값은 팀 키 보관 위치에서 받음 |

역할별 모델은 계약표 6장 ⑪을 따른다. 비워 두면 `LLM_MODEL_DEFAULT`를 쓰고, 역할별 교체는 다섯 에이전트 분리(T43) 뒤 앱 경유 평가에서 이득이 확인된 역할만 팀 결정으로 한다. 공휴일·근무 시간·즉시 알림 위험 종류는 `load_settings()`가 기동 때 읽는다. 날짜·시각 형식 오류, 시작 이하인 종료 시각, 빈 위험 종류 목록·허용 밖 위험 종류는 `ValueError`로 기동을 멈춘다. 기한과 알림은 6.5·6.6의 같은 설정을 사용한다.

## 부록 A. 예시 ID

문서 예시·팀 자체 30문항·시드가 같은 값을 쓴다(계약표 부록 A). 시드(`db/seeds`)는 이 UUID로 만든다.

| 데모 이름 | 무엇 | 표 | 고정 UUID |
| --- | --- | --- | --- |
| `KG-DEMO-01` | 가상 햇살유치원 | `organizations` | `00000000-0000-4000-8000-000000000001` |
| `CL-DEMO-01` | 만 4세 별빛반 | `classrooms` | `00000000-0000-4000-8000-000000000101` |
| `CL-DEMO-02` | 만 5세 햇님반 | `classrooms` | `00000000-0000-4000-8000-000000000102` |
| `T-DEMO-01` | 우리 반 담임 | `users` | `00000000-0000-4000-8000-000000000201` |
| `T-DEMO-02` | 다른 반 교사(권한 거부 시험용) | `users` | `00000000-0000-4000-8000-000000000202` |
| `D-DEMO-01` | 원장 | `users` | `00000000-0000-4000-8000-000000000301` |
| `P-DEMO-01` | 우리 아이 학부모 | `users` | `00000000-0000-4000-8000-000000000401` |
| `P-DEMO-02` | 다른 아이 학부모 | `users` | `00000000-0000-4000-8000-000000000402` |
| `C-DEMO-01` | 우리 아이 | `children` | `00000000-0000-4000-8000-000000000501` |
| `C-DEMO-02` | 다른 아이(권한 거부 시험용) | `children` | `00000000-0000-4000-8000-000000000502` |
| `C-DEMO-03` | 별빛반 노을, 보호자 P-DEMO-02 | `children` | `00000000-0000-4000-8000-000000000503` |
| `RM-DEMO-01` | 상담실 | `rooms` | `00000000-0000-4000-8000-000000000601` |
| `R-DEMO-01` · `R-DEMO-02` | 상담 요청 · 민원 요청 | `requests` | `…000000000701` · `…000000000702` |
| `K-DEMO-01` · `K-DEMO-02` | 상담 후보 카드 · 민원 회신 카드 | `cards` | `…000000000801` · `…000000000802` |

그 밖의 데모 요청(…703~707)·문서(…b01~b03)·규칙(…d01)은 `apps/api/app/mock/seed.py`를 참고한다.

## 변경 이력

| 판 | 날짜 | 내용 | 작성 |
| --- | --- | --- | --- |
| v0.1 | 2026-11-18 | 초안. API 목록 29개, 핵심 6개 상세 명세, 화면용 조회 칸(3.7, T12 #254 리뷰), 검증·권한 규칙, 도구 실패 코드·실패 후 처리, 실행 규칙(기한 계산·알림 발송 시각 포함, T10 회의 결과), API 필드↔DB 컬럼 대응, 설정값 | 태웅 |
| v0.2 | 2026-11-18 | 나머지 API 상세 명세(3.8~3.23)를 모의 API·OpenAPI와 대조해 채움. 29개 상세 절 연결, 모의 API 안내·설정값·데모 ID 보완 | 태웅 |
| v0.3 | 2026-11-20 | 영민 #256 리뷰 반영: `find_consult_slots` 실패 코드에 `TOOL_TIMEOUT` 추가(YC-F01), 에이전트 허용 목록은 T43부터 적용(5.3 ①), `create_card` 끝내 실패 시 학부모 안내('받았지만 늦어질 수 있음', 화면의 '접수됨'과 같게)와 서버의 미배정 재올림(5.4·6.3). 강사 11/18 피드백 2·3·4번: 세 업무 흐름·사람 인계·도구 이름 대조(5.7), 서버 설정 위치·WORK_HOURS·IMMEDIATE_RISK_CATEGORIES(6.5·6.6·8장), 공휴일·퇴근 뒤 실계산 예시(6.6.1), 화면·API·DB 대표 사례와 시험 기록(6.7), notify_failed 경고(3.7·5.4) | 태웅 |
