# agents/graphs

STEP 3 단일 요청 처리 흐름과 STEP 4 협업 그래프를 둡니다.

## 알림장 초안 (`daily_note.py`)

- 입구 함수: `draft_daily_notes(payload, writer=None, checker=None)` — 입력·출력은 API 설계 문서 v0.4 3.19, 흐름은 `Docs/Step2/알림장_에이전트_흐름.md`
- 반 공통 줄(`day`·`supplies`·`meal`)은 코드가 만들고, 자료 AI는 아이 메모 줄·보호자 요청 줄만 써요. 다른 아이 이름·요청 누락은 코드가, 나머지는 검사 AI가 봐요
- 모델은 `agents/llm.py`의 `OpenAIModel`(`.env`의 `OPENAI_API_KEY`, `LLM_MODEL_DOCUMENT`·`LLM_MODEL_CHECKER`). `openai` 패키지가 필요해요
- 시험: `PYTHONPATH=apps/api:. pytest tests/unit/test_daily_note_graph.py` (가짜 모델)
- 함정 평가: `PYTHONPATH=apps/api:. python tools/eval_daily_note.py --model echo` (모델 없는 기준선) · `--model openai --out <파일>`

## 요청 협업 뼈대 (`request_collaboration.py`)

- `REQUEST_AGENT=app.modules.requests.graph_agent:run_request`와 `REQUEST_COLLAB_GRAPH=1`을 함께 설정하면 새 그래프를 고릅니다. 기본은 기존 요청 그래프입니다.
- 감독이 요청 유형을 나누고, 문의·민원은 `Send`로 자료 검색과 기억 읽기를 동시에 시작합니다. 합친 뒤 자료 쓰기와 검사를 거쳐, 검사 실패는 최대 두 번 자료로 돌려보냅니다. 카드 뒤에는 기존 `interrupt`로 사람 결정을 기다립니다.
- 카드 저장은 기존 함수를 쓰고, 문의의 검색·기억 읽기·쓰기·검사는 새 노드에서 실행합니다. 초안·근거·기억은 현재 체크포인트 State에도 남으므로 운영 전 저장 범위 검토가 필요합니다.

2단계에서는 문의의 자료 검색·기억 읽기·자료 쓰기·검사를 실제 함수에 연결했습니다. 새 그래프가 만든 답을 카드 저장에 넘겨 같은 모델을 두 번 부르지 않습니다. 검색·기억·검사 실패는 빈 초안 카드로 넘깁니다. 민원 일반·상담의 기존 카드 처리는 유지합니다.
