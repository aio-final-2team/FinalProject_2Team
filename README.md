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
- 제출 산출물의 원본과 제출본(DOCX·PDF·링크)은 `Docs/StepN/`에 함께 둡니다.
- 시연 데이터는 가상 자료만 사용합니다. 실제 비밀값과 Android 서명 키는 커밋하지 않습니다.

각 폴더의 `README.md`에 해당 위치의 책임과 WBS 연결을 적었습니다. 현재 애플리케이션은 초기 골격이며, 기능은 WBS 순서에 따라 구현합니다.
