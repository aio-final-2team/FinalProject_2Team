# 실패 요청의 trace 찾는 법

1. **오류 응답부터 확인** — 응답 JSON에서 `error.trace_id`를 복사합니다. 공통 오류 응답은 `error` 객체에 `trace_id`를 넣습니다([apps/api/app/core/errors.py:55](../../apps/api/app/core/errors.py#L55)). 요청 추적 미들웨어는 요청 `X-Request-ID`를 그대로 쓰거나 UUID를 만들고, 처리 뒤 응답 헤더 `X-Request-ID`에도 같은 값을 씁니다([request_id.py:20](../../apps/api/app/core/request_id.py#L20), [request_id.py:29](../../apps/api/app/core/request_id.py#L29)). CORS도 이 응답 헤더를 노출합니다([main.py:57](../../apps/api/app/main.py#L57)). 오류가 아니어도 헤더에서 trace를 얻을 수 있습니다.

2. **events에서 trace로 이력 검색** — `events` 테이블에 별도 `trace_id` 컬럼은 없습니다. 각 기능의 INSERT가 `detail` JSONB 안에 `trace_id`를 씁니다. 예: 요청 이력 INSERT([requests/events.py:13](../../apps/api/app/modules/requests/events.py#L13)), 자료 문의 기록([documents/staff_ask.py:34](../../apps/api/app/modules/documents/staff_ask.py#L34)).

```sql
SELECT id, created_at, request_id, card_id, actor_type, agent_name, action, detail
FROM events
WHERE org_id = :org_id
  AND detail->>'trace_id' = :trace_id
ORDER BY id;
```

3. **요청 ID 또는 카드 ID로 전체 이력** — 오류 응답이나 화면에서 요청/카드 ID를 확보했다면 다음처럼 조회합니다. `events`는 request_id와 card_id에 각각 인덱스가 있습니다([0001_initial.sql:327](../../apps/api/migrations/sql/0001_initial.sql#L327), [0001_initial.sql:352](../../apps/api/migrations/sql/0001_initial.sql#L352)).

```sql
SELECT id, created_at, request_id, card_id, actor_type, agent_name, action, detail
FROM events
WHERE org_id = :org_id AND request_id = :request_id
ORDER BY id;

SELECT id, created_at, request_id, card_id, actor_type, agent_name, action, detail
FROM events
WHERE org_id = :org_id AND card_id = :card_id
ORDER BY id;
```

4. **LangSmith에서 그래프 실행 확인** — 서버 설정에서 `LANGSMITH_API_KEY`와 `LANGSMITH_TRACING=true`가 모두 설정된 경우 기록됩니다. `infra/DEPLOY.md`는 기능 묶음 이름을 `요청 처리`, `알림장 초안`, `문의 답변 초안`, 모델 호출 이름을 `역할:모델`(예: `SUPERVISOR:gpt-6-luna`)로 안내합니다([DEPLOY.md:98](../../infra/DEPLOY.md#L98), [DEPLOY.md:239](../../infra/DEPLOY.md#L239)). 묶음 이름과 역할/모델 이름으로 범위를 좁히고, 실행 시각과 입력의 요청·카드 ID를 대조합니다. **팀 서버에서 LangSmith가 실제 켜져 있는지는 태웅님 확인 필요**입니다.

## 코드 근거

- 오류 본문과 헤더가 같은 trace: `apps/api/app/core/request_id.py:20-30`, `apps/api/app/core/errors.py:51-63`.
- 이벤트 trace는 `events.detail` JSONB에 저장: `apps/api/app/modules/requests/events.py:11-22`, `apps/api/app/modules/documents/staff_ask.py:34-42`.
- LangSmith 설정/이름: `infra/DEPLOY.md:98,239`, `agents/llm.py:44-65`.
