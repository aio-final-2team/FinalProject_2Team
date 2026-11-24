# 유치온

유치원과 가정의 요청·상담·알림장을 한 흐름으로 연결하는 Android 앱과 업무 지원 에이전트 프로젝트입니다.

## 기술 구성

- 앱: React, Capacitor Android
- API: FastAPI, Pydantic
- 업무 흐름: LangGraph
- 웹 화면: React, Nginx
- 데이터: PostgreSQL, pgvector
- 도구 연결: MCP, 서비스 내 알림은 백엔드에서 직접 처리
- 개발·배포: Docker Compose, AWS EC2 우선

## 디렉터리 원칙

- `apps/`는 실행 애플리케이션, `agents/`는 에이전트 역할별 로직을 둡니다.
- API 이미지는 `apps/api`만이 아니라 레포 루트를 빌드 컨텍스트로 사용합니다.
- `contracts/openapi.yaml`을 화면·API 계약의 기준으로 삼고 `contracts/mock_api/`로 모의 API를 제공합니다.
- 단계별 기획서·WBS 원본과 제출 파일은 `Docs/StepN/`에 모읍니다. 별도 `deliverables/` 폴더는 사용하지 않습니다.
- 시연 데이터는 가상 자료만 사용합니다. 실제 비밀값과 Android 서명 키는 커밋하지 않습니다.

## 문서 위치

- `Docs/Step1/`: 최신 기획서(`기획서.docx`·`기획서.md`)와 WBS(`WBS.xlsx`·`WBS.md`). 11/16·11/17 날짜 판은 `Docs/Step1/이전판/`
- `Docs/Step1/assets/`: 기획서 Markdown에서 참조하는 이미지
- 각 `Docs/StepN/README.md`: 해당 단계의 문서 구성과 최신 기준 파일 안내

## 2차 검토 문서

2차 검토는 `develop` 브랜치의 아래 문서로 합니다. 링크는 develop의 최신 내용을 가리킵니다.

| 문서 | 위치 |
| --- | --- |
| 기획서 · WBS | [기획서](Docs/Step1/기획서.md) · [WBS](Docs/Step1/WBS.md) (Word·Excel 원본은 같은 폴더) |
| 숫자·출처 검증표 (T17) | [Docs/Step3/T17_숫자_출처_검증표.md](Docs/Step3/T17_숫자_출처_검증표.md) |
| API 설계 문서 (T13) · DB 스키마 설계서 (T09) | [API](Docs/Step2/API_설계_문서.md) · [DB](Docs/Step2/DB_스키마_설계서.md). 문서 머리에 1차 검토 뒤 보완 표가 있습니다 |
| 단일 에이전트 상태 전이 설계서 (T25) | [Docs/Step3/T25_단일에이전트_상태전이_설계서.md](Docs/Step3/T25_단일에이전트_상태전이_설계서.md) |

**시연 코드 기준 커밋**: develop `641591f`. 팀 서버에 지금 배포된 커밋입니다(11/24 밤 배포, 흐름 고치기 #338·가상 사진 #337·AI 보안 장치 #331·#333까지, DB 판 `0015`). 값은 이 줄에만 두고, API·DB 설계서 머리와 [Step1 README](Docs/Step1/README.md#2차-검토-링크와-시연-기준-커밋)는 이 줄을 가리킵니다. 팀 서버를 다시 배포하면 이 한 줄만 고칩니다.

각 코드 폴더의 `README.md`에는 해당 위치의 책임과 WBS 연결을 적었습니다. 현재 애플리케이션은 초기 골격이며, 기능은 WBS 순서에 따라 구현합니다.
