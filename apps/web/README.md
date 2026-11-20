# apps/web

유치온 웹 앱입니다. 웹 URL이 먼저 나가는 결과물이고, 같은 코드를 Capacitor로 감싸 안드로이드 앱을 만듭니다.

## 실행

```bash
cd apps/web
npm ci
npm run dev        # http://localhost:5173
npm run build      # 타입 검사 + 빌드
```

시연 계정 버튼(학부모·선생님·원장)으로 들어갑니다. 서버(T13)가 붙기 전에는 MSW 가짜 API가 응답하고, 새로고침하면 가짜 데이터가 처음 상태로 돌아갑니다.

## 환경 변수 (`.env.example`)

| 변수 | 뜻 |
| --- | --- |
| `VITE_API_BASE_URL` | 백엔드 주소. 비우면 같은 주소의 `/api` |
| `VITE_USE_MOCK` | `false`면 MSW를 끄고 실제 서버를 부른다 |
| `VITE_DEMO_ACCOUNTS` | `false`면 로그인 화면의 시연 계정 버튼을 숨긴다 |

## 기술

React 19 · TypeScript · Vite 6 · React Router 7 · TanStack Query 5 · Tailwind 4 · Motion 12 · MSW 2 · Pretendard. 버전은 모두 고정했고 `package-lock.json`으로 설치합니다(`npm ci`).

## 폴더

| 폴더 | 내용 |
| --- | --- |
| `src/styles` | 디자인 토큰(`tokens.css`)과 모션. 색은 브랜드 색만, 화면 코드는 토큰 클래스(`bg-card`, `text-ink2` …)만 쓴다 |
| `src/domain` | T04 상태·필터·위험 등급 상수와 카드 타입. 상태 표시 이름은 여기서만 정한다 |
| `src/api` | API 호출과 TanStack Query 훅. 행동은 모두 `Idempotency-Key`를 붙인다 (AC-05) |
| `src/mocks` | MSW 가짜 API와 하늘반 예시 데이터. 필드 이름은 T10 계약 뒤에 맞춘다 |
| `src/components` | 공통 부품: Button, Pill·TypeTag, Sheet, Toast, StateView, Icon, Buddy·SymbolMark |
| `src/layouts` | 교사·원장(1024px 이상 왼쪽 메뉴) · 학부모(모바일 웹, PC에서는 가운데 480px) 틀 |
| `src/features` | 화면. 지금은 로그인, 교사·원장 받은함 + 카드 상세 |

화면 설계와 결정 근거: `Docs/Step2/유치온_T12_화면지도.md`, `Docs/Step2/유치온_T04_흐름권한명세.md`

## 배포

`Dockerfile`이 `npm ci`로 빌드하고 nginx로 띄웁니다. `nginx.conf`는 `/teacher/inbox` 같은 주소를 새로고침해도 화면이 나오도록 `index.html`로 넘깁니다.
