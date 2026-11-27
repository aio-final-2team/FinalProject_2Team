# 사람별 QA 원으로 시험해요

> **이 PR이 develop에 머지되고 팀 서버에 자동 배포된 다음부터 쓸 수 있어요.** 배포됐는지는 #일반의 `[자동 배포]` 알림이나 [QA 도구 화면](https://3-34-13-40.sslip.io/api/v1/qa/console) 위쪽의 서버 판으로 확인해요.

사람마다 자기 가상 원이 하나씩 있어서, 다른 사람의 시험 데이터를 건드리지 않고 문의·알림장·상담·소식 기능을 처음부터 몇 번이든 다시 시험할 수 있어요. 데모 원(`teacher01` 등)은 시연용이라 시험에 쓰지 않아요.

**뭐부터 하나요**
1. 아래 2장에서 내 이름표 계정을 고르고, 비밀번호는 디스코드 공지에서 확인해요.
2. 웹 화면 `https://3-34-13-40.sslip.io`에 그 계정으로 로그인해서 평소처럼 화면을 눌러 보며 QA해요.
3. 처음 상태로 되돌리거나 오류를 찾을 땐 QA 도구 화면 `https://3-34-13-40.sslip.io/api/v1/qa/console`을 열어요.
4. AI에게 맡길 땐 이 문서와 `contracts/openapi.yaml`을 읽히고 7장 예시처럼 시켜요.

## 0. 화면으로 QA해요

- **화면 QA**: 웹 화면에서 내 QA 계정으로 로그인하면 돼요. 학부모 계정(`sj.parent01`)으로 문의·투약·귀가를 넣고, 담임 계정(`sj.teacher01`)으로 받은함·알림장을 확인하는 식이에요. 창 두 개(일반 창 + 시크릿 창)를 쓰면 두 역할을 같이 볼 수 있어요.
- **QA 도구 화면**(`/api/v1/qa/console`): 같은 계정으로 로그인하면 버튼으로 할 수 있어요.
  - 내 원 처음으로 되돌리기
  - 알림장만 다시 시험하기: 반·날짜를 골라 그날 알림장을 지워요.
  - 요청 ID로 오류 찾기: 개발자 도구 → 네트워크 → 응답 헤더 `X-Request-ID`를 붙여 넣어요.
  - 지금 서버 판 보기
- QA 도구 화면은 QA 서버에서만 열려요. 아래 3~6장은 같은 기능을 API로 직접 부르는 법이에요.

## 1. 내 가상 원은 이렇게 동작해요

팀 QA 서버 주소는 `https://3-34-13-40.sslip.io`예요. 사람마다 반·아이·보호자·상담실·자료·기억·돌봄 메모·하루 중 기록·소식 사진·상담 예약·알림장용 요청이 있는 원을 하나씩 써요. 자기 원 밖의 아이·요청은 보이지 않아요. AI 호출 비용과 작업 대기열은 다 같이 써요.

QA 도구는 `QA_TOOLS=true` 또는 `1`인 서버에서만 열려요. 꺼져 있으면 로그인 여부와 관계없이 404 `NOT_FOUND`예요. 가상 원 시드와 원 전체 초기화는 DB 모드 전용이에요. mock 모드의 원 전체 초기화는 404이며, trace 조회와 배포 정보 조회는 사용할 수 있어요.

## 2. 내 계정을 골라요

| 이름표 | 사람 | 원 | 담임 로그인 예 |
| --- | --- | --- | --- |
| sj | 성주 | QA 성주 원 | sj.teacher01 |
| ym | 영민 | QA 영민 원 | ym.teacher01 |
| jh | 지혜 | QA 지혜 원 | jh.teacher01 |
| ih | 인혜 | QA 인혜 원 | ih.teacher01 |
| tw | 태웅 | QA 태웅 원 | tw.teacher01 |

이름표 뒤에 `teacher01`(별빛반 담임), `teacher02`(햇님반 담임), `teacher03`(보조 교사), `director01`(원장), `parent01`·`parent02`(보호자)를 붙여요. 추가 보호자 계정도 같은 이름표를 붙여요. **비밀번호는 디스코드 공지에서 확인해요.** 아래 예시에서는 자기 컴퓨터의 `QA_PASSWORD` 환경 변수에 안내받은 값을 넣어 사용해요. 값은 문서·GitHub에 적지 않아요. 서버에서 이 값이 비어 있으면 QA 원은 만들어지지 않아요.

## 3. 로그인해서 토큰을 받아요

```bash
BASE_URL=https://3-34-13-40.sslip.io
# QA_PASSWORD는 디스코드 공지의 값으로 자기 환경에 미리 설정해 주세요.
TOKEN=$(curl -fsS "$BASE_URL/api/v1/auth/login" \
  -H 'Content-Type: application/json' \
  --data "$(jq -nc --arg password "$QA_PASSWORD" \
    '{login_id:"sj.teacher01",password:$password}')" | jq -r .access_token)
curl -fsS "$BASE_URL/api/v1/me" -H "Authorization: Bearer $TOKEN"
```

응답의 `user.org_id`·`user.classroom_ids`·`children`에서 자기 원의 ID를 얻어요. 다른 원의 예시 UUID를 그대로 쓰면 404예요. 이후 로그인 필요한 요청에는 `Authorization: Bearer $TOKEN`을 붙여요. 토큰은 화면 캡처·공유 로그에 넣지 않아요.

## 4. 시험 전에 배포 판을 확인해요

```bash
curl -fsS "$BASE_URL/api/v1/qa/info"
```

로그인 없이 `commit`·`deployed_at`·`migration`·`data_backend`와 writer·요청 에이전트·임베딩·모델 이름 설정을 확인해요. 배포 정보를 주지 않은 로컬 환경에서는 commit·deployed_at이 null이에요. mock의 migration도 null이에요. 키·비밀번호·DB 접속 주소는 응답에 없어요. 시험 보고에 commit을 붙이면 어느 판의 결과인지 알 수 있어요.

## 5. 다시 처음부터 시험해요

원 전체를 되돌리려면 아래 요청을 보내요. 자기 원의 어떤 역할로도 할 수 있어요.

```bash
curl -fsS -X POST "$BASE_URL/api/v1/qa/sandbox/reset" \
  -H "Authorization: Bearer $TOKEN"
```

본문은 없어요. 자기 원 전체의 시험 데이터를 지운 뒤 기준 시드를 다시 넣어요. 응답의 `org_name`·`deleted`(표별 삭제 수)·`seeded`(사용자·아이·문서 수)로 확인해요. 계정 ID와 기존 로그인 토큰은 유지돼요. 다른 QA 원과 데모 원에는 영향이 없어요. 사진·문서 파일은 디스크에 남겨요. 같은 원의 실행 중 작업이 있다면 먼저 끝낸 뒤 초기화해 주세요.

알림장만 다시 시험하려면 기존 도구를 써요. 자기 반 ID를 로그인 응답에서 얻고, 날짜는 시험할 날짜로 바꿔요.

```bash
curl -fsS -X POST "$BASE_URL/api/v1/qa/daily-notes/reset" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  --data "$(jq -nc --arg classroom "$CLASSROOM_ID" \
    '{classroom_id:$classroom,note_date:"2026-11-27"}')"
```

이 도구는 해당 반 담임·원장만 쓰며 그 반·날짜의 알림장 묶음을 지워요. 날짜를 생략하면 오늘(KST)이에요. 문의·기억 본문·하루 중 기록은 남아요.

## 6. 오류가 나면 요청 ID로 찾아요

응답 헤더 `X-Request-ID` 또는 오류 본문의 `error.trace_id`를 보관해요. 직접 `X-Request-ID`를 보내면 그 값으로 이어져요.

```bash
curl -fsS "$BASE_URL/api/v1/qa/traces/$TRACE_ID" \
  -H "Authorization: Bearer $TOKEN"
```

`events`에는 자기 원에서 같은 trace_id로 남은 이력이 시각순으로 나와요. `errors`에는 API가 처리하지 못한 500의 시각·메서드·경로·상태·예외 종류·파일:줄만 나와요. 예외 메시지와 입력 내용은 errors에 저장하지 않아요. errors는 API 프로세스 메모리의 최근 500건이라 배포·재기동 때 사라져요. 다른 원의 이력·오류는 보이지 않고, 찾지 못하면 두 배열 모두 비어요. worker에서 난 예외는 API의 errors 버퍼에 없으니 events와 처리 결과도 함께 확인해요.

500이 아닌 4xx는 `error.code`와 검증 상세로 원인을 확인해요. trace가 비어 있다고 성공한 요청이라는 뜻은 아니에요. 보고에는 commit·호출 메서드·경로·응답 상태·error.code·trace를 붙이되 비밀번호·토큰은 빼요.

## 7. AI에게 이렇게 시켜요

> 이 README와 contracts/openapi.yaml을 읽고, 환경 변수에 있는 QA 비밀번호로 sj.teacher01에 로그인해 주세요. 내 반 ID로 오늘 알림장 초안 만들기 → 확인·수정 → 발송까지 API로 실행하고, 실패하면 요청 ID와 /qa/traces 결과를 붙여 보고해 주세요. 시작할 때 /qa/info의 commit을 기록하고 비밀번호·토큰은 출력하지 마세요.

> 이 README와 contracts/openapi.yaml을 읽고 ym.parent01로 문의를 만든 뒤 ym.teacher01로 답변 초안을 확인해 주세요. 요청에 X-Request-ID를 붙이고, 다른 원의 아이·요청을 조회하면 404인지도 확인해 주세요. 시험 뒤 내 QA 원만 /qa/sandbox/reset으로 초기화하고 삭제·시드 개수를 보고해 주세요. 비밀번호는 환경에서 읽고 보고에는 토큰을 넣지 마세요.

## 8. 함께 쓸 때 주의해요

- develop에 머지될 때마다 자동 배포돼요. API가 잠깐 끊기거나 초안이 실패하면 배포 판을 확인하고 다시 시도해요.
- 머지하지 않은 PR의 코드는 서버에 없어요. 로컬 브랜치와 서버 commit을 구분해요.
- 실제 AI 호출 비용·작업 대기열은 다 같이 써요. 많은 초안을 한꺼번에 요청하지 않아요.
- 비밀번호·토큰·API 키를 GitHub 이슈·PR·커밋·공유 로그에 붙이지 않아요.
- 자기 이름표의 원에서만 시험해요. 데모 원은 시연용으로 남겨요.
