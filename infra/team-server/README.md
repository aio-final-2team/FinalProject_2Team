# 첫 배포 준비

`compose.server.yaml`은 루트 Compose에 겹쳐 쓰는 서버 설정이에요.
실제 배포 담당자가 접속한 서버에서만 `deploy.sh`를 실행해요.
서버 생성·접속·앞단 변경은 스크립트에 없어요.

```sh
cp infra/team-server/.env.server.example infra/team-server/.env.server
# 실제 비밀번호·JWT 키·외부 API 주소·CORS를 환경 파일에 넣어요.
infra/team-server/deploy.sh
tools/smoke.sh "$API_BASE_URL"
```

환경 파일은 Git에서 제외돼요. 예시 JWT 키는 DB 기동 검사를 통과하지 못해요.
현재 브랜치에 upstream을 먼저 지정해요. 배포는 변경이 없는 작업 폴더에서
`git pull --ff-only` 후 Compose 기동을 요청해요. API는 하나만 실행해요.
DB 모드는 기존 엔트리포인트가 마이그레이션 → 데모 시드 → API 순서로 시작해요.

API·웹은 기본 loopback 포트 18000·15173만 써요. `SERVER_API_PORT`·
`SERVER_WEB_PORT`로 기존 서비스와 겹치지 않게 바꿔요. DB는 호스트 포트를 열지 않아요.
기존 80/443 앞단이 `/health`·`/api/v1/...`는 API로, 화면 요청은 웹으로 보내도록
배포 담당자가 연결해요. API 경로를 지우거나 접두사를 덧붙이지 않아요.
앞단이 다른 컨테이너에 있으면 그 컨테이너의 localhost와 호스트 loopback은 달라요.
그때의 연결 방식은 실제 앞단 구성을 확인한 뒤 정해요.

Compose 2.24.4 이상이 필요해요. 포트 목록을 `!override`·`!reset`으로
바꿔서 로컬 포트가 함께 열리지 않게 해요.
자세한 배포·확인·백업 절차는 [DEPLOY.md](../DEPLOY.md)를 봐요.
