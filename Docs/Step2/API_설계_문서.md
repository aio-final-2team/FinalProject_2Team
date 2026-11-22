# 유치온 API 설계 문서 (T13)

**팀 확인 전 초안 — T46·T48·T54와 [제안][선택] v0.8 화상상담**

문서 버전 v0.8 | 작성 상태: [제안][선택] T56 화상상담 접속·가상 음성 분석을 모의·DB와 대조해요

| 항목 | 내용 |
| --- | --- |
| 작업 | T13 API 설계 문서(FastAPI·Function Calling 도구 계약)·모의 API (#170) |
| 작성 | 태웅 · 검토 인혜 |
| 기준 문서 | 기획서 1117판 3장 FR-01~FR-13 · T04 흐름·권한 명세(PR #234) · [입출력 계약표](입출력_계약표_초안.md) v0.20(T46·T48·T54·T56 팀 확인 전 초안) · [DB 스키마 설계서](DB_스키마_설계서.md) v0.18(0012 가상 음성 분석 포함) |
| 따른 가이드 | 강사님 'API 설계 문서 작성법' 11/18 수정본. 1~6장이 가이드의 '문서에 들어가는 여섯 가지' 순서다 |

이 문서는 T10 계약표에서 합의한 필드·권한·오류를 엔드포인트와 도구 단위로 펼친 것이다. 계약표와 이 문서가 다르면 계약표를 먼저 고치고 두 문서의 판을 같이 올린다. 구현이 시작되면 FastAPI의 `/docs`와 대조해 판을 올린다(계약표 1.1 규칙 1). 이 판(v0.8)은 HTTP API 53개와 신호 WebSocket 전부의 상세 명세, 화면이 쓰는 조회 응답 칸(3.7), 도구 전체의 실패 처리, 업무 흐름(5.7), 실행 규칙과 대표 사례 대조(6.7)를 담는다. 모의 API와 생성물 `contracts/openapi.yaml`을 붙였으며, 쓰는 법과 데모 계정은 [모의 API 안내](../../contracts/mock_api/README.md)에 있다.

**목차.** 1. 공통 정보와 인증 · 2. API 목록 · 3. 엔드포인트 상세 명세 · 4. 검증과 권한 규칙 · 5. Tool 정의와 호출 흐름 · 6. 실행 규칙 · 7. API 필드와 DB 컬럼 대응 · 8. 설정값 · 부록 A. 예시 ID · 변경 이력

**가이드 최종 제출 전 체크리스트와 이 문서**

| 체크리스트(가이드 33쪽) | 이 문서 |
| --- | --- |
| 구현할 API가 모두 목록 표에 있고 요구사항 ID와 연결된다 | 2장(53개, 요구사항 열) |
| 서버 주소·인증·오류 형식·/docs·변경 이력이 있다 | 1장, 끝의 변경 이력 |
| 구현할 API마다 상세 명세와 필드 명세 표가 있다 | 3장(53개 전부) |
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
| 모의 API | API 53개가 메모리 데모 데이터로 응답한다. 다시 켜면 초기화된다. 실행·계정·흐름은 [모의 API 안내](../../contracts/mock_api/README.md) 참고 |

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
| `Content-Type` | 요청 | `application/json`. 자료·피드 사진 올리기는 `multipart/form-data` |

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
| 403 | `FORBIDDEN` | [제안] T54 칸·사진 범위 변경·삭제·숨김 권한 거부(3.29) | 서버 권한 검사 |
| 404 | `NOT_FOUND` | 없거나, 다른 기관·다른 반·남의 자료 | 서버 범위 검사 |
| 409 | `CARD_VERSION_CONFLICT` | 화면이 본 카드 판이 지금 판과 다름(`details.current_version`) | 서버 |
| 409 | `ALREADY_DECIDED` | 같은 카드 판에 이미 결정이 있음 | 서버 + DB 유니크 |
| 409 | `INVALID_TRANSITION` | T04 전이 규칙에 없는 상태 변경(예: 회신 전 처리 완료, 보류 아닌 카드 재개) | 서버 |
| 409 | `REASON_REQUIRED` | 학부모 미확인 민원을 이유 없이 처리 완료(계약표 6장 ⑦) | 서버 + DB 트리거 |
| 409 | `SLOT_TAKEN` | 같은 상담실·담임의 겹치는 시간이 확정됐거나 다른 보호자가 체크 중 | 서버 + DB 배제 제약 |
| 409 | `SLOT_PAST` | 후보 시작 시각이 현재 시각 이하인 시간을 체크·확정 | 서버 |
| 409 | `SLOT_NOT_CHOSEN` | 학부모가 체크하지 않은 후보로 확정 | 서버 |
| 409 | `NOTE_BATCH_BLOCKED` | 반에 아직 확인 안 된 알림장이 있음(`details.blocked[]`) | 서버 |
| 422 | `VALIDATION_FAILED` | 입력 형식·허용 값·길이·함께 와야 하는 칸이 어긋남(`details.fields[]`) | Pydantic |
| 500 | `INTERNAL_ERROR` | 서버 내부 오류. 내부 내용은 응답에 넣지 않고 로그에만 남김 | — |
| 503 | `UPSTREAM_UNAVAILABLE` | 모델·외부 API 장애. 요청은 저장되고 나중에 다시 처리 | 서버 |

400은 쓰지 않는다. 필수 정보가 빠진 요청은 오류가 아니라 요청 상태 `needs_info`로 정상 응답에 담는다(계약표 1.1 규칙 4). [제안] T46 투약은 교직원이 확인하므로 `received`와 `missing_fields`로 표시해요(3.27). FastAPI 기본 422 응답은 예외 처리기에서 위 형식으로 바꿔 돌려준다. `message`는 서버의 기본 한국어 문장이고, 화면에 띄울 문구는 화면이 `code`별로 정한다(계약표 1.1 규칙 9).

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

인증 열의 '자기 것'·'우리 반'은 4.2의 범위 규칙을 뜻한다. 상세 열은 53개 API의 3장 절 번호를 가리킨다.

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
| 30 | GET | `/api/v1/classrooms/{classroom_id}/children` | 담임(우리 반)·원장(같은 기관) | 반 아이 목록(이름순) | 200 | FR-10 | 3.24 |
| 31 | GET | `/api/v1/memories` | 담임(본인) | 내 AI 기억 보기 | 200 | FR-06 | 3.25 |
| 32 | DELETE | `/api/v1/memories/{memory_id}` | 담임(본인) | 내 AI 기억 지우기 | 204 | FR-06 | 3.25 |
| 33 | POST | `/api/v1/daily-notes/drafts/{input_id}/regenerate` | 담임(우리 반) | 미확인 알림장 다시 만들기 | 202 | FR-10 | 3.26 |
| 34 | GET | `/api/v1/children/{child_id}/pickup-guardians` | 자기 아이 보호자·담임·원장 | 등록 인계자 목록(팀 확인 전 초안) | 200 | FR-16 | 3.27 |
| 35 | GET | `/api/v1/care-requests` | 담임·원장 | 투약·귀가 교직원 목록(팀 확인 전 초안) | 200 | FR-16 | 3.27 |
| 36 | POST | `/api/v1/requests/{request_id}/care-decisions` | 담임·원장 | 투약·인계 실제 확인·완료(팀 확인 전 초안) | 200 | FR-16 | 3.27 |
| 37 | POST | `/api/v1/consultations/{booking_id}/delay` | 그 반 예약 담임 | 상담 예상 종료 기록([제안] v0.6) | 200 | FR-17 | 3.28 |
| 38 | GET | `/api/v1/classrooms/{classroom_id}/posts` | 그 반 아이 보호자 | 반 칸 글 목록([제안] v0.7) | 200 | FR-22·AC-06 | 3.29 |
| 39 | POST | `/api/v1/classrooms/{classroom_id}/posts` | 그 반 아이 보호자 | 반 칸 글·사진 올리기([제안] v0.7) | 201 | FR-22·AC-06 | 3.29 |
| 40 | GET | `/api/v1/organizations/{org_id}/posts` | 그 기관 보호자·교직원 | 원 칸 글 목록([제안] v0.7) | 200 | FR-22·AC-06 | 3.29 |
| 41 | POST | `/api/v1/organizations/{org_id}/posts` | 그 기관 보호자·교직원 | 원 칸 글·사진 올리기([제안] v0.7) | 201 | FR-22·AC-06 | 3.29 |
| 42 | GET | `/api/v1/posts/{post_id}` | 칸 권한 | 글 상세·보이는 사진([제안] v0.7) | 200 | FR-22·AC-06 | 3.29 |
| 43 | DELETE | `/api/v1/posts/{post_id}` | 같은 기관 작성자(반 이동·퇴소 뒤에도) | 글·사진 파일 지우기([제안] v0.7) | 204 | FR-22·AC-06 | 3.29 |
| 44 | PATCH | `/api/v1/posts/{post_id}` | 그 기관 원장·원 칸 | 원 칸 글 숨기기([제안] v0.7) | 200 | FR-22·AC-06 | 3.29 |
| 45 | GET | `/api/v1/classrooms/{classroom_id}/albums` | 그 반 아이 보호자 | 반 칸 앨범([제안] v0.7) | 200 | FR-22·AC-06 | 3.29 |
| 46 | GET | `/api/v1/organizations/{org_id}/albums` | 그 기관 보호자·교직원 | 원 칸 앨범([제안] v0.7) | 200 | FR-22·AC-06 | 3.29 |
| 47 | GET | `/api/v1/photos/{photo_id}/file` | 칸·사진 권한 | 인증 사진 파일([제안] v0.7) | 200 | FR-22·AC-06 | 3.29 |
| 48 | GET | `/api/v1/children/{child_id}/photo-scope` | 그 아이 보호자 | 현재 사진 공개 범위([제안] v0.7) | 200 | FR-22·AC-06 | 3.29 |
| 49 | PATCH | `/api/v1/children/{child_id}/photo-scope` | 그 아이 보호자 | 사진 공개 범위 바꾸기([제안] v0.7) | 200 | FR-22·AC-06 | 3.29 |
| 50 | GET | `/api/v1/consultations/{booking_id}/room` | 예약 담임·신청 보호자 | 화상상담 접속권([제안][선택] v0.8) | 200 | FR-18 | 3.30 |
| 51 | POST | `/api/v1/consultations/{booking_id}/voice-analyses` | 예약 담임 | 가상 음성 분석 접수([제안][선택]) | 202 | FR-18 | 3.30 |
| 52 | GET | `/api/v1/consultations/{booking_id}/voice-analyses` | 예약 담임·원장 | 가상 음성 분석 목록([제안][선택]) | 200 | FR-18 | 3.30 |
| 53 | GET | `/api/v1/voice-analyses/{analysis_id}` | 예약 담임·원장 | 가상 음성 분석 결과([제안][선택]) | 200 | FR-18 | 3.30 |

SSE 두 개(6·14)는 실시간 진행 화면(NFR-10)이 쓰므로 넣었어요. 투약·귀가 SSE는 AI 단계 없이 현재 상태 done으로 끝나요(3.27).

## 3. 엔드포인트 상세 명세

HTTP API 53개를 가이드의 여덟 칸으로 쓴다(계약표 1.1 규칙 8). 고정 예시 ID는 부록 A의 데모 ID다. 필드 표의 '빈값'은 `""`이나 `null`을 받아도 되는지다. 3.8 이후 예시는 주요 응답 필드와 목록 첫 항목만 줄여 보인다. 토큰과 새로 발급한 ID는 `…`로 줄이고, 경로의 `{card_id}`·`{input_id}`·`{note_id}`는 앞선 응답에서 받은 값을 쓴다.

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
| ⑧ 실행 규칙 | 저장만 하고 바로 답한다(10초 안). 중복 제출은 `(requester_id, client_request_id)` DB 유니크로 막는다. AI 처리가 실패해도 요청은 남고, 재시도 뒤에도 실패하면 사람 카드로 넘긴다(6.3). 투약·귀가는 AI를 실행하지 않고 교직원 목록에 남겨요(3.27) |

**요청 본문 필드**

| 필드 | 위치 | 타입 | 필수 | 빈값 | 제약 | 설명 |
| --- | --- | --- | --- | --- | --- | --- |
| `client_request_id` | 본문 | string | 필수 | 불가 | 8~64자, 화면이 만든 UUID 권장 | 같은 제출을 두 번 받지 않기 위한 키 |
| `type` | 본문 | string | 필수 | 불가 | `inquiry`·`consultation`·`complaint`·`medication`·`pickup` | 요청 유형. 투약·귀가는 팀 확인 전 초안(3.27) |
| `body` | 본문 | string | 필수 | 불가 | 1~2,000자 | 질문·요청 내용 |
| `child_id` | 본문 | string(UUID) | 필수 | 불가 | 내 아이 | 대상 아이. 반은 서버가 아이에서 정한다 |
| `previous_request_id` | 본문 | string(UUID) | 선택 | `null` 가능 | 내 요청, 끝난 상태 | 끝난 요청을 다시 열 때 이전 요청(T04 2.1) |
| `pickup_guardian_id` | 본문 | string(UUID) | 선택 | null 가능 | pickup만, 같은 아이의 등록된 활성 보호자 | 미등록 인계자는 생략해요. [제안] T46 초안(3.27) |
| `pickup_name`·`pickup_relation` | 본문 | string | 선택 | null·빈값 가능 | pickup만, 각 100자 이하 | 미등록 인계자의 이름·관계예요. 추측하지 않아요. |
| `medication_name`·`medication_dose`·`medication_time` | 본문 | string | 선택 | null·빈값 가능 | medication만, 각 100자 이하 | 약 이름·용량·시간이에요. 누락은 missing_fields로 표시해요. |

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

투약·귀가도 자기 요청 목록·상세·대화·스트림에서 읽어요. 실제 확인·완료와 등록 인계자 계약은 3.27의 팀 확인 전 초안이에요. 민원용 confirm은 계속 409예요.

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
| `request.missing_fields[]` | string[] | 예 | `needs_info`일 때 물어볼 항목이에요. [제안] 투약은 received에서도 약 이름·용량·시간 누락을 표시해요(3.27). 없으면 빈 목록이에요. |
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
| ⑧ 실행 규칙 | 체크는 다른 요청의 확정 예약·유효 체크와 겹치지 않아야 한다. 시작한 후보는 체크·확정 모두 409 `SLOT_PAST`다. 체크 만료와 보류·원장 지시는 아래 규칙을 따른다 |

체크할 때 상담실 또는 담임 시간이 다른 요청의 확정 예약·24시간 안 체크와 겹치면 409 `SLOT_TAKEN`이다.
요청이 `awaiting_review`일 때만 24시간 지난 체크를 풀고 `needs_info`로 돌린다. 담임에게 `slot_hold_expired` 알림을 남긴다(계약표 6장 ⑥).
보류·원장 보고 중에는 체크와 요청 상태를 유지한다. 재개·원장 지시 뒤 만료를 검사한다.
`escalated`에서는 원장 지시 전에 확정할 수 없다. 지시하면 보고 카드를 닫고 상담 후보 카드로 돌려보낸다.
최종 확정은 담임 → 상담실 순 자문 잠금과 DB 배제 제약으로 한 건만 받는다(DB 설계서 9.1 F1-7).

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
| 409 | `INVALID_TRANSITION` | 시간을 고를 단계(`needs_info`)가 아닌데 체크, 원장 보고 중 지시 전에 확정 |
| 409 | `SLOT_NOT_CHOSEN` | 학부모가 체크하지 않은 후보로 확정 |
| 409 | `SLOT_TAKEN` | 같은 상담실·담임의 확정 예약 또는 다른 요청의 유효 체크와 겹침 → 후보 다시 내기 안내 |
| 409 | `SLOT_PAST` | 후보 시작 시각이 현재 시각 이하인 시간을 체크·확정 |
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
| ⑦ 오류 응답 | 403, 404, 409 `NOTE_BATCH_BLOCKED`(`details.blocked[] { note_id, child_id, open_checks[] }`), 422. 초안 작업이 queued·running·failed면 409 `NOTE_BATCH_BLOCKED`, `details.blocked=[]`다. |
| ⑧ 실행 규칙 | 한 트랜잭션에서 반 전체를 잠그고 확인한 뒤 보낸다. 이미 보낸 알림장은 다시 보내지 않고 `sent_count`에서 뺀다 |

```json
{ "error": { "code": "NOTE_BATCH_BLOCKED", "message": "확인이 안 끝난 알림장이 있어요.",
             "trace_id": "…", "details": { "blocked": [ { "note_id": "…", "child_id": "00000000-0000-4000-8000-000000000502",
             "open_checks": [ { "id": "c1", "item_key": "supplies", "kind": "date_check", "problem": "준비물 날짜가 식단표와 달라요", "sentence": "내일 실내화" } ] } ] } } }
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
| `classroom { id, name }` | 객체 | 항상 | 반 이름. 규칙 제안 카드는 반이 없으면 null이다. 원장 화면에서 반을 구분하려고 준다 | `requests.classroom_id` → `classrooms.name` |

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
| `items[].key` | `day`·`meal`·`medication`·`pickup`·`supplies`·`child`·`inquiry` | 줄 종류. `child`는 아이별 메모를 풀어 쓴 줄이고 출처는 `teacher_input`이다. 메모가 없거나 공백뿐이면 이 줄이 없다. 보호자 문의는 반 공통 `day`와 다른 `inquiry` 줄, 투약·귀가는 `medication`·`pickup` 줄로 잇고 출처는 `request`다. 투약·귀가 실제 확인은 3.27의 팀 확인 전 초안이고, 응답 request_status로 현재 상태를 보여요 |
| `items[].source.type` | `teacher_input`·`document`·`request` | 담임 입력(`daily_note_inputs`), 원 자료(식단·일정), 학부모 요청(문의·투약·귀가) |
| `items[].source.document_id`·`document_title` | — | `document`일 때 |
| `items[].source.request_id` | — | `request`일 때 |
| `open_checks[] { id, item_key, kind, problem, sentence, request_id? }` | — | 확인할 항목. `id`·`item_key`·`kind`·`problem`은 필수다. `problem`은 선생님이 읽는 설명이고, `sentence`는 걸린 초안 문장(없으면 null)이다. `request_id`는 선택 UUID이고 생략·null이 가능하다. 보호자 요청 누락이면 해당 요청 ID를 넣는다. `resolved_checks[]`는 지금처럼 `id`만 보낸다 |
| `open_checks[].kind` | `not_in_memo`·`sensitive`·`other_child`·`date_check`·`absent`·`draft_failed`·`check_failed`·`request_missed` | 순서대로 메모에 없음·민감 정보·다른 아이·날짜 확인·결석·아이 초안 실패·검사 실패·보호자 요청 누락 |

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
| `items[].id`·`type`·`title`·`status`·`status_label`·`updated_at` | 응답 | UUID·string·datetime | 항상 | title은 null 가능 | 등록 유형 5개·상태 11개 | 본인 요청의 요약 |
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
| `items[].id`·`kind`·`title` | 목록 응답 | integer·string | 항상 | 불가 | kind는 기존 13종과 consultation_ending·consultation_delayed, 모두 15종 | 알림 종류와 제목 |
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
| ⑧ 실행 규칙 | 일반이면 risk_category를 지운다. 열린 원장 보고 카드가 있으면 담임은 위험 등급만 바꾸고 escalated를 유지한다. 원장이 일반으로 내리면 열린 원장 보고 카드를 done으로 닫고 risk_reclassified 이력에 해당 카드 ID를 남기며 요청을 awaiting_review로 바꾼다. 이때 escalated에서 담임 회신 단계로 돌아오면 회신 카드 담당자에게 해당 회신 카드로 연결되는 new_card 알림을 한 번 남긴다. 열린 보고 카드가 없으면 일반은 awaiting_review로, 긴급은 원장 보고 카드를 확보하고 escalated로 바꾼다. 같은 요청 카드의 due_at을 접수 시각 기준으로 다시 계산하며 호출한 카드와 이번에 닫은 보고 카드의 판을 각각 1 올린다. 초안은 새로 만들지 않고 그 밖의 재분류는 new_card 알림을 만들지 않는다. |

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
| 409 | `INVALID_TRANSITION` | 원장 보고·개인 규칙 제안·끝난 카드 |
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

DB도 같은 결정 계약을 쓴다. 카드 거절·반려 이유는 출처 요청의 반 아이 이름을 가려 결정한 담임의 기억에 저장한다. 반이 없으면 같은 기관 전체를 본다. 이름 앞에 한글이 없고 뒤가 끝·공백·문장부호 또는 조사·호칭일 때만 가리고, 낱말 안쪽은 보존한다. 지우지 않은 같은 코드 세 건부터 제안 카드 하나를 만든다. 같은 주인·코드의 마지막 decline 결정 뒤에는 새 기억 세 건이 쌓여야 다시 제안한다. 개인 규칙 제안은 재배정하지 않고, 주인에게 근무 시간 기준 new_card 알림을 남긴다. 자동 대역은 코드별 안내만 제안하고 `other` 자유 글은 자동 규칙으로 만들지 않는다. 구체적인 조건 추출은 기억 AI가 맡으며, DB 상담 계산은 `active`인 `slot_unavailable` 규칙의 시간 조건만 읽는다.

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
| ④ 요청 본문 | 생성은 classroom_id·note_date·activities·supplies, 선택으로 child_memos[]를 보낸다. |
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
| `child_memos[]` | 생성 본문 | object[] | 선택 | 빈 목록 가능 | 생략하면 [] | 아이별 메모 |
| `child_memos[].child_id` | 생성 본문 | string(UUID) | 항목마다 필수 | 불가 | 그 반 아이, 중복 불가 | 다른 반·다른 기관·없는 아이면 422다. details.child_id에 해당 ID가 온다 |
| `child_memos[].memo` | 생성 본문 | string | 항목마다 필수 | 빈 문자열 불가 | 1~500자 | 모의 생성은 원문 그대로 child 줄에 넣는다. 공백뿐이면 줄을 만들지 않는다 |
| `draft_status`·`error` | 응답 | string·object | 항상 | error는 null 가능 | queued·running·succeeded·failed; 오류는 {code, message} | 실패 조회도 200, 모의 오류 코드는 UPSTREAM_UNAVAILABLE |

초안 입구 함수의 아이 입력은 `{ child_id, display_name, memo, requests: [{ request_id, type, text }] }`다. 전체 입력은 `{ input_id, note_date, classroom, activities, supplies, children, menu }`이고, `menu`는 `{ document_id, title, text }` 또는 null이다. `requests`는 클라이언트가 보내지 않고 서버가 모은다. 같은 기관·반·아이의 보호자가 보낸 `medication`·`pickup`·`inquiry` 중 `created_at`의 한국 날짜가 `note_date`인 요청이다. `text`는 보호자 요청 본문이고, 없으면 빈 목록이다. 이 입구는 DB runner를 연결할 때도 같은 모양으로 쓴다.

모의 초안은 요청 원문을 `source: { type: request, request_id }` 줄에 넣는다. 하늘의 "기침해요"는 반영하고, 노을의 고정 귀가 요청(…70a) 하나만 일부러 빼서 `request_missed`를 보여 준다. 이때 `item_key: pickup`, `sentence: null`, `request_id: …70a`다. 다른 귀가 요청은 반영한다. 교사는 요청을 확인하고 기존 PATCH의 `resolved_checks`로 해결한다. 미해결 항목이 있으면 확인·발송을 막는 규칙은 같다.

```http
POST /api/v1/daily-notes/drafts
{"classroom_id": "00000000-0000-4000-8000-000000000101", "note_date": "2026-11-18", "activities": "블록 놀이와 산책을 했어요.", "supplies": "내일 실내화", "child_memos": [{"child_id": "00000000-0000-4000-8000-000000000501", "memo": "블록으로 높은 탑을 쌓음"}]}
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
| 422 | `VALIDATION_FAILED` | 필수 칸·타입·길이, 중복 child_id, 그 반 아이가 아닌 메모(details.child_id) |

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
| ⑧ 실행 규칙 | 학부모에게 classroom_id를 주어도 내 아이·sent 조건을 먼저 적용한다. created_at으로 정렬 뒤 쪽을 나눈다. 모의 초안은 day·supplies·meal에 아이 메모·그날 보호자 요청 줄을 더한다. 첫 아이의 준비물 확인 c1과 노을의 고정 귀가 요청 누락 확인을 남긴다. |

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
{"items": [{"child_id": "00000000-0000-4000-8000-000000000503", "note_date": "2026-11-18", "status": "draft", "content": {"items": [{"key": "day", "label": "오늘 하루", "value": "블록 놀이와 산책을 했어요.", "source": {"type": "teacher_input", "document_id": null, "document_title": null, "request_id": null}}, {"key": "supplies", "label": "준비물", "value": "내일 실내화", "source": {"type": "teacher_input", "document_id": null, "document_title": null, "request_id": null}}, {"key": "meal", "label": "식사", "value": "점심: 카레라이스, 채소와 과일", "source": {"type": "document", "document_id": "00000000-0000-4000-8000-000000000b01", "document_title": "가상 식단표", "request_id": null}}]}, "open_checks": [], "confirmed_at": null, "sent_at": null}], "total": 20, "page": 1, "size": 20}
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
| ⑤ 검증·권한 | teacher와 현재 담당 반만. 문서·요청 출처도 범위를 검사한다. 요청의 child_id가 알림장 아이와 다르거나 문서 visibility가 parents·all이 아니면 422 VALIDATION_FAILED다. sent는 수정 불가. 없는 확인 ID와 미해결 항목을 남긴 confirm은 저장된 확인 항목과 대조해야 알 수 있어 서버가 409로 막는다(4.1). |
| ⑥ 정상 응답 | 200 + note. confirm=true이고 미해결 0개면 ready·confirmed_at을 남긴다. |
| ⑦ 오류 응답 | 아래 오류 표. |
| ⑧ 실행 규칙 | content를 보내면 전체 내용을 바꾼다. confirm=false(기본)이면 기존 확인을 지우고 미해결 유무에 따라 needs_check·draft로 되돌린다. 빈 본문도 기존 확인을 해제한다. 오류면 수정하지 않는다. |

| 필드 | 위치 | 타입 | 필수 | 빈값 | 제약 | 설명 |
| --- | --- | --- | --- | --- | --- | --- |
| `note_id` | 경로 | string(UUID) | 필수 | 불가 | 현재 담당 반 알림장 | 3.20 응답에서 받은 ID |
| `content` | 본문 | object | 선택 | null 가능 | items[]의 key·label·value·source는 3.7; 빈 items도 허용 | 생략·null이면 내용 유지 |
| `content.items[].key` | 본문 | string | 줄마다 필수 | 불가 | day·meal·medication·pickup·supplies·child·inquiry | 줄 종류. child의 출처는 teacher_input, inquiry는 request만 허용 |
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
| 422 | `VALIDATION_FAILED` | 형식·출처 필수 칸, 다른 아이·아이 없는 요청 출처, visibility가 staff인 문서 출처 |

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


### 3.24 반 아이 목록 — `GET /api/v1/classrooms/{classroom_id}/children`

| 칸 | 내용 |
| --- | --- |
| ① 호출 목적 | 알림장 메모를 쓸 아이를 이름순으로 고른다(FR-10). |
| ② 요청 헤더 | `Authorization`(필수), `X-Request-ID`(권장). |
| ③ 경로·쿼리 | 경로 classroom_id(UUID, 필수)만 받는다. 페이지 쿼리는 없다. |
| ④ 요청 본문 | 없음. |
| ⑤ 검증·권한 | 현재 배정 기간 안인 담임과 같은 기관 원장만 본다. 학부모는 403 FORBIDDEN_ROLE, 없는 반·범위 밖 반은 404 NOT_FOUND다. |
| ⑥ 정상 응답 | 200 + `{ items: [{ id, display_name, classroom_id }] }`. 이름 오름차순이고, 아이가 없으면 items는 []다. |
| ⑦ 오류 응답 | 401 UNAUTHENTICATED, 403 FORBIDDEN_ROLE, 404 NOT_FOUND, UUID 형식이 틀리면 422 VALIDATION_FAILED. |
| ⑧ 실행 규칙 | 요청할 때마다 담임 배정 기간과 기관을 확인한다. 보호자·계정 정보는 보내지 않는다. |

| 필드 | 위치 | 타입 | 필수 | 빈값 | 제약 | 설명 |
| --- | --- | --- | --- | --- | --- | --- |
| `classroom_id` | 경로 | string(UUID) | 필수 | 불가 | 볼 수 있는 반 | 목록을 받을 반 |
| `items[]` | 응답 | object[] | 항상 | 빈 목록 가능 | display_name 오름차순 | 해당 반 아이 전부 |
| `items[].id`·`classroom_id` | 응답 | string(UUID) | 항상 | 불가 | 아이 ID·반 ID | child_memos의 child_id에 id를 보냄 |
| `items[].display_name` | 응답 | string | 항상 | 불가 | 아이 표시 이름 | 목록에 보여 줄 이름 |

```http
GET /api/v1/classrooms/00000000-0000-4000-8000-000000000102/children
HTTP/1.1 200 OK
{"items": [{"id": "00000000-0000-4000-8000-000000000502", "display_name": "바다", "classroom_id": "00000000-0000-4000-8000-000000000102"}]}
```

### 3.25 내 AI 기억 보기·지우기 — `GET /api/v1/memories`, `DELETE …/memories/{memory_id}`

담임은 본인 소유이며 `deleted_at`이 비어 있는 기억만 읽고 지운다. 원장·학부모는 403 `FORBIDDEN_ROLE`이다. 다른 사람·다른 기관·없는 기억·이미 지운 기억의 삭제는 모두 404 `NOT_FOUND`이며, 거부 이력을 남긴다.

| 필드 | 위치 | 타입·규칙 | 뜻 |
| --- | --- | --- | --- |
| `kind` | 쿼리, 선택 | rejection_reason·preference·tone | 생략하면 본인 기억 전체 |
| `page`·`size`·`sort` | 쿼리 | 공통 목록 규칙. 정렬은 created_at·-created_at | 같은 시각이면 id로 정렬 |
| `items[].id` | 응답 | 양의 정수 | 기억 ID |
| `items[].kind`·`reason_code` | 응답 | 위 kind 세 값·string 또는 null | 기억 종류·거절 이유 코드 |
| `items[].content`·`structured`·`created_at` | 응답 | string·object·date-time | 기억 내용·구조화 값·생성 시각 |
| `total`·`page`·`size` | 응답 | 정수 | 소유권·kind·삭제 여부를 거른 뒤 쪽 나누기 |
| `memory_id` | 삭제 경로 | 양의 정수 | 본인 기억만. 성공은 204, 본문 없음 |

삭제는 `deleted_at`을 채우고 content를 빈 문자열, structured를 빈 객체로 바꾼다. 행과 출처 연결은 이력용으로 남기고, 이후 조회·기억 AI 입력·제안 횟수에서 제외한다. 기억 생성·말투 추출은 기억 AI가 맡으며 이 API는 학습하거나 새 규칙을 만들지 않는다. 가상 말투 기억도 미리 넣지 않는다.

### 3.26 알림장 다시 만들기 — `POST /api/v1/daily-notes/drafts/{input_id}/regenerate`

| 항목 | 내용 |
| --- | --- |
| ① 호출 목적 | 저장한 반 입력으로 미확인 초안만 다시 만든다. 실패·중단된 입력도 재시도한다. |
| ② 권한 | teacher, 현재 담당 반(대체 담임 배정 기간 포함). 다른 반·기관·없는 입력은 404, 원장·학부모는 403이다. |
| ③ 경로·본문 | input_id는 UUID. 본문 없음. activities·supplies·child_memos는 저장된 입력을 그대로 쓴다. 보호자 요청·식단은 실행 시점에 다시 모은다. |
| ④ 정상 응답 | 202 + RegenerateResponse `{input_id, draft_status, error, kept_edited}`. kept_edited는 접수 시 교사 수정으로 보존한 미확인 알림장 수(0 이상 정수)다. DB는 queued 뒤 running→succeeded 또는 failed, 모의는 즉시 결과를 만든다. 진행·결과 조회는 API 23·24와 같으며 기존 DraftResponse에는 kept_edited를 더하지 않는다. |
| ⑤ 차단 | 입력에 sent 알림장이 하나라도 있으면 409 INVALID_TRANSITION이다. 발송과 같은 입력 잠금을 쓴다. |
| ⑥ 보존 | ready는 내용·확인자·시각·검사 항목을 그대로 둔다. draft·needs_check 중 content ≠ ai_original이거나 daily_note_edited 이력이 있으면 모두 보존한다. 나머지는 새 초안·새 확인 ID·새 ai_original로 갱신하고 기존 알림장 ID는 유지한다. 실행 중 생긴 수정·확인도 저장 직전에 다시 검사한다. 아직 없는 아이의 초안은 새로 저장한다. |
| ⑦ 복구·동시성 | failed는 재접수한다. queued·running은 시작 후 DAILY_NOTE_WRITER_TIMEOUT(기본 300초) 안이면 현재 상태만 돌려주고 작성기를 다시 부르지 않는다. 접수 시각(대기 중)·실행 시각은 반 묶음 카드 draft.draft_started_at으로 판단하며 기록이 없는 옛 입력은 created_at을 쓴다. 제한을 넘으면 다시 받고 이전 실행의 늦은 성공·실패는 버린다. 재생성 도중 교사 수정·확인도 보존한다. |
| ⑧ 이력 | 최초·재생성 저장은 daily_note_drafted, 내용이 실제로 바뀐 PATCH만 daily_note_edited, 확인은 daily_note_confirmed, 보내기는 daily_note_sent를 아이별 events.daily_note_id에 연결한다. 확인 취소는 기존 returned로 ready→draft를 남긴다. 빈 PATCH·확인 항목 해소만으로는 edited 이력을 남기지 않는다. 검사 해소로 needs_check→draft가 되면 기존 checked로 상태 변화를 남긴다. 재생성 요청자는 반 묶음 카드 draft.regenerated_by와 새 drafted 이력 detail.regenerated_by에 저장한다. 상태 변경과 같은 트랜잭션이다. |

`daily_notes.ai_original`은 선생님이 받은 마지막 AI 초안이다. 선생님의 PATCH·확인·발송으로는 바꾸지 않고, 수정하지 않은 미확인 알림장을 재생성해 저장할 때 새 초안으로 갱신한다. 기존 공개 NoteView에는 추가하지 않는다. 0003 이전 행은 마이그레이션 시점의 content로 채운다. 그 전에 사라진 초안을 복원했다는 뜻은 아니다. 말투 규칙 추출은 기억 AI가 이 원본과 수정 결과를 이용해 맡는다. 백엔드는 저장·조회·이력만 제공한다.

### 3.27 투약·귀가 요청 — [제안] T46 팀 확인 전 초안

이 절과 API 34~36은 **팀 확인 전 초안**이에요. FR-16·AC-09에 맞춰 미등록 인계자와 투약 필수값 누락을 표시해요.
[제안] 아래 자유 입력·확인 판·근무 밖 귀가 알림 규칙은 팀 확인 전 결정이에요.
투약 용량·시간과 인계자는 AI가 추측하지 않아요. 보호자 원문과 추가 대화를 그대로 보존해요.

| API | 입력 | 응답·권한 |
| --- | --- | --- |
| 기존 3 `POST /requests` | type은 medication·pickup도 받아요. body·child_id·client_request_id는 같아요. pickup에는 선택 pickup_guardian_id 또는 pickup_name·pickup_relation을 보내요. medication에는 선택 medication_name·medication_dose·medication_time을 보내요. 문자열은 각 100자 이하예요. | 202 received예요. 같은 키는 기존 요청과 현재 상태를 200으로 돌려줘요. 자기 아이 보호자만 등록해요. |
| 34 `GET /children/{child_id}/pickup-guardians` | 아이 UUID | 200 `{items:[{id,display_name}]}` 이름순이에요. 자기 아이 보호자·배정 기간 안 담임·같은 기관 원장만 읽어요. 연락처·로그인 ID는 보내지 않아요. |
| 35 `GET /care-requests` | 선택 classroom_id·status(received·assigned·completed), page=1·size=20(최대 100), sort는 -created_at(기본)·created_at·-updated_at·updated_at이에요. | CareRequestList예요. 기존 RequestList 항목에 version·unregistered_pickup·missing_fields를 더해요. 담임은 현재 반, 원장은 기관 전체를 봐요. next_action은 confirm·complete·null이에요. |
| 36 `POST /requests/{request_id}/care-decisions` | `{decision:"confirm"|"complete", version:1, pickup_guardian_id?:UUID}`예요. version은 필수 양의 정수예요. | 200 `{request:{id,status},care:CareOut}`예요. 배정 기간 안 담임·같은 기관 원장만 실제 확인을 기록해요. |

[제안] 등록 인계자는 같은 기관·아이의 child_guardians에 연결된 활성 학부모 계정이에요.
명시한 UUID는 접수와 새 confirm 때 검사해요. 틀린 UUID는 422 VALIDATION_FAILED예요.
UUID를 생략한 이름·관계만 있는 요청과 기존 '오늘 할머니가 데리러 가요' 시드도 접수·확인·완료할 수 있어요.
그때 상세 care와 교직원 목록의 unregistered_pickup은 true예요. 이름·관계도 없으면 null로 두고 원문을 보여요.
confirm 자체가 교직원의 명시 확인이에요. 별도 checked 이력에 '미등록 인계자 확인'·실제 actor·version을 남기고 원장에게 알림 1건을 만들어요.
같은 요청·인계자 이름·관계의 원장 경고는 정정 후 재확인해도 한 번만 만들어요. 이름이나 관계가 달라진 인계자는 새 경고 대상이에요.
등록 인계자는 확인 당시 UUID·이름·관계를 이력에 보존해요. 이후 계정 비활성·아이 연결 해제는 complete를 막지 않아요.
등록 인계자의 결정에는 같은 pickup_guardian_id를 다시 보내요. 미등록이면 생략해요. 현장 신원 확인은 교직원이 맡아요.

[제안] 투약의 약 이름·용량·시간이 없거나 공백이면 요청을 막지 않아요.
missing_fields에 medication_name·medication_dose·medication_time 중 빠진 칸을 넣어 상세 request·care와 교직원 목록에 표시해요.
보호자 본문에서 수치를 뽑아 채우지 않아요. received와 확인 할 일을 유지하고, 교직원이 대화 전체와 누락을 확인한 뒤 결정해요.
다른 유형에 투약·인계자 칸을 보내면 422예요. 기존 원문만 있는 시드는 투약 세 칸을 모두 누락으로 표시해요.

상태는 **received → assigned → completed**예요. confirm은 내용을 확인하고 수행을 준비했다는 기록,
complete는 실제 투약·인계를 마친 기록이에요. 확인 전 complete는 409 INVALID_TRANSITION이에요.
같은 입력 판의 같은 단계 재전송은 기존 결과만 돌려줘요. 완료 뒤 confirm·대화 추가는 409예요.
이 흐름은 AI 카드 승인이 아니어서 cards·approvals를 만들지 않아요. 실제 주체는 events.actor_type=user·actor_id예요.

[제안] care.version은 입력 판이에요. 최초 1이고 **보호자 새 글마다 1씩 증가**해요. 확인·완료 자체는 판을 바꾸지 않아요.
교직원은 상세 care.version 또는 교직원 목록 version을 결정에 보내요. 중간에 보호자 글이 왔으면
confirm·complete 모두 409 CARD_VERSION_CONFLICT, details.current_version을 돌려줘요.
보호자 글은 취소·정정 여부를 자동 판단하지 않고 모두 재확인 대상으로 삼아요.
assigned이면 received로 돌리고 confirmed_at을 지워요. received에서도 판을 올리고 담당자(없으면 원장)에게 알림 1건을 남겨요.
교직원은 새 대화 전체를 읽고 최신 판으로 다시 확인해요. 취소 글을 요청 완료나 자동 취소로 처리하지 않아요.
원래 본문과 구조화 입력은 바꾸지 않아요. 새 글·확인·완료는 요청 행 FOR NO KEY UPDATE 잠금으로 직렬화하고,
상태·이력·알림은 같은 트랜잭션에서 저장해요. AI는 실행하지 않아요.

CareOut은 version·pickup_guardian_id·pickup_name·pickup_relation·unregistered_pickup,
medication_name·medication_dose·medication_time·missing_fields·confirmed_at·completed_at이에요.
다른 요청 유형의 care는 null이에요. 확인·완료 시각은 한국 시각이고 교직원 신원은 응답에 넣지 않아요.
학부모의 기존 목록·상세·대화·SSE에서도 자기 요청을 봐요. SSE는 AI 단계 없이 현재 상태 done 한 개로 끝나요.
민원용 POST /confirm과 상담 시간 선택은 409 INVALID_TRANSITION이에요.

접수는 담당자에게 care_requested, confirm은 신청 학부모에게 care_confirmed, 완료는 학부모에게 completed예요.
정정·미등록 인계자 경고에는 기존 care_requested와 고정 본문을 써요. 알림에 투약 지시·추가 대화 원문을 싣지 않아요.
[제안] 귀가 알림은 아이 안전 때문에 18시 뒤·주말에도 즉시예요. 발송 실패 재시도도 근무일로 미루지 않아요.
투약의 교직원 알림은 기존 근무 시간 규칙을 유지해요. 같은 이벤트·수신자 알림은 한 번만 만들어요.

알림장 초안은 같은 날 요청 원문과 request 출처를 medication·pickup 줄로 연결해요.
읽기 전용 content.items[].request_status는 현재 received·assigned·completed예요. 보호자 정정 뒤에는 received로 보여요.
PATCH에 보내도 저장하지 않아요. content·ai_original·발송 시점 본문은 고쳐 쓰지 않아요.
알림장 확인·발송이 투약·인계를 완료시키지 않아요. 같은 아이·유형의 request 출처만 허용하고 다른 출처는 422예요.
목록은 한 연결에서 연결 요청 상태를 한 번에 읽어요.

오류는 기존 공통 형식이에요. 미인증 401, 교직원 기능의 학부모 호출 403 FORBIDDEN_ROLE,
범위 밖 404 NOT_FOUND, 단계·유형 불일치 409 INVALID_TRANSITION, 옛 입력 판 409 CARD_VERSION_CONFLICT예요.
명시한 인계자 UUID 불일치·잘못된 형식은 422 VALIDATION_FAILED예요. 인계자 실패 details.field는 pickup_guardian_id예요.
미등록 인계자와 투약 누락 자체는 422 사유가 아니에요.

저장은 기존 requests·request_messages·events·notifications를 써요. 접수 detail에 구조화 입력,
confirm에 pickup_snapshot·version·care_decision, 추가 대화의 returned에 care_message·message_id·version을 남겨요.
시각과 입력 판은 순서 있는 이력으로 읽어요. T46은 새 컬럼·마이그레이션을 더하지 않아요. T54의 새 표·칸은 0010이에요.

### 3.28 상담 지연 입력 — [제안] v0.6

`POST /api/v1/consultations/{booking_id}/delay`는 JWT를 가진 그 반의 예약 담임만 호출해요.
반 배정 기간과 기관·요청 범위도 확인해요. 학부모·원장은 403 FORBIDDEN_ROLE,
다른 반·기관·없는 예약은 404 NOT_FOUND예요.
같은 반의 다른 교사도 예약 담임이 아니면 403 FORBIDDEN_ROLE예요.
확정 예약이고 요청이 sent_or_booked여야 하며, 그 밖의 상태는 409 INVALID_TRANSITION이에요.

본문은 `{ "expected_end_at": "2026-11-16T09:55:00+09:00" }`예요.
오프셋을 포함한 시각이어야 해요. 상담 시작 이후에만 기록할 수 있고,
예상 종료는 현재·원래 종료보다 뒤이며 원래 종료 + 3시간 이내, 예약 시작과 같은 한국 날짜여야 해요.
틀리면 422 VALIDATION_FAILED예요. UTC 입력도 받고 응답은 한국 시각으로 맞춰요.

성공은 200이에요.

```json
{"booking":{"id":"00000000-0000-4000-8000-000000000901",
 "period":{"start":"2026-11-16T09:00:00+09:00","end":"2026-11-16T09:30:00+09:00"},
 "status":"confirmed","expected_end_at":"2026-11-16T09:55:00+09:00"},"affected_bookings":1}
```

`affected_bookings`는 같은 기관에서 담임 또는 상담실을 함께 쓰며,
새 예상 종료와 시작이 겹치는 뒤 확정 예약 수예요. 사람 수·알림 수가 아니에요.
동일 시각을 다시 보내면 지연 이력과 같은 시각의 알림을 늘리지 않아요.
예약의 period·확정 상태는 바꾸지 않아요. 저장 뒤 해당 예약 담임의 같은 한국 날짜 예약만 한 번 점검하므로 mock에서도
이 API → 알림 목록으로 지연 시 대체 시간 제안을 재현할 수 있어요. DB에서는 Beat도 점검해요.
점검이 잠겨 있으면 다음 Beat가 처리하므로 응답의 수는 발송 완료를 뜻하지 않아요.

대체 시간은 안내이며 잡아 두지 않아요. **예약 변경·취소로 대체 시간을 받아들이는 경로와
실제 상담 종료 입력·화면 연결은 후속 계약**으로 정해요. 이 제안에서 새로 만들지 않아요.


### 3.29 [제안] v0.7 피드·앨범

팀 확인 전 제안이에요. API 38~49는 위 표의 경로를 쓰며 `/api/v1` 아래예요.
T50이 붙기 전에는 올린 사람이 아이를 직접 표시해요.
T50 전에는 올린 사람이 아이를 빠뜨리면 그 사진은 칸 규칙만 따라요. 화면에서 아이 표시를 안내해 주세요.

| 칸 | 내용 |
| --- | --- |
| ① 호출 목적 | 보호자끼리 반 칸 글을 나누고, 같은 기관 구성원이 원 칸 글·사진을 봐요(FR-22·AC-06) |
| ② 요청 헤더 | JWT 필수. 생성은 multipart/form-data, 숨김·범위 변경은 application/json이에요 |
| ③ 경로·쿼리 | 기관·반·글·사진·아이 ID는 UUID예요. 목록은 기존 page=1·size=20(최대 100)·sort=-created_at, 오름차순은 created_at이에요. 동률은 같은 방향의 id로 정렬해요. 앨범 child_id는 보호자 자기 아이만 고를 수 있어요 |
| ④ 요청 본문 | 글 생성: body 1~2,000자(공백만은 안 돼요), files 0~10장, child_ids는 파일 순서별 아이 UUID 배열들의 JSON 문자열이에요. 예: [["아이 UUID"],[]]. 기본 []는 모든 사진의 태그 없음이에요. 숨김은 {"status":"hidden"}, 범위 변경은 {"photo_scope":"family"}(family·class·org 중 하나)예요 |
| ⑤ 검증·권한 | 먼저 칸 권한, 그다음 사진 공개 범위를 검사해요. class 칸은 그 반 아이 보호자만 읽고 써요. 교직원·다른 반 보호자는 목록·상세·앨범·파일 모두 403 FORBIDDEN과 permission_denied 이력이에요. org 칸은 같은 기관 보호자·교직원 모두 읽고 써요. 다른 기관·없는 자원은 404예요. 다른 아이 범위 조회·변경, 남의 글 삭제·원장 외 숨김도 403이에요 |
| ⑥ 정상 응답 | 글 생성 201·상세/숨김 200은 {post: Post}, 목록·앨범은 {items,total,page,size}예요. 범위 조회·변경 200은 {child_id,photo_scope}, 삭제는 204예요. 파일은 검사한 형식의 바이트와 Cache-Control: private, no-store·X-Content-Type-Options: nosniff·Content-Disposition: inline을 줘요 |
| ⑦ 오류 응답 | 공통 형식으로 401 UNAUTHENTICATED, 403 FORBIDDEN, 404 NOT_FOUND, 422 VALIDATION_FAILED예요. 태그가 다른 반/원 아이이거나 중복·배열 수 불일치여도 422예요. 업로드 몸통 51MiB 초과는 413 VALIDATION_FAILED예요 |
| ⑧ 저장·이력 | feed_posts·feed_photos·feed_photo_children, children.photo_scope(0010)를 써요. 생성·삭제·숨김·범위 변경은 events의 feed_post_created·feed_post_deleted·feed_post_hidden·photo_scope_changed에 trace_id·대상 ID를 남겨요. 새 알림은 만들지 않아요 |

Post는 id·lane(class/org)·classroom_id(org 칸은 null)·author_id·body·status(published/hidden)·created_at·photos를 줘요.
Photo는 id·post_id·media_type·size_bytes·created_at·file_url만 줘요. 저장 경로·sha256·태그·숨은 사진 개수는 주지 않아요.
file_url은 `/api/v1/photos/{photo_id}/file`이고 공개 정적 주소는 없어요.

아이별 photo_scope 기본값은 family예요. family는 해당 아이 보호자와 올린 사람, class는 반 칸까지,
org는 반·원 칸까지 허용해요. 보호자가 여럿이면 마지막 변경이 이겨요.
칸 권한을 통과한 뒤, 올린 사람은 모든 사진을 보고 다른 사람은 표시된 아이 **전원**에 대해
자기 아이이거나 그 아이 공개 범위가 이 칸을 덮어야 봐요. 태그가 없으면 칸 권한만 봐요.
사진이 안 보이면 글의 photos·앨범에서 빼고 앨범 total에도 세지 않아요. 파일은 404예요.
매번 현재 관계·공개 범위를 읽으므로 바꾸면 지난 사진에도 바로 적용돼요.

사진은 가상 자료만 써요. jpeg·png·webp를 확장자·전송 MIME 대신 첫 바이트로 검사하고, 장당 5MiB(5,242,880바이트)까지 받아요.
칸 권한을 몸통 읽기 전에 검사해요. Content-Length와 읽는 중 누적 크기는 10장×5MiB + 1MiB(51MiB)까지예요. 파일 10개·일반 필드 2개를 넘기면 422예요.
MEDIA_DIR의 UUID 파일로 저장하고 DB에는 경로·형식·크기·sha256만 둬요. 생성 실패 때 저장한 파일도 정리해요.
mock은 MEDIA_DIR/mock 아래를 쓰고 초기화 때 그 폴더만 비워요. DB 파일은 그대로 둬요.
원장은 원 칸 글만 hidden으로 숨겨요. 숨긴 글·사진은 모든 일반 조회·파일에서 404이고 목록에서도 빠져요.
같은 기관 작성자는 반 이동·퇴소로 칸 권한을 잃어도 숨긴 글까지 삭제할 수 있어요.
삭제는 deleted_at·이력을 커밋한 뒤 사진 파일을 디스크에서 지워요. 커밋 실패 때는 글·사진·파일을 보존해요.
데모는 두 모드가 같은 UUID로 반 글 2개·원 글 2개·2×2 단색 PNG 5장을 써요.

### 3.30 [제안][선택] v0.8 화상상담

팀 결정 D24의 12/9 판단 전에는 별도 브랜치에서만 준비해요. 화면은 후속이에요.
`FEATURE_VIDEO_CONSULT`는 기본 false예요. 꺼지면 인증 여부와 무관하게 공통 오류 404 `NOT_FOUND`예요.

| 칸 | 계약 |
| --- | --- |
| 요청 | `GET /api/v1/consultations/{booking_id}/room`, Bearer 인증, 본문 없음 |
| 참여자 | confirmed 예약의 teacher_id 한 명과 requests.requester_id 보호자 한 명 |
| 시간 | 예약 시작 - 10분부터 coalesce(expected_end_at, 예약 종료) + 30분까지, 양끝 포함 |
| 200 | `{booking_id, opens_at, closes_at, ice_servers, signal_path, ticket, ticket_expires_at}` |
| 접속권 | 60초 JWT, aud=consult-signal, sub=사용자, booking=예약, role=역할, jti=일회용 식별자. 일반 API Bearer로 쓸 수 없어요 |
| 실패 | 같은 기관의 다른 사람은 403 `FORBIDDEN` + permission_denied, 다른 기관·없는 예약은 404 |
| 상태·시간 | 확정 외 상태는 409 `CONFLICT`. 시간 밖은 같은 코드와 details.reason=room_not_open 또는 room_closed, details.opens_at·closes_at |

응답 시각은 오프셋을 담은 ISO 8601이에요. `Cache-Control: private, no-store`로 접속권 캐시를 막아요.
`VIDEO_ICE_SERVERS`는 JSON 배열이고, 기본은 `[{"urls":"stun:stun.l.google.com:19302"}]`예요.
기능이 켜졌을 때는 설정을 엄격히 검사하고, 꺼졌을 때 잘못된 값이면 경고 후 기본 STUN을 써요.
TURN의 urls·username·credential을 넣으면 그대로 돌려줘요. 서버가 외부 회의 서비스에 접속하지 않아요.

`WS /api/v1/consultations/{booking_id}/signal?ticket=…`은 접속 때 서명·만료·aud·예약·현재 사용자 활성/토큰 판·역할·참여자·시간을 다시 검사해요.
켠 상태의 검사 실패는 연결을 수락한 뒤 1008 access_denied로 닫아요. 꺼졌을 때는 HTTP handshake 404 공통 오류로 거절해요.
접속권은 한 번만 쓰고, 쓴 jti는 만료 시각까지만 메모리에 보관해요. 재접속은 room에서 새 접속권을 받아요.
접속 뒤 메시지를 처리하기 전 마지막 검사에서 10초가 지났으면 계정 활성·토큰 판·예약 상태·참여자·시간을 다시 검사해요.
실패한 연결만 1008 access_denied(마감이면 room_closed)로 닫고 상대에게 peer_left를 알려요.
조용한 연결도 closes_at에 권한·시간을 다시 확인해요. 지연 신고로 연장됐으면 새 마감까지 기다리고, 끝났으면 1008 room_closed로 닫아요. 서버가 닫으면 화면은 RTCPeerConnection을 닫아요.
uvicorn 접속 로그의 ticket 값은 가려요. 방별 잠금은 방 상태만 바꾸고, 보내기·이력 저장은 잠금 밖에서 해요.
보내기가 2초를 넘으면 잠금 안에서 수신자를 방에서 빼고 남은 상대에게 peer_left를 알려요. 닫기 프레임을 기다리지 않고 수신 작업을 취소해 연결을 끝내요.
역할마다 한 연결만 두고, 같은 사람이 다시 접속하면 옛 연결을 1008 replaced로 닫아요.
상대가 들어오면 두 사람에게 `{type: peer_joined}`, 나가면 남은 사람에게 `{type: peer_left}`를 보내요.
메시지는 JSON `{type: offer|answer|ice|bye, data}` 두 칸만 받고 상대에게 그대로 전달해요.
한 메시지 UTF-8 64KiB 이하, 연결마다 최근 1초에 20개 이하예요. 초과·잘못된 JSON·binary는 1008이에요.
`bye`도 전달한 뒤 보낸 연결을 1000으로 닫아요. 상대가 없으면 신호를 보관하지 않아요.
영상·음성은 브라우저끼리 WebRTC로 직접 주고받아요. 서버는 SDP·ICE·영상·음성을 저장하거나 기록하지 않아요.
`video_joined`·`video_left`는 booking_id와 예약 request_id만 이력에 연결해요(0011).
방 목록은 현재 API 프로세스 하나의 메모리예요. 여러 API 프로세스로 늘릴 때는 신호 공유 방식을 먼저 바꿔야 해요.

플래그를 켠 시드에서 데모 기관에 확정 예약이 없으면 가상 예약을 채워요.
확정된 데모 예약 …0901은 시드할 때마다 지금 입장할 수 있게 옮겨요.
시작은 지금-5분과 KST 당일 00:00 중 늦은 값을 5분 단위로 내려요. 끝은 시작+30분과 당일 23:59 중 이른 값이에요.
늦은 밤에도 같은 규칙을 쓰며 시간 때문에 생략하지 않아요. 시드는 예상 종료(expected_end_at)를 NULL로 두어요.
mock·DB 시드는 now를 받으며 생략할 때만 실제 시각을 읽어요. 시험은 고정 시각을 넘겨요.
새 가상 예약도 같은 시간 범위를 써요. 담임·상담실 시간이 겹치면 갱신을 건너뛰고 경고해요. 다른 예약은 바꾸지 않아요.
mock·DB가 같은 예약 `…0901`·요청 `…0790`, teacher01·parent01을 써요. 데모 외 기존 예약과 취소·완료한 데모 예약은 그대로 둬요.

#### 가상 음성 분석(API 51~53)

실제 사람의 녹음은 쓰지 않아요. `FEATURE_VOICE_ANALYSIS`는 기본 false이고, 꺼지면 세 경로 모두 공통 404예요.
상담방 플래그·접속 시간과 독립적이에요. 접수는 confirmed·done 예약만 가능하고 cancelled는 409 CONFLICT예요.
이미 있는 분석 조회는 예약 상태와 상관없어요.

| 칸 | 계약 |
| --- | --- |
| 접수 | `POST /consultations/{booking_id}/voice-analyses`, Bearer, multipart `file` 한 개와 `synthetic=true` 필수 |
| 파일 | 첫 바이트로 audio/wav·audio/mpeg·audio/webm·audio/mp4를 확인해요. 이름·선언 MIME은 믿지 않아요. 파일 10MiB 이하예요 |
| 쓰기 권한 | 예약의 teacher_id 한 명만 가능해요. 원장·다른 교사·보호자는 403 `FORBIDDEN`과 permission_denied 이력이에요 |
| 읽기 | `GET /consultations/{booking_id}/voice-analyses` → `{items:[분석]}`, 생성 시각·UUID 내림차순. `GET /voice-analyses/{analysis_id}` → 분석 한 개 |
| 읽기 권한 | 그 예약 담임과 같은 기관 원장만 가능해요. 보호자·다른 교사는 403과 이력, 다른 기관·없는 자원은 404예요 |
| 분석 공통 칸 | `{id, booking_id, status, transcript, result, duration_seconds, sha256, created_at, started_at, completed_at}` |
| 요약 result | `{summary: 문자열(3줄 이하), parent_requests: 문자열 배열, follow_ups: 문자열 배열}` |
| 202·상태 | 접수 응답은 queued, 이후 running → succeeded 또는 failed예요. 중단된 queued도 정리 때 failed가 돼요. 미완료·실패의 transcript는 빈 글, result는 빈 요약·배열이에요 |
| 실패 | synthetic 누락·false·잘못된 파일·복수 파일은 422 `VALIDATION_FAILED`, 10MiB 초과는 413 같은 코드예요 |

WAV 파싱 오류는 422예요. MP4는 M4A ·M4B ·mp42·mp41·isom·iso2·dash 브랜드만 받고 사진·QuickTime 브랜드는 거절해요.
EBML은 DocType=webm만 받아요. ID3는 10바이트 헤더·동기안전 태그 크기를 확인하고, 태그(선택 footer 포함) 바로 다음에 MPEG 프레임 동기가 있어야 해요.
길이 duration_seconds는 WAV의 선언 프레임 수와 실제 data 프레임 수 중 작은 값 또는 분석기 결과로 채워요. 알 수 없는 압축 음성은 null이에요.
녹취·요약·요청·후속 조치 글의 NUL 글자는 지우고 저장해요.
시각은 오프셋이 있는 ISO 8601이고 시작·완료 전 시각은 null이에요. 세 응답에 private, no-store를 붙여요.
`CONSULT_VOICE_ANALYZER` 기본은 `app.modules.consultations.voice_stub:analyze`예요. 입구는 Path → `{transcript,result,duration_seconds?}`예요.
`openai`를 고르면 `OPENAI_STT_MODEL`(기본 gpt-4o-mini-transcribe)로 녹취하고 agents/llm.py의 DOCUMENT 모델로 요약해요.
DB의 RUN_IN=api는 BackgroundTasks, RUN_IN=worker는 Celery default 큐에 분석 ID만 넘겨요. mock은 RUN_IN과 상관없이 같은 프로세스에서 실행해요.
상태 검사가 한 실행만 가져가요.
분석 제한은 300초예요. 초과·잘못된 결과·분석기 예외는 failed이고 늦은 결과는 저장하지 않아요.
5분 점검은 worker 모드에서만 돌아요. yuchion.sweep은 300초 넘은 queued·running을 failed로 끝내며 재실행하지 않아요.
api 모드는 시작할 때 미완료 queued·running을 모두 failed로 끝내고 파일을 지워요. 정리는 기능 플래그가 꺼져도 해요.
파일은 MEDIA_DIR 아래 UUID 이름으로 잠시 두고, 성공·실패·시간 초과 모두 상태 커밋 뒤 지워요. 삭제 실패는 경고만 남겨요.
DB에는 음성 바이트를 넣지 않으며 끝나면 임시 경로도 비워요. 다시 듣기·파일 다운로드 API는 없어요.
0012는 consultation_voice_analyses와 요청 연결 voice_analysis_requested·voice_analysis_completed를 더해요.
이력에는 녹취·요약·원본 이름·분석기 예외 원문을 남기지 않아요.
`tools/make_virtual_voice.py <저장소 밖 경로.wav>`는 가상 대본 두 목소리로 WAV를 만들어요. 저장소 안 출력은 거절하고 키가 없으면 안내만 해요.
음성 파일은 저장소에 넣지 않아요. 시험은 코드로 만든 무음 WAV·가짜 분석기·가짜 OpenAI 호출만 써요.

## 4. 검증과 권한 규칙

### 4.1 형식 검사(422)와 서버 검사(403·404·409)를 나눈다

| 검사 | 어디서 | 실패하면 | 예 |
| --- | --- | --- | --- |
| 형식: 타입·허용 값·길이·날짜 형식 | Pydantic(`Literal`·`Field`) | 422 `VALIDATION_FAILED` | `type = "unknown"`, `body` 2,001자 |
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
| 원장·원감 | 원 전체 | 카드 결정(원장 보고 카드 포함)·원장 지시·재배정·원장 현황·자료 올리기. 단 민원 회신 카드의 승인·처리 완료는 하지 않는다(T04 3.2 '원장 보고 후에도 회신은 담임 승인'). 원장은 지시를 남기거나 다른 교사에게 재배정한다. 하려 하면 403 `FORBIDDEN_ROLE` |

모든 조회와 변경은 토큰의 `org`로 먼저 거르고, 그다음 반·사람 범위를 본다. 범위 밖 자원은 403이 아니라 404로 답하고 `events`에 `permission_denied`로 남긴다(DB 설계서 4.4). 이 규칙은 AI 보안 가드레일 문서(T52)의 권한표와 같아야 한다. [제안] T54의 같은 기관 반 칸 거부는 3.29의 403 FORBIDDEN 예외예요.

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
| ④ 사람 승인 상태 | 학부모에게 나가는 일(회신 발송·예약 확정·알림장 발송)은 도구로 하지 않는다. 담임의 결정 API가 승인 기록(`approvals`)을 남긴 뒤에만 일어난다. 예외는 담임이 이미 승인한 '원에 남은 답'의 바로 답(5.7, FR-20) 하나다 | 도구 목록에 없음 |

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
| `propose_rule` | 기억 | 같은 주인·이유 코드 3번(마지막 decline 뒤 새 기억만). rule_json은 객체, after·before는 HH:MM | `rule_id`(이미 있으면 기존 ID) | `SAVE_FAILED`(참), `VALIDATION_FAILED`(거짓) | 1번 다시 → 실패면 제안만 되돌리고 tool_failed 기록(카드 거절·기억은 유지, 다음에 다시 셈) |
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

**사람에게 넘기고 자동 답변하지 않는 기준.** 긴급(`risk_level = urgent`)·판단 필요(`uncertain`) 민원, 근거 없음(`no_evidence`), 문서 충돌, 검사 AI가 2번 돌려보낸 뒤에도 통과 못 함(3번째, FR-08), 권한 밖이면 학부모에게 나가는 답은 없고 초안 없는 사람 카드로 넘긴다. 권한 밖 자료는 읽지 않으며, 카드도 현재 사용자의 범위 안에서만 만든다. 학부모에게 나가는 모든 답은 담임 결정 API가 승인 기록(`approvals`)을 남긴 뒤에만 나간다(5.3 ④). 접수 안내·정보 되묻기는 답변 발송과 구분한다. **예외는 원에 남은 답 하나다(FR-20, T04 5.1 합의 7).** 담임이 이미 승인해 저장한 문의 답이라, 감독 AI가 `find_saved_answer`로 찾은 답의 `similarity`가 기준 이상이고 `sources_current = true`이며 요청이 긴급·판단 필요가 아니면, 카드 없이 그 답과 출처로 바로 답한다(요청 `classified → sent_or_booked`, 이력에 `saved_answer_id`). 기준값은 평가 뒤 정한다(T14 7장 2번). 모의 API는 이 바로 답을 흉내 내지 않는다.

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

**카드가 끝내 안 생긴 요청.** 요청은 `POST /requests`에서 먼저 저장되므로, AI가 카드 만들기(`create_card`)까지 실패하거나 처리 중에 멈춰도 요청은 남아 있다. 서버 점검 작업이 5분마다 진행 중 상태(`received`·`classified`·`assigned`)로 5분 넘게 카드가 없는 요청을 찾아, 처음에는 처리를 한 번 다시 넣고 `agent_requeued` 이력만 남긴다. 다시 넣은 뒤 5분이 지나도 카드가 없으면 초안 없는 카드를 담당 없이 만들고(받은함 '미배정') 요청을 `awaiting_review`로 바꾼다. 넘긴 이유 `card_missing`은 이력 `events.detail.handoff_reason`에 남긴다. 학부모 화면에는 그동안에도 '접수됨'이 보이고, 채팅 안내도 '받았지만 선생님 확인이 늦어질 수 있음'이라 화면과 말이 어긋나지 않는다. 모의 API는 이 점검 작업을 돌리지 않고, 실제 서버의 백그라운드 워커에서 돈다.

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

아래는 `schedule.py`로 계산한 값이다. 시간대는 모두 한국 표준시(+09:00), 설정은 `HOLIDAYS=2026-12-25`, `WORK_HOURS=09:00-18:00`, `IMMEDIATE_RISK_CATEGORIES=child_safety`다. 2026년 12/25(금)이 공휴일이라, 공휴일 전날(12/24 목) 뒤로 공휴일과 주말 사흘을 건너뛰는 경우를 함께 본다. 학부모 열은 그 접수 시각에 보낼 알림이 생겼다고 가정한 계산값이다. 이 표의 민원은 접수만으로 학부모 답변·알림을 만들지 않으며, 회신 알림은 승인·발송 시각에 다시 계산한다.

| 상황 | 접수 시각 | 요청 종류·위험 | 교직원 알림 `deliver_after` | 학부모 알림 | 처리 기한 `due_at` | 지연 표시가 켜지는 시각(`is_delayed = due_at < now()`) |
| --- | --- | --- | --- | --- | --- | --- |
| 금요일 퇴근 뒤 | 2026-12-18 금 18:30 | 민원 일반(`complaint`, `normal`) | 12/21 월 09:00 | 발생 즉시(가정: 12/18 18:30) | 12/21 월 18:30 | 12/21 18:30 초과부터 |
| 공휴일 전날 근무 중 | 2026-12-24 목 17:30 | 민원 일반(`complaint`, `normal`) | 12/24 목 17:30 | 발생 즉시(가정: 12/24 17:30) | 12/28 월 17:30 | 12/28 17:30 초과부터 |
| 공휴일 전날 퇴근 뒤 | 2026-12-24 목 18:30 | 민원 일반(`complaint`, `normal`) | 12/28 월 09:00 | 발생 즉시(가정: 12/24 18:30) | 12/28 월 18:30 | 12/28 18:30 초과부터 |
| 아이 안전 긴급, 근무 밖 | 2026-12-18 금 20:00 | 민원 긴급(`urgent`, `child_safety`) | 12/18 금 20:00 | 발생 즉시(가정: 12/18 20:00) | 12/18 금 22:00 | 12/18 22:00 초과부터 |
| 교직원 위협 긴급, 근무 밖 | 2026-12-18 금 20:00 | 민원 긴급(`urgent`, `staff_attack`) | 12/21 월 09:00 | 발생 즉시(가정: 12/18 20:00) | 12/18 금 22:00 | 12/18 22:00 초과부터 |

기한과 같은 시각에는 지연이 아니다. 마지막 사례는 알림이 오기 전에 지연이 켜진다. 이는 긴급 2시간과 교직원 알림 예외가 서로 다른 규칙이기 때문이다. `test_documented_holiday_notification_examples`가 표의 다섯 행과 기한 경계(같은 시각·1마이크로초 뒤)를 고정한다.

#### 6.6.2 상담 종료·지연 알림(T48)

Beat가 1분마다 시작이 하루 이내인 확정 예약을 읽어요. 실제 알림을 넣을 예약만 잠가요.
종료 알림 `consultation_ending`은 시작 이후·예상 종료 10분 전 이상·종료 미만일 때 담임에게 남겨요.
지연 시각이 없으면 원래 종료를 써요. 상담 중인 담임 안내라 근무 시간 밖에도 바로 생성·발송해요.
주기가 늦으면 종료 전까지만 따라잡고, 종료 뒤에는 지난 알림을 만들지 않아요.

지연은 시간 경과로 추측하지 않아요. 3.28의 [제안] HTTP가 담임의 예상 종료를 기록해요.
같은 트랜잭션에 `consultation_delay_reported` 이력을 남겨요. 완료·취소는 지연 신호가 아니에요.
앞 상담이 시작됐고 명시된 예상 종료가 같은 기관·담임 또는 상담실을 쓰는 뒤 예약 시작보다 늦으면,
뒤 예약의 담임·신청 학부모에게 `consultation_delayed`를 남겨요. 앞 학부모·아이 정보는 넣지 않아요.
대체 시간은 예상 종료 뒤 14일 안 최대 세 개예요. 근무일·시간·활성 상담실·담임 일정·확정 예약의
연장 구간·살아 있는 학부모 체크·승인된 시간 규칙을 적용해요. 빈 시간이 없으면 다른 날짜를 안내해요.
제안은 예약·체크를 바꾸지 않아요. 예약 변경·취소는 3.28의 후속 계약이에요.

키는 예약·종류·종료 예정 시각(종료 알림) 또는 지연 끝 until(대체 시간)·수신자로 만들어요.
같은 값의 재실행은 중복을 만들지 않아요. 지연이 바뀌면 새 종료 알림과 대체 시간을 다시 계산해요.
옛 pending 알림은 held로 돌리고, 보낸 알림은 보존해요. 옛 제안은 `consultation_reminded` 이력에
`outcome=superseded`와 알림 ID를 한 번 남겨요. 새 생성 이력에는 until·제안 시각을 남겨요.
지연 값이 그대로인 채 끝나면 superseded 이력을 남기지 않아요.
대체 시간 알림은 기존 교직원 근무 시간 규칙을 유지하고, 미룬 시각이 예약 종료 이상이면 만들지 않아요.
발송·재시도 때 종료·완료·취소됐거나 현재 지연 값과 어긋난 알림은 held로 남겨요.
**발송 기록만 held, 목록 노출은 유지**해요. 목록은 원래 deliver_after 기준이에요.
DB 워커에서 주기 실행하고 mock은 HTTP 입력 직후 같은 점검을 실행해요.

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
| 마지막 AI 초안(내부 저장) | `daily_notes.ai_original` | 0003. 교사 수정은 원본을 바꾸지 않으며 수정하지 않은 미확인 초안 재생성 때 갱신함. 기존 행은 적용 시점 content로 채움 |
| 알림장 상태 이력 | `events.daily_note_id` | 기관 복합 FK. daily_note_drafted·daily_note_edited·daily_note_confirmed·daily_note_sent |
| 내 기억 목록·삭제 | `memories` | owner_id=본인, deleted_at 비어 있는 행. 삭제는 deleted_at 표시 |
| `child_memos[]` | `daily_note_inputs.child_memos` | 0002에서 추가한 jsonb NOT NULL DEFAULT '[]'::jsonb, 배열 CHECK. 아이 UUID·중복·소속·메모 길이는 API가 검사함(DDL·DB 설계서 v0.8) |
| `notes[].status` · `content` · `open_checks[]` | `daily_notes.status` · `content` · `open_checks` | 같음 |
| `ingest_status` | `documents.ingest_status` | 같음 |
| `chunk_count` | — | 저장하지 않음. 그 문서의 `document_chunks` 개수 |
| 넘긴 이유(`ai_timeout`·`ai_failed`·`card_missing`, 분류 결과의 `handoff_reason`) | `events.detail->>'handoff_reason'` | 칸을 따로 두지 않고 이력에 넣음 |
| `notification.kind` · `read_at` | `notifications.kind` · `read_at` | 같음 |
| `completed_unconfirmed` 등 원장 현황 숫자 | `director_overview` 뷰 | 뷰의 칸 이름 그대로 |
| 피드 글·사진·아이 표시·공개 범위([제안]) | `feed_posts` · `feed_photos` · `feed_photo_children` · `children.photo_scope` | 3.29. 사진 바이트는 파일에 두고 file_url은 인증 API 주소로 계산해요 |
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
| `MEDIA_DIR` | `var/media` | [제안] 피드 파일 저장 폴더. mock은 mock/만 초기화하고 DB 파일은 보존해요 |
| `MOCK_STREAM_DELAY_MS` | `300` | 모의 SSE 이벤트 사이 간격(밀리초). 음수는 0으로 처리 |
| `LLM_MODEL_DEFAULT` | `gpt-6-luna` | 역할별 모델을 비워 두면 쓰는 모델(D27) |
| `LLM_MODEL_SUPERVISOR` | (비움) | 감독 AI 모델 |
| `LLM_MODEL_DOCUMENT` | (비움) | 자료 AI 모델 |
| `LLM_MODEL_MEMORY` | (비움) | 기억 AI 모델 |
| `LLM_MODEL_CHECKER` | (비움) | 검사 AI 모델 |
| `LLM_MODEL_CODE` | (비움) | 코드 AI 모델 |
| `DAILY_NOTE_WRITER_TIMEOUT` | `300` | 초안 입구 함수의 대기 제한(초). 초과하면 failed이고 늦은 결과는 저장하지 않음 |
| `NOTE_DRAFT_CONCURRENCY` | `5` | 그래프에 전달하는 아이별 초안 동시 실행 수. 지원하는 그래프에서 적용 |
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
| `R-DEMO-08` · `R-DEMO-10` | 하늘 문의 "기침해요" · 노을 귀가 "오늘 할머니가 데리러 가요"(가상) | `requests` | `…000000000708` · `…00000000070a` |
| `K-DEMO-01` · `K-DEMO-02` | 상담 후보 카드 · 민원 회신 카드 | `cards` | `…000000000801` · `…000000000802` |

피드 글 `e01`~`e04`(반 2·원 2)는 `feed_posts`의 `…000000000e01`~`…000000000e04`, 사진 `f01`~`f05`는 `feed_photos`의 `…000000000f01`~`…000000000f05`예요([제안] 가상 단색 PNG).

별빛반(`…0101`, 만 4세, teacher01)은 기존 하늘·노을과 PR #262 `roster_c4.json` 명단 18명을 합쳐 20명이다. 명단의 `C4-NN`은 `demo_id("54NN")`으로 옮겼고, 추가한 아이에게는 보호자가 없다. 햇님반(`…0102`, 만 5세, teacher02)은 바다 1명이다. 반 이름·교사 표시 이름은 develop의 모의 시드와 같고, 이름·순서는 `apps/api/app/mock/seed.py`에서 볼 수 있다.

알림장 연결용 두 요청은 모의 저장소 초기화 날짜에 접수 상태로 넣고, 문의·귀가 처리 카드는 아직 만들지 않는다.

그 밖의 데모 요청(…703~707)·문서(…b01~b03)·규칙(…d01)은 `apps/api/app/mock/seed.py`를 참고한다.

## 변경 이력

| 판 | 날짜 | 내용 | 작성 |
| --- | --- | --- | --- |
| v0.1 | 2026-11-18 | 초안. API 목록 29개, 핵심 6개 상세 명세, 화면용 조회 칸(3.7, T12 #254 리뷰), 검증·권한 규칙, 도구 실패 코드·실패 후 처리, 실행 규칙(기한 계산·알림 발송 시각 포함, T10 회의 결과), API 필드↔DB 컬럼 대응, 설정값 | 태웅 |
| v0.2 | 2026-11-18 | 나머지 API 상세 명세(3.8~3.23)를 모의 API·OpenAPI와 대조해 채움. 29개 상세 절 연결, 모의 API 안내·설정값·데모 ID 보완 | 태웅 |
| v0.3 | 2026-11-20 | 영민 #256 리뷰 반영: `find_consult_slots` 실패 코드에 `TOOL_TIMEOUT` 추가(YC-F01), 에이전트 허용 목록은 T43부터 적용(5.3 ①), `create_card` 끝내 실패 시 학부모 안내('받았지만 늦어질 수 있음', 화면의 '접수됨'과 같게)와 서버의 미배정 재올림(5.4·6.3). 강사 11/18 피드백 2·3·4번: 세 업무 흐름·사람 인계·도구 이름 대조(5.7), 서버 설정 위치·WORK_HOURS·IMMEDIATE_RISK_CATEGORIES(6.5·6.6·8장), 공휴일·퇴근 뒤 실계산 예시(6.6.1), 화면·API·DB 대표 사례와 시험 기록(6.7), notify_failed 경고(3.7·5.4). T04에 맞춰 원에 남은 답 바로 답 예외(5.3 ④·5.7)와 민원 회신·완료는 원장이 하지 않음(4.2) 명시 | 태웅 |
| v0.4 | 2026-11-20 | 알림장 아이별 child_memos, child 줄, 확인 항목 kind 8값·sentence·선택 request_id, API 30 반 아이 목록을 추가함. 모의 API·OpenAPI를 맞추고 반·교사 이름은 develop 기준으로 유지함. PR #262 별빛반 명단 18명은 C4-NN → 54NN으로 맞춤. 아이 입력에 그날 보호자 requests를 더하고 request_missed 누락 예시·요청 출처 줄·문의와 귀가 시드 두 개를 연결함. T10 v0.9·0002 저장 열·PATCH child 허용 값을 대조함 | 태웅 |
| v0.4.1 | 2026-11-20 | 보호자 문의 줄 inquiry를 추가해 반 공통 day와 구분함. inquiry 출처는 request이며 수정·조회·모의 API·OpenAPI·T10 v0.10을 맞춤. 초안 제한 300초·동시성 설정을 반영함 | 태웅 |
| v0.5 | 2026-11-20 | 0003 알림장 최초 원본·아이별 이력, API 31·32 내 기억 조회·삭제, API 33 미확인 초안 재생성·실패/중단 복구를 추가함. T10 v0.11·모의·DB·OpenAPI를 맞춤 | 태웅 |
| v0.5.1 | 2026-11-20 | 재생성 때 마지막 AI 초안을 저장하고 교사 수정본을 보존함. kept_edited·실행 중 재요청 재사용·요청자 기록·수정/확인 취소 이력을 구분함. T10 v0.12·모의·DB·OpenAPI를 맞춤 | 태웅 |
| v0.5.2 | 2026-11-20 | 상담 SLOT_PAST·체크 충돌·보류/원장 보고 중 체크 보존·지시 후 확정과 동시 예약 잠금을 모의·DB·OpenAPI·T10 v0.13에 맞춤 | 태웅 |
| v0.5.3 | 2026-11-20 | T48 상담 종료 10분 전·명시된 지연의 대체 시간 알림 2종과 내부 지연 기록 입구·주기·중복/만료 기준을 추가함. 공개 HTTP 경로는 유지하고 T10 v0.14·0007·OpenAPI를 맞춤 | 태웅 |
| v0.6 [제안] | 2026-11-21 | T48 지연 입력 API 37·당일/3시간 상한·시각별 재알림·superseded·근무 밖 종료 알림을 더했어요. 예약 변경/취소는 후속이에요. | 태웅 |
| v0.6 초안 | 2026-11-20 | 팀 확인 전 T46 투약·귀가 등록·인계자 조회·교직원 확인/완료(API 34~36), 알림장 request_status·접수/확인 알림을 더했어요. | 태웅 |
| v0.6 [제안] | 2026-11-21 | T46 미등록 인계자 경고·투약 누락·보호자 추가 글 재확인과 version·즉시 귀가 알림·교직원 목록 sort를 맞췄어요. FR-16·AC-09를 따르며 head 0009는 같아요. | 태웅 |
| v0.7 [제안] | 2026-11-21 | T54 반·원 피드·앨범·사진 범위 API 38~49와 0010·가상 시드를 더했어요. 반 칸 교직원 거부·읽을 때 사진 공개 범위·파일 삭제를 두 모드로 검사해요. | 태웅 |
| v0.7.1 [제안] | 2026-11-21 | T54 업로드 413·권한 검사 순서·커밋 뒤 파일 삭제·작성자 삭제 권한·mock 파일 초기화를 맞추고 표·필드 대응·설정·예시 ID를 보완했어요. T10 v0.18을 가리켜요. | 태웅 |
| v0.8 [제안][선택] | 2026-11-22 | T56 room(API 50)·signal WebSocket·기본 꺼짐 플래그·60초 접속권·0011 입퇴장 이력을 더했어요. | 태웅 |

변경 이력 v0.8 · 2026-11-22 [제안][선택] — 가상 음성 분석 API 51~53, 기본 대역·OpenAI 선택·300초 제한·원본 삭제·0012를 더했어요.
