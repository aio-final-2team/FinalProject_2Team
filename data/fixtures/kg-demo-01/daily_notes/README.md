# 알림장 AI 초안용 가상 데이터 (별빛반 1주)

※ 유치온 개발·평가용 가상 자료입니다. 실제 기관·인물·아동 정보가 아닙니다.

11/20 팀 결정 ① "메모에 없는 말은 쓰지 않는 알림장 AI"를 시연하려고 만든 입력 데이터입니다. 성주님이 정리한 "11/27까지 더할 것 3번 데이터"(명단 18명, 아이별 메모, 함정)에 해당합니다.

| 파일 | 내용 | 양 |
| --- | --- | --- |
| `roster_c4.json` | 만 4세 별빛반(`C4`) 가상 아이 명단. 담임 `T-DEMO-01` | 18명 (`C4-01`~`C4-18`) + 시드 시험용 2명(`seed_children`: 하늘 `…0501`·노을 `…0503`) = **시연 20명**(FB-018-4) |
| `class_days.json` | 반 공통 입력 `activities`·`supplies`와 근거 문서 | 5일 (2026-11-16~20) |
| `child_memos.json` | 아이별 선생님 메모 `{note_date, child_key, memo, trap_case}` | 100개 = 18명×5일 90개(빈 메모 12, 함정 20) + 시드 2명×5일 10개(빈 메모 1, 함정 아님) |
| `guardian_requests.json` | 보호자 요청 `{request_key, note_date, created_at, child_key, type, body, expect, trap}`. 메모와 같은 날·같은 아이에 붙어 있어 함께 평가해요 | 20개 (투약 5·귀가 7·문의 8, 함정 12개) |

## 고른 이유

- **날짜 11/16~20**: 식단표 `MN-2026-W47`(같은 주)와 오전 간식표 `MN-2026-11-SNACK`이 있어 '식사' 줄을 실제 문서에서 가져올 수 있어요. 학부모 상담 주간(`SC-2026-11`)이기도 해요.
- **준비물**: 11/18~20에 김장 체험(`NT-2026-30`, 만 4·5세반) 준비물을 적어 문서 근거(`source.type = document`)를 보여 줘요.
- **메모 말투**: 선생님이 바쁠 때 쓰는 짧은 키워드형("점심 반 남김. 낮잠 잘 잠")으로 썼어요. AI가 이 짧은 말을 문장으로 풀되, 없는 사실은 더하지 않는지를 봐요.
- **이어지는 메모**: 아라(`C4-08`)는 11/17 미열 → 11/18 결석 → 11/19 열 없음, 별하(`C4-06`)는 11/16 무릎 긁힘 → 11/17 상처 확인처럼 날짜를 넘어 이어져요.
- **비슷한 이름**: 지아(`C4-12`)·지안(`C4-13`)은 일부러 비슷하게 지었어요. 이름을 헷갈리는지 봐요(평가 ND-09·ND-10).

## API·DB와 연결 (API 설계 v0.4, 태웅님 `taewoong-next` 기준)

| 이 데이터 | API·DB | 상태 |
| --- | --- | --- |
| `class_days[].activities`·`supplies` | API 22 요청 본문 · `daily_note_inputs.activities`·`supplies` | 지금 있음 |
| `child_memos[]` (하루치) | API 22 `child_memos[] {child_id, memo}` · `daily_note_inputs.child_memos` jsonb | API 설계 v0.4. **빈 메모(`""`)는 보내지 않아요**(memo 1~500자) |
| `roster_c4.children[]` | `children` 표 시드 · API 30 반 아이 목록 | `child_id` = `…54NN` (`C4-NN`과 번호 같음). 별빛반은 이 18명 + 시험용 하늘·노을 = 20명 |
| `meal_source`·`snack_source` | `content.items[key=meal].source = {type: document, …}` | 검색으로 찾음. 여기 값은 평가 정답 확인용 |

- 반·담임은 모의 API 시드(PR #256)에 맞췄어요: `T-DEMO-01`(계약표 부록의 '우리 반 담임', 30문항의 담임)이 담임인 **만 4세 별빛반**이에요. 그래서 팀원 문서를 고치지 않아도 돼요.
- 이 폴더는 `documents` 적재(T20) 대상이 아니에요. 검색에 넣지 않아요.

## 평가

함정 메모 20개의 정답·채점 기준은 [`data/evaluation/daily_note/`](../../../evaluation/daily_note/README.md)에 있어요. `child_memos.json`의 `trap_case`가 평가 문항 ID예요.
