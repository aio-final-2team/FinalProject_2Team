# apps/web

유치온 웹 앱입니다. 웹 URL이 먼저 나가는 결과물이고, 같은 코드를 Capacitor로 감싸 안드로이드 앱을 만듭니다.

## 실행

```bash
cd apps/web
npm ci
npm run dev        # http://localhost:5173
npm run build      # 타입 검사 + 빌드
```

시연 계정 버튼(학부모·선생님·원장)으로 들어갑니다. 화면은 늘 실제 API(`/api/v1`)를 부르고, 어느 백엔드가 답할지는 아래에서 고릅니다.

## 진짜 응답 보면서 개발하기

개발 서버는 `/api/v1` 요청을 `API_PROXY_TARGET`으로 넘깁니다(`vite.config.ts`). `.env.example`을 `.env.local`로 복사해서 고르면 됩니다.

| 이렇게 하면 | 받는 응답 |
| --- | --- |
| `API_PROXY_TARGET=https://3-34-13-40.sslip.io` | **팀 서버.** DB·워커·AI(알림장·문의 답변·감독·요청 그래프)·임베딩·법령·날씨가 다 켜진 develop 코드예요. 키나 도커 없이 `npm run dev`만 하면 돼요 |
| 비워 둠(기본) | 로컬 FastAPI `http://127.0.0.1:8000`. 저장소 기본값은 모의 모드(`DATA_BACKEND=mock`)·대역 AI라서 응답이 가짜예요 |

- 팀 서버를 쓸 땐 `VITE_API_BASE_URL`은 비워 두세요. 값이 있으면 브라우저가 그 주소를 직접 불러서 프록시를 안 타요.
- 팀 서버 자료는 팀이 같이 써요. 시험으로 넣는 글은 앞에 `[TEST]`를 붙여 주세요.
- 팀 서버는 develop에 머지된 백엔드만 돌아요. 아직 PR에 있는 서버 변경은 머지·배포 뒤에 보여요.
- 로컬 백엔드도 진짜로 돌리려면 레포 루트 `.env`에서 `DATA_BACKEND=db`·`RUN_IN=worker`·`DAILY_NOTE_WRITER=graph`·`ANSWER_WRITER=graph`·`REQUEST_AGENT=app.modules.requests.graph_agent:run_request`·`LLM_MODEL_SUPERVISOR=gpt-6-luna`·`OPENAI_API_KEY`를 채우고 `docker compose --profile worker up --build`로 띄워요(켜는 값 설명은 `infra/DEPLOY.md` 5-5절).

## 환경 변수 (`.env.example`)

| 변수 | 뜻 |
| --- | --- |
| `VITE_API_BASE_URL` | 화면이 부르는 백엔드 주소. 비우면 같은 주소의 `/api/v1` |
| `VITE_DEMO_ACCOUNTS` | `false`면 로그인 화면의 시연 계정 버튼을 숨긴다 |
| `API_PROXY_TARGET` | 개발 서버가 `/api/v1`을 넘길 곳. 비우면 로컬 FastAPI. 화면 번들에는 안 들어간다 |

## 기술

React 19 · TypeScript · Vite 6 · React Router 7 · TanStack Query 5 · Tailwind 4 · Motion 12 · Pretendard. 버전은 모두 고정했고 `package-lock.json`으로 설치합니다(`npm ci`).

## 폴더

| 폴더 | 내용 |
| --- | --- |
| `src/styles` | 디자인 토큰(`tokens.css`)과 모션. 색은 브랜드 색만, 화면 코드는 토큰 클래스(`bg-card`, `text-ink2` …)만 쓴다 |
| `src/domain` | T04 상태·필터·위험 등급 상수와 카드 타입. 상태 표시 이름은 여기서만 정한다 |
| `src/api` | API 호출과 TanStack Query 훅. 행동은 모두 `Idempotency-Key`를 붙인다 (AC-05) |
| `src/components` | 공통 부품: Button, Pill·TypeTag, Sheet, Toast, StateView, Icon, Buddy·SymbolMark |
| `src/layouts` | 교사·원장(1024px 이상 왼쪽 메뉴) · 학부모(모바일 웹, PC에서는 가운데 480px) 틀 |
| `src/features` | 화면. 지금은 로그인, 교사·원장 받은함 + 카드 상세 |

화면 설계와 결정 근거: `Docs/Step2/유치온_T12_화면지도.md`, `Docs/Step2/유치온_T04_흐름권한명세.md`

## 배포

`Dockerfile`이 `npm ci`로 빌드하고 nginx로 띄웁니다. `nginx.conf`는 `/teacher/inbox` 같은 주소를 새로고침해도 화면이 나오도록 `index.html`로 넘깁니다.
