# 요청 그래프 평가 문항

`request_cases.json`은 가상 원 자료(`data/fixtures/kg-demo-01`)의 제목과 본문에서 만든 20문항입니다. 문의 12개, 민원 일반 6개, 긴급·판단 필요 2개입니다. 위험 등급 정답은 넣지 않았습니다. 검색 기준일은 2026-12-02, 대상 반은 C4입니다.

`PYTHONPATH=apps/api:. python tools/eval_request.py`로 가짜 모델을 써서 옛·새 그래프의 분기, 카드 종류, 근거 문서, 근거 없음 처리를 비교합니다. 민원 일반은 옛 경로가 모의 초안을 쓰므로 근거 차이가 예상됩니다. `--real`은 실제 모델을 부르므로 별도 허가 없이는 실행하지 않습니다.

`--record`를 붙이면 `DATABASE_URL`의 기존 `eval_runs`에 실행마다 한 줄을 저장합니다(`suite=service`, 요청 20문항의 통과 수/전체). 옵션이 없으면 DB에 접속하지 않고 기존 출력·`--out` JSON·종료값을 유지합니다. 기록할 때는 시작 시각, 요청 모델(`fake` 또는 `LLM_MODEL_DOCUMENT` → `LLM_MODEL_DEFAULT` → 기본 모델), `--out` 경로도 남깁니다. `note` JSON에는 도구 이름과 검사 모델(`fake` 또는 `LLM_MODEL_CHECKER` → 기본 모델 설정)이 들어갑니다. 응답 모델 ID는 실행기가 수집하지 않아 `returned_model`은 NULL이며, 채점 실패는 실행 오류가 아니므로 `errors=0`입니다. 기록 실패는 오류로 종료하고, 이미 쓴 결과 파일은 유지합니다.
