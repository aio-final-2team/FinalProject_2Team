# agents/graphs

STEP 3 단일 요청 처리 흐름과 STEP 4 협업 그래프를 둡니다.

## 알림장 초안 (`daily_note.py`)

- 입구 함수: `draft_daily_notes(payload, writer=None, checker=None)` — 입력·출력은 API 설계 문서 v0.4 3.19, 흐름은 `Docs/Step2/알림장_에이전트_흐름.md`
- 반 공통 줄(`day`·`supplies`·`meal`)은 코드가 만들고, 자료 AI는 아이 메모 줄·보호자 요청 줄만 써요. 다른 아이 이름·요청 누락은 코드가, 나머지는 검사 AI가 봐요
- 모델은 `agents/llm.py`의 `OpenAIModel`(`.env`의 `OPENAI_API_KEY`, `LLM_MODEL_DOCUMENT`·`LLM_MODEL_CHECKER`). `openai` 패키지가 필요해요
- 시험: `PYTHONPATH=apps/api:. pytest tests/unit/test_daily_note_graph.py` (가짜 모델)
- 함정 평가: `PYTHONPATH=apps/api:. python tools/eval_daily_note.py --model echo` (모델 없는 기준선) · `--model openai --out <파일>`
