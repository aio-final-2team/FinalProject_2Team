# contracts/mock_api — 화면을 먼저 붙여 보는 모의 API

실제 백엔드(DB·에이전트)가 준비되기 전에 화면을 만들 수 있도록, [API 설계 문서](../../Docs/Step2/API_설계_문서.md)의 v0.4 API 30개를 가상 데이터로 답하는 서버입니다. 경로·필드·오류 형식이 실제 API와 같아서, 나중에 백엔드가 바뀌어도 화면 코드는 그대로 씁니다. 코드는 `apps/api/app` 안에 있고(실제 API와 같은 앱), 이 폴더에는 쓰는 법만 둡니다.

**처음 쓰는 순서**

1. 서버를 켭니다(아래).
2. `http://localhost:8000/docs`를 열고 `POST /api/v1/auth/login`에 아래 계정 하나로 로그인합니다.
3. 받은 `access_token`을 오른쪽 위 **Authorize**에 넣고 다른 API를 눌러 봅니다.

## 켜는 법

저장소 맨 위 폴더에서 실행합니다.

```bash
docker compose up api
```

Docker 없이 켤 때는 Python 3.12 가상환경에 `apps/api/requirements.txt`를 설치한 뒤 실행합니다.

```bash
PYTHONPATH=apps/api uvicorn app.main:app --port 8000
```

- 자동 문서 `http://localhost:8000/docs`, 상태 확인 `http://localhost:8000/health`
- API 경로는 모두 `/api/v1`로 시작하고, 로그인 뒤에는 `Authorization: Bearer <access_token>` 헤더를 보냅니다.
- 웹 화면(`http://localhost:5173`)에서 부르는 것은 기본으로 허용돼 있습니다. 다른 주소면 `CORS_ORIGINS`에 쉼표로 더합니다.

## 데모 계정

비밀번호는 모두 `demo1234`입니다(모의 API 전용 값).

| 아이디 | 역할 | 쓰임 |
| --- | --- | --- |
| `parent01` | 학부모 | 햇살반 하늘이 보호자. 요청 만들기·시간 체크·'확인했어요' |
| `parent02` | 학부모 | 별빛반 바다·햇살반 노을이 보호자. 남의 요청이 안 보이는지 확인 |
| `teacher01` | 담임 | 햇살반. 받은함·카드 결정·상담 확정·알림장 |
| `teacher02` | 담임 | 별빛반. 다른 반 카드가 404로 막히는지 확인 |
| `director01` | 원장 | 원 전체. 원장 보고 지시·재배정·원장 현황 |

처음부터 들어 있는 데이터: 상담 요청(시간 고르기 단계), 담임 확인을 기다리는 민원, 긴급 민원(원장 보고), 판단 필요 민원, 보류 카드, 끝난 문의, 담당 없는 문의, 식단표·행사 안내·옛 판 문서, 담임 규칙 제안. 고정 ID는 `apps/api/app/mock/seed.py`와 계약표 부록 A에 있습니다.

햇살반(`…0101`, 만 5세)은 기존 하늘·노을에 PR #262 가상 명단 18명을 더해 20명이에요. 별빛반(`…0102`, 만 4세)은 바다 1명이에요. 추가한 18명은 보호자 계정이 없어요. 기존 UUID·로그인 ID·비밀번호는 같아요.

## 알림장 v0.4

먼저 `GET /api/v1/classrooms/{classroom_id}/children`으로 아이 목록을 받아요. 이름순이고 응답은 `{ "items": [{ "id", "display_name", "classroom_id" }] }` 모양이에요. 현재 배정 기간 안인 담임·같은 기관 원장이 볼 수 있어요. 학부모는 403 `FORBIDDEN_ROLE`, 범위 밖 반은 404 `NOT_FOUND`예요.

`POST /api/v1/daily-notes/drafts`에 `child_memos`를 선택으로 더할 수 있어요. 예를 들어 `"child_memos": [{"child_id": "00000000-0000-4000-8000-000000000501", "memo": "블록으로 높은 탑을 쌓음"}]`처럼 보내요. memo는 1~500자이고, 같은 아이를 두 번 넣거나 그 반 아이가 아니면 422 `VALIDATION_FAILED`예요. 다른 반·다른 기관·없는 아이면 `error.details.child_id`에 보낸 ID가 와요.

모의 초안은 메모를 그대로 `content.items[]`의 `key: child`, `source.type: teacher_input` 줄에 넣어요. 메모를 생략하거나 공백만 보내면 그 아이의 child 줄이 없어요. 확인 항목은 `{ id, item_key, kind, problem, sentence }` 모양이에요. kind는 `not_in_memo`·`sensitive`·`other_child`·`date_check`·`absent`·`draft_failed`·`check_failed` 중 하나예요. problem은 설명, sentence는 걸린 문장(없으면 null)이에요. 모의 생성은 첫 아이에게 기존 준비물 확인을 `date_check`로 남겨요. 해결할 때는 지금처럼 `resolved_checks`에 id만 보내요.

## 흐름 따라 해 보기

- **상담:** 학부모가 `POST /requests`(`type: consultation`) → `GET /requests/{id}`에서 후보 3개 확인 → `POST /requests/{id}/slot-choices`로 체크 → 담임이 `POST /cards/{id}/bookings`로 확정
- **민원:** 학부모가 `POST /requests`(`type: complaint`) → 담임이 `POST /cards/{id}/decisions`(`approve`) → 학부모가 `POST /requests/{id}/confirm` → 담임이 `decisions`(`complete`). 학부모가 확인하기 전에 끝내려면 `reason_text`가 있어야 하고, 없으면 409 `REASON_REQUIRED`입니다
- **알림장:** 담임이 `POST /daily-notes/drafts` → `GET /daily-notes?classroom_id=&date=`로 아이별 초안 → 확인 항목을 고치고 아이마다 `PATCH /daily-notes/{id}`(`confirm: true`) → `POST /daily-notes/send`. 하나라도 준비가 안 됐으면 409 `NOTE_BATCH_BLOCKED`입니다
- **AI 진행 표시:** `GET /requests/{id}/stream`(학부모, 단계만)과 `GET /cards/{id}/stream`(교직원, 초안 글자와 카드까지). 이벤트 사이 간격은 `MOCK_STREAM_DELAY_MS`(기본 300)입니다

## 실패 화면 만들어 보기

- 알림장 초안의 `activities`에 `[실패]`를 넣거나, 올리는 자료의 파일 이름에 `[실패]`를 넣습니다. 접수는 202로 되고, 상태 조회에서 `failed`와 `error.code = UPSTREAM_UNAVAILABLE`이 옵니다.
- 다른 반·다른 학부모 자료를 부르면 404, 역할이 다르면 403, 다른 사람이 먼저 처리한 카드는 409 `CARD_VERSION_CONFLICT`입니다.

## 알아 둘 것

- **데이터는 메모리에만 있습니다.** 서버를 다시 켜면 바꾼 것이 모두 사라지고 데모 데이터로 돌아갑니다. 서버는 프로세스 하나로 켭니다.
- 분류·초안·문서 적재·상담 후보는 시연용 규칙으로 바로 만듭니다. 실제 모델이나 외부 서비스는 부르지 않습니다.
- 처리 기한과 교직원 알림 시각은 API 설계 문서 6.5·6.6대로 계산합니다. 공휴일은 `HOLIDAYS=2026-12-25,2027-01-01`처럼 넣습니다.
- 계약 파일 `contracts/openapi.yaml`은 앱에서 뽑은 생성물입니다. API를 바꾼 뒤에는 `python apps/api/scripts/export_openapi.py`로 다시 뽑습니다(시험이 둘이 같은지 봅니다).
