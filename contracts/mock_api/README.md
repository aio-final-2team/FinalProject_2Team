# contracts/mock_api — 화면을 먼저 붙여 보는 모의 API

실제 백엔드(DB·에이전트)가 준비되기 전에 화면을 만들 수 있도록, [API 설계 문서](../../Docs/Step2/API_설계_문서.md)의 v0.9 HTTP API 60개와 신호 WebSocket(화상상담은 기본 꺼짐인 [제안][선택], 투약·귀가·상담 지연과 피드·앨범은 팀 확인 전 초안)를 가상 데이터로 답하는 서버입니다. 경로·필드·오류 형식이 실제 API와 같아서, 나중에 백엔드가 바뀌어도 화면 코드는 그대로 씁니다. 코드는 `apps/api/app` 안에 있고(실제 API와 같은 앱), 이 폴더에는 쓰는 법만 둡니다.

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
| `parent01` | 학부모 | 별빛반 하늘이 보호자. 요청 만들기·시간 체크·'확인했어요' |
| `parent02` | 학부모 | 햇님반 바다·별빛반 노을이 보호자. 남의 요청이 안 보이는지 확인 |
| `teacher01` | 담임 | 별빛반. 받은함·카드 결정·상담 확정·알림장 |
| `teacher02` | 담임 | 햇님반. 다른 반 카드가 404로 막히는지 확인 |
| `director01` | 원장 | 원 전체. 원장 보고 지시·재배정·원장 현황 |

처음부터 들어 있는 데이터: 상담 요청(시간 고르기 단계), 담임 확인을 기다리는 민원, 긴급 민원(원장 보고), 판단 필요 민원, 보류 카드, 끝난 문의, 담당 없는 문의, 식단표·행사 안내·옛 판 문서, 담임 규칙 제안, 알림장 연결용 하늘 문의·노을 귀가 요청. 고정 ID는 `apps/api/app/mock/seed.py`와 계약표 부록 A에 있습니다.

별빛반(`…0101`, 만 4세)은 기존 하늘·노을에 PR #262 `roster_c4.json` 가상 명단 18명을 더해 20명이에요. 햇님반(`…0102`, 만 5세)은 바다 1명이에요. 명단의 `C4-NN`은 `demo_id("54NN")`으로 옮겨요. PR #269 보호자 요청이 있는 16명은 `demo_id("44NN")`·`parent-c4-NN` 보호자 계정이 있고 비밀번호는 `demo1234`예요. 요청이 없는 C4-03·C4-17은 보호자가 없어요. 반·교사 표시 이름은 develop의 모의 시드와 같고, 기존 UUID·로그인 ID·비밀번호는 같아요.

## 알림장 v0.4.1

먼저 `GET /api/v1/classrooms/{classroom_id}/children`으로 아이 목록을 받아요. 이름순이고 응답은 `{ "items": [{ "id", "display_name", "classroom_id" }] }` 모양이에요. 현재 배정 기간 안인 담임·같은 기관 원장이 볼 수 있어요. 학부모는 403 `FORBIDDEN_ROLE`, 범위 밖 반은 404 `NOT_FOUND`예요.

`POST /api/v1/daily-notes/drafts`에 `child_memos`를 선택으로 더할 수 있어요. 예를 들어 `"child_memos": [{"child_id": "00000000-0000-4000-8000-000000000501", "memo": "블록으로 높은 탑을 쌓음"}]`처럼 보내요. memo는 1~500자이고, 같은 아이를 두 번 넣거나 그 반 아이가 아니면 422 `VALIDATION_FAILED`예요. 다른 반·다른 기관·없는 아이면 `error.details.child_id`에 보낸 ID가 와요.

모의 초안은 메모를 그대로 `content.items[]`의 `key: child`, `source.type: teacher_input` 줄에 넣어요. 메모를 생략하거나 공백만 보내면 그 아이의 child 줄이 없어요. 확인 항목은 `{ id, item_key, kind, problem, sentence, request_id? }` 모양이에요. request_id는 선택 UUID이고 생략·null이 가능해요. kind는 `not_in_memo`·`sensitive`·`other_child`·`date_check`·`absent`·`draft_failed`·`check_failed`·`request_missed`의 8개 중 하나예요. problem은 설명, sentence는 걸린 문장(없으면 null)이에요. 모의 생성은 첫 아이에게 기존 준비물 확인을 `date_check`로 남겨요. 해결할 때는 지금처럼 `resolved_checks`에 id만 보내요.

서버는 같은 기관·반·아이의 보호자가 그날 보낸 문의·투약·귀가 요청을 아이 입력의 `requests: [{request_id, type, text}]`로 모아요. 날짜는 요청 생성 시각을 한국 날짜로 바꿔 비교해요. 클라이언트가 초안 본문에 requests를 보낼 필요는 없어요. 모의 초안은 요청 원문을 `source.type: request`, `source.request_id` 줄로 옮겨요. 문의는 `inquiry`(출처 `request`만 허용), 투약·귀가는 `medication`·`pickup` 줄이에요. 반 공통 활동은 `day`에 남아서 문의와 함께 보여요.

추가된 가상 요청은 하늘의 문의 "기침해요"(`…0708`, parent01)와 노을의 귀가 "오늘 할머니가 데리러 가요"(`…070a`, parent02) 두 개예요. 서버 초기화 날짜로 초안을 만들면 하늘 요청은 들어가고, 노을의 고정 요청 하나는 일부러 빠져 `request_missed`·`request_id: …070a`·`sentence: null`이 떠요. 그날의 기존 문의 시드도 함께 읽어요. 다른 귀가 요청까지 누락시키지는 않아요. 담임이 내용을 보완한 뒤 해당 확인 id를 `resolved_checks`로 해결해야 확인·발송할 수 있어요.

PR #269 `guardian_requests.json`의 가상 요청 20개(투약 5·귀가 7·문의 8)도 들어 있어요. `GR-NN`은 `demo_id("72NN")`이고, 2026-11-16~20의 접수 시각·본문을 그대로 써요. 날짜별 요청 수는 2·4·6·5·3개예요. GR-12·13은 11/18 같은 아이의 두 요청으로 둘 다 들어가요. GR-11의 "내일은 할머니가 데리러 가요."는 보낸 날인 11/19에만 들어가요. 원본에서 C4-15의 관계가 mother·father로 달라, 계정 하나에는 처음 나온 mother를 유지해요.

투약·귀가 시드는 교직원과 신청 학부모가 원문·대화·상태를 읽어요. 기존 두 요청과 새 20개는 접수 상태이며 시드 때 처리 카드는 만들지 않아요. T46 초안은 `POST /requests`로 등록하고 교직원이 실제 확인·완료를 기록해요. 이름만 적힌 옛 귀가 시드는 인계자 UUID가 없어 새 요청으로 등록해야 해요. 대역은 원문을 옮겨요. 원본의 민감 정보·날짜·다른 아이 이름 함정 평가는 그래프 연결 뒤에 다뤄요.

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

T48 알림 두 종류 `consultation_ending`·`consultation_delayed`를 알림 목록·읽음에서 받아요.
종료 예정 10분 이내 담임 알림과, 명시된 상담 지연의 대체 시간 제안이에요.
[제안] v0.6 `POST /consultations/{booking_id}/delay`에 그 반 예약 담임의 JWT와
`{"expected_end_at":"2026-11-16T09:55:00+09:00"}`를 보내요.
시작한 상담·현재/원래 종료 뒤·같은 KST 날짜·원래 종료 + 3시간 이내만 받아요.
200은 booking {id,period,status,expected_end_at}·affected_bookings(뒤 확정 예약 수)예요.
입력 직후 점검이 대체 시간 알림을 만들어요. 같은 값은 중복 없이, 바뀐 값은 새 제안으로 보내요.
옛 pending은 held, 보낸 제안은 superseded 이력으로 남겨요. 발송 기록만 held, 목록 노출은 유지해요.
종료 알림은 근무 밖에도 즉시예요. 주기 실행은 DB 워커만 해요.
대체 시간을 받는 예약 변경/취소와 실제 종료 입력·화면은 후속 계약이에요. 시간 경과만으로 지연을 만들어 내지 않아요.

## 알림장 v0.5.1·내 기억

API 31 GET /memories는 담임 본인의 기억만 kind로 걸러 쪽을 나눠요. API 32 DELETE /memories/{memory_id}는 본인 기억을 지우고 204(본문 없음)로 답해요. 지운 기억은 목록에서 빠지고, 남의 기억은 404예요. 말투 기억은 미리 넣지 않아요.

API 33 POST /daily-notes/drafts/{input_id}/regenerate는 저장한 반 입력으로 미확인 초안을 다시 만들어요. ready와 교사 수정본(content ≠ ai_original 또는 daily_note_edited 이력)은 유지하고 sent가 하나라도 있으면 409 INVALID_TRANSITION이에요. 응답은 기존 초안 응답에 kept_edited(접수 시 보존한 미확인 수정본 수)를 더해요. failed와 시간 제한을 넘은 queued·running은 다시 받을 수 있고, 제한 안의 실행은 현재 상태를 돌려줘요. 모의는 즉시 처리하며 [실패] 입력은 계속 failed예요. DB는 BackgroundTasks로 queued→running→succeeded/failed를 처리해요.

선생님이 받은 마지막 AI 초안은 내부 ai_original로 보존하고 공개 NoteView는 그대로예요. 교사 수정으로는 원본을 바꾸지 않고, 미수정 초안 재생성 때 새 초안으로 바꿔요. 내용 변경만 daily_note_edited를 남기고 확인 취소는 returned로 ready→draft, 검사 해소는 checked로 needs_check→draft를 기록해요. 새 초안 이력과 반 묶음 카드에 재생성 요청자도 남겨요. 말투 추출·학습은 기억 AI가 맡아요.

## 상담 체크·확정 v0.5.2

이미 시작한 후보는 체크·확정 모두 409 `SLOT_PAST`예요.
다른 요청의 확정 예약·24시간 안 체크와 담임 또는 상담실 시간이 겹치면 체크할 때 409 `SLOT_TAKEN`이에요.
보류·원장 보고 중에는 24시간이 지나도 체크를 유지하고, 재개·원장 지시 뒤에 만료를 풀어요.
원장 지시 전에 확정하면 409 `INVALID_TRANSITION`이에요. 지시하면 보고 카드를 닫고 상담 카드로 돌려보내요.

## T46 v0.6 — 팀 확인 전 초안

투약·귀가 등록, 등록 인계자 조회(API 34), 교직원 목록(API 35)·실제 확인/완료(API 36)를 열었어요.
자기 요청 목록·상세·대화·SSE에서도 보여요. 실제 완료는 교직원 confirm 뒤 complete로만 기록해요.
[제안] 귀가는 등록 pickup_guardian_id 또는 미등록 pickup_name·pickup_relation을 받아요.
미등록도 접수·확인하고 unregistered_pickup=true·별도 확인 이력·원장 알림을 남겨요.
원장 경고는 같은 요청·인계자 이름·관계마다 한 번이에요. 정정 후 같은 인계자를 다시 확인해도 늘지 않아요.
투약 세 칸 medication_name·medication_dose·medication_time 누락은 missing_fields로 표시해요.
교직원은 상세 care.version 또는 목록 version을 confirm·complete에 반드시 보내요.
보호자 새 글마다 version을 올리고 received로 돌려 confirmed_at을 지워요. 옛 판은 CARD_VERSION_CONFLICT예요.
확인 당시 인계자로 완료를 기록하므로 확인 뒤 비활성·연결 해제도 complete는 가능해요.
귀가 알림은 근무 밖·주말과 실패 재시도에도 즉시예요. 목록 sort는 다른 목록과 같아요.
알림장 medication·pickup 줄에 읽기 전용 request_status가 붙고 원문·AI 원본은 그대로예요.
필드·권한·오류·이름만 있는 옛 시드의 처리는 T13 3.27을 따라요.

## [제안] v0.7 피드·앨범

반·원 칸의 글·앨범·사진 파일·아이별 공개 범위(API 38~49)는 mock·DB가 같은 계약을 써요.
본문·사진 생성은 multipart예요. files 순서와 맞춘 child_ids JSON 배열 문자열을 같이 보내요.
반 칸은 그 반 보호자만, 원 칸은 같은 기관 구성원 모두 읽고 써요. 파일도 같은 권한을 매번 검사해요.
가상 단색 PNG 5장과 글 4개를 같은 UUID로 시드해요. 공개 범위는 family·class·org 예시가 있어요.
MEDIA_DIR/mock에 파일을 두고 초기화 때 그 폴더만 비워요. 공개 정적 주소는 없어요. 삭제를 저장한 뒤 사진 파일도 지워요.
칸 권한을 몸통보다 먼저 검사해요. 전체 업로드 51MiB 초과는 413, 파일 10개·일반 필드 2개 초과는 422예요.
T50이 붙기 전에는 올린 사람이 아이를 직접 표시해요. 자세한 입력·오류·응답은 T13 3.29를 봐요.

## [제안][선택] v0.8 화상상담

FEATURE_VIDEO_CONSULT는 기본 false이며 room·signal handshake는 공통 404예요.
true면 예약 담임·신청 보호자만 GET /consultations/{booking_id}/room으로 60초 ticket을 받아요.
signal_path + ?ticket=… WebSocket은 접속 때 권한·시간을 다시 검사해요. ticket은 한 번만 쓰므로 재접속 때 새로 받아요.
켠 상태의 거부는 accept 뒤 1008 access_denied, 꺼짐은 handshake 404예요. 접속 로그의 ticket 값은 가려요.
메시지 처리 전 마지막 검사에서 10초가 지났으면 계정·토큰 판·예약·참여자·시간을 다시 보고 실패한 연결만 닫아요.
조용한 연결도 closes_at에 권한·시간을 다시 확인해요. 지연 신고로 연장됐으면 새 마감까지 기다리고, 끝났으면 1008 room_closed로 닫아요. 서버가 닫으면 화면은 RTCPeerConnection을 닫아요.
방별 잠금 밖에서 보내고 기록해요. 보내기가 2초를 넘으면 수신자를 방에서 빼고 peer_left를 보낸 뒤 수신 작업을 취소해요. 막힌 닫기 프레임은 기다리지 않아요.
{type: offer|answer|ice|bye, data}만 상대에게 전달하고, 입퇴장은 peer_joined·peer_left예요.
64KiB·초당 20개 제한, 역할별 재접속은 이전 연결을 닫아요. 신호·영상·음성은 저장하지 않아요.
방은 현재 API 프로세스 하나의 메모리예요. VIDEO_ICE_SERVERS의 TURN 설정은 그대로 전달해요.
플래그를 켜면 데모 기관에 확정 예약이 없을 때 가상 예약 …0901(teacher01·parent01)을 더해요.
확정된 데모 예약 …0901은 시드할 때마다 지금 입장할 수 있게 옮겨요(신규 예약도 같은 범위).
시작은 지금-5분과 KST 당일 00:00 중 늦은 값을 5분 단위로 내려요. 끝은 시작+30분과 당일 23:59 중 이른 값이에요.
늦은 밤에도 시간 때문에 생략하지 않아요. 시드는 예상 종료(expected_end_at)를 NULL로 두고, 취소·완료한 데모 예약은 보존해요.
mock·DB 시드는 now를 받으며 생략할 때만 실제 시각을 읽어요. 시험은 고정 시각을 넘겨요.
담임·상담실 겹침이면 경고 후 건너뛰고 다른 예약은 보존해요. ICE 설정 오류는 기능이 꺼졌으면 경고 후 기본 STUN을 써요.
상세 권한·오류·시간 경계는 T13 3.30과 OpenAPI를 봐요. 실제 사람 음성·사진은 쓰지 않아요.


[제안][선택] v0.8 가상 음성 분석(API 51~53)은 FEATURE_VOICE_ANALYSIS 기본 false예요.
켜면 예약 담임만 synthetic=true·파일 한 개로 접수하고 담임·원장이 결과를 읽어요.
기본 대역은 가상 녹취·3줄 이하 요약을 돌려줘요. OpenAI는 CONSULT_VOICE_ANALYZER=openai로 고를 때만 써요.
두 모드 모두 queued→running→succeeded/failed이며 원본은 끝나면 지워요. 실제 녹음은 쓰지 않아요.
접수는 confirmed·done만 가능하고 cancelled는 409예요. 기존 결과 조회는 예약 상태와 상관없어요.
mock은 RUN_IN과 상관없이 같은 프로세스에서 실행해요. api 모드는 시작할 때 미완료 queued·running을 실패 처리하고 파일을 지워요.
5분 점검은 DB worker 모드에서만 돌아요. 300초 넘은 queued·running은 재전달 없이 failed로 끝내고 파일을 지워요.
정리는 기능 플래그가 꺼져도 해요. WAV는 실제 data로 길이를 제한하고 잘못된 헤더·음성 외 브랜드·DocType·ID3는 422예요.
ID3 태그(선택 footer 포함) 바로 다음에 MPEG 프레임 동기가 있어야 해요. 녹취·요약 글의 NUL은 지워요. 가상 음성 도구는 저장소 안 출력을 거절해요.
설정·파일 제한·권한·응답 칸은 T13 3.30을 봐 주세요. 화면은 후속이에요.


## [제안][선택] v0.9 동네 피드·성장 영상

이번에는 동네 피드 API 54~56만 더해요. FEATURE_NEIGHBORHOOD_FEED 기본 false이며 꺼지면 공통 404예요.
동네 칸에 쓰는 행위 = 본인이 공개를 켠 것이에요. 같은 region 보호자만 읽고 쓰며 NULL·빈 문자열·공백류(탭·줄바꿈 포함)뿐인 region은 동네 없음(403)이에요.
같은 기관 교직원은 403과 이력을 남기고 다른 기관 교직원은 같은 동네여도 글·파일이 404예요.
동네 칸은 교직원이 보지도 숨기지도 않아요. 신고·관리 기능은 범위 밖이며 작성자 지우기만 가능해요.
작성자 표시는 기관 이름+보호자, 사용자 UUID는 null이에요. 자기 아이만 표시하고 사진은 현재 공개 범위를 검사해요.
가상 자료만 쓰고, 켠 상태 시드에 parent-n01(같은 동네)·parent-x01(다른 동네)을 더해요. 비밀번호는 demo1234예요.
기존 글 상세·지우기·사진 파일 API를 함께 써요. 반·원 칸 숨기기는 그대로예요. 자세한 칸·권한·사진 규칙은 T13 3.31을 봐 주세요.
반·원 경로는 기존 응답 모델을 유지하고 동네는 별도 모델, 공유 상세만 두 모양 중 하나예요.
플래그 꺼짐에서 photo_scope=neighborhood 변경은 아이 조회·권한 검사 전에 누구든 기록 없이 422 VALIDATION_FAILED(field=photo_scope)예요.
성장 영상은 다음 절을 봐요. 화면은 후속이에요.


## [제안][선택] 성장 영상(T60, v0.9)

FEATURE_GROWTH_VIDEO=true로 켜요. 기본 false일 때 네 경로는 공통 404예요.
POST /children/{child_id}/growth-videos에 `{photo_limit: 12}`를 보내면 202·queued 상태 객체를 받아요(3~20, 기본 12).
같은 경로 GET의 items에서 상태를 확인하고 성공한 file_url로 MP4를 받아요. DELETE /growth-videos/{id}는 204예요. 경로 앞에는 /api/v1을 붙여요.
현재 아이 보호자만 쓰며, 먼저 queued 행으로 자리를 잡아요. 요청은 보이는 사진·파일 존재·머리 픽셀 40MP 이하만 검사하고 후보가 3장 미만이면 행을 없애고 422예요. 디코딩은 작업에서만 하며, 깨진 사진을 뺀 뒤 3장 미만이면 failed와 failure_reason=not_enough_photos예요(“영상을 만들 수 있는 사진이 3장 이상 필요해요.”). 사진을 지우거나 공개 범위를 좁혀 볼 수 없게 되면 기존 영상 파일도 404예요.
가상 사진만 사용하고 H.264·720×720·장당 2초(최대 60초)로 만들어요. imageio-ffmpeg 휠의 실행 파일을 로컬에서 쓰며 실행 제한은 120초예요.
파일은 private, no-store·nosniff이며 단일 Range 요청은 206이에요. 단위 대소문자는 무시하고, 못 읽는 값·여러 구간은 200 전체로 답해요. 시작이 크기 이상이면 416과 Content-Range: bytes */크기를 줘요. 삭제는 커밋 뒤 파일 정리예요.
RUN_IN=api와 mock은 스레드 1개짜리 전용 실행기를 쓰고, db·worker는 media 큐와 media-worker(--concurrency=1)를 써요. worker의 5분 점검은 queued 30분·running 360초 초과를 failed로 끝내요. api는 시작할 때 남은 작업을 정리하며 재실행하지 않아요.
0016·DDL v0.22을 적용해요. 자세한 응답 칸은 T13 3.32·OpenAPI에 있어요.

성장 영상은 아이마다 진행 중 1개·성공 영상 보관 5개까지이며 초과는 409예요. POST 본문은 생략할 수 있어요. 내부 사진 검사는 permission_denied를 남기지 않아요.
사진마다 머리에서 크기·움직임을 검사해 40MP 초과·움직이는 그림을 빼요. 한 장 디코드·축소는 10초 제한이고 깨진 사진도 건너뛰어요. 유효한 사진 3장이 필요해요. 720×720 검은 배경에 투명을 합성하고 최소 변 길이는 2px이에요. 임시 PNG는 성공·실패 모두 지워요. 최종 입력은 장당 1/2fps·2초예요. 작업에서 다음 후보를 더 살펴 photo_limit까지 채우고 성공할 때 실제 사용 사진·개수를 저장해요.
imageio-ffmpeg 번들 ffmpeg는 GPLv3 정적 빌드(이미지 +80MB)라 이미지를 밖에 배포하면 고지가 필요해요.

실패 행은 보관 5개에 세지 않아요. 전처리 디코더에도 -max_pixels 40000000을 적용해요. 임시 그림은 MEDIA_DIR/tmp/growth-frames-*이며 성공·실패에 지우고 점검·api 시작 때 1시간 지난 폴더를 정리해요. setpriv가 있으면 부모 종료 시 ffmpeg도 종료하고, 없으면 직접 실행하며 시간 제한은 같아요.
