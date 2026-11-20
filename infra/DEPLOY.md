# 유치온 배포 가이드

> 상태: **초안** (2026-11-17) · `TODO`는 확정되면 채웁니다.
> 이 문서는 T30(첫 배포), T63(최종 배포 URL), T66(배포 아키텍처 설계도)의 기준 문서입니다.

## 0. 결정 사항

| 날짜 | 결정 | 영향 |
|---|---|---|
| 2026-11-17 | 첫 배포부터 **AWS EC2**로 진행 (강사님 팀 VM 사용 안 함) | WBS T30·T73 일정 조정 필요, `infra/team-server/` 정리 대상 |
| 2026-11-17 | 모바일은 **Android APK + iOS TestFlight** | iOS 작업 WBS 추가 필요, Mac·Apple Developer 계정 필요 |

## 1. 전체 구성

```
[브라우저] ──https──┐
                    ├─▶ [EC2 (ap-northeast-2)]
[폰 앱 APK/IPA] ────┘      ├─ web        React + nginx      (컨테이너 :80)
                           ├─ api        FastAPI            (컨테이너 :8000)
                           └─ db         PostgreSQL+pgvector (컨테이너 :5432, 외부 비공개)
```

- 서버에서는 루트의 `compose.yaml`로 `web`, `api`, `db` 세 서비스를 띄웁니다. 원장 현황은 같은 React 앱의 역할별 화면에서 제공합니다.
- 폰 앱은 `apps/web` 코드를 Capacitor로 포장한 것이며 **compose로 배포하지 않습니다** (8장).
- 외부 연동: OpenAI, LangSmith, (예정) AWS Rekognition

| 항목 | 값 |
|---|---|
| 리전 | ap-northeast-2 (서울) |
| EC2 사양 | `TODO` (예: t3.medium — 메모리 측정 후 확정) |
| 도메인 | `TODO` |
| 운영 브랜치 | `TODO` (main 예상) |
| 배포 담당 / AWS 계정 관리자 | `TODO` |

## 2. 환경

| 환경 | 위치 | 주소 | 용도 |
|---|---|---|---|
| 로컬 | 각자 PC | http://localhost:5173 (web), :8000 (api) | 개발 |
| 운영 | AWS EC2 | `TODO` https://도메인 | 시연·제출·앱 테스트 |

## 3. 사전 준비 (최초 1회)

### 3-1. AWS 계정
- [ ] 계정 수령 및 접근 확인 (`TODO` 수령일)
- [ ] **AWS Budgets 알림 설정** (예: 월 `TODO` 달러 초과 시 팀 메일 알림) — AWS는 자동으로 과금을 멈추지 않음
- [ ] IAM 사용자 분리 (루트 계정 사용 금지)

### 3-2. EC2
- [ ] 인스턴스 생성 (Ubuntu, 리전 ap-northeast-2)
- [ ] 키페어 생성 → `.pem`은 **레포에 올리지 않음**, 보관 위치 `TODO`
- [ ] 탄력적 IP(Elastic IP) 연결 — 재시작해도 주소가 바뀌지 않도록
- [ ] Docker, Docker Compose 플러그인 설치

### 3-3. 보안그룹 (인바운드)

| 포트 | 허용 대상 | 용도 |
|---|---|---|
| 22 | 팀원 IP만 | SSH |
| 80 | 0.0.0.0/0 | HTTP (HTTPS 리다이렉트용) |
| 443 | 0.0.0.0/0 | HTTPS |
| 8000 | `TODO` | 리버스 프록시 적용 전 임시 개방 여부 결정 |
| **5432** | **열지 않음** | DB는 외부 노출 금지 |

### 3-4. 도메인 · HTTPS (`TODO`)
- iOS 앱은 `http://` 접속을 기본으로 막으므로 **HTTPS가 필수**입니다.
- 방식 후보: 리버스 프록시(nginx 또는 Caddy) + Let's Encrypt 인증서
- 라우팅 후보: `/` → web, `/api` → api

## 4. 환경변수

`.env.example`을 복사해 서버의 `.env`를 만듭니다. **실제 값은 문서·레포에 적지 않습니다.**

| 이름 | 설명 | 운영 값 기준 | 보관 위치 |
|---|---|---|---|
| `POSTGRES_DB` | DB 이름 | yuchion | 서버 `.env` |
| `POSTGRES_USER` | DB 사용자 | yuchion | 서버 `.env` |
| `POSTGRES_PASSWORD` | DB 비밀번호 | **로컬 기본값 사용 금지**, 새로 생성 | 서버 `.env` |
| `DATABASE_URL` | API → DB 접속 주소 | 위 비밀번호 반영 | 서버 `.env` |
| `VITE_API_BASE_URL` | 프론트가 호출할 API 주소 | `TODO` https://도메인/api | 서버 `.env`, 앱 빌드 시 |
| `JWT_SECRET` | 로그인 토큰 서명 키 | 무작위 긴 값 | 서버 `.env` |
| `OPENAI_API_KEY` | OpenAI 호출 | 팀 키 | 서버 `.env` |
| `LANGSMITH_API_KEY` | LangSmith 추적 | 팀 키 | 서버 `.env` |

> ⚠️ `VITE_API_BASE_URL`은 **빌드할 때 결과물에 박힙니다.** 값을 바꾸면 컨테이너 재시작이 아니라 `web` 이미지를 다시 빌드해야 하고, 앱(APK/IPA)도 다시 빌드해야 합니다. 기본값 `http://localhost:8000`으로 빌드하면 브라우저·폰에서 API 호출이 실패합니다.

## 5. 서버 배포 절차

PR의 CI는 API·웹 이미지 빌드를 확인합니다(WBS T74). 배포 담당자는 GitHub Actions의 **Manual Deploy (Docker Compose)**를 수동 실행할 수 있습니다. 이 워크플로는 API·웹 이미지 빌드를 확인한 뒤 AWS EC2에 배포합니다. 아래는 EC2에 직접 접속해 배포하는 절차입니다.

### 5-1. 최초 배포

```bash
# EC2 접속
ssh -i <키파일>.pem ubuntu@<탄력적 IP>

# 코드 받기
git clone <레포 주소> yuchion && cd yuchion
git checkout <운영 브랜치>

# 환경변수
cp .env.example .env
nano .env            # 4장 기준으로 운영 값 입력

# 실행
docker compose up -d --build
docker compose ps    # web·api 실행, db healthy 확인
```

### 5-2. 업데이트 배포

```bash
cd yuchion
git pull
docker compose up -d --build --remove-orphans
docker compose ps
```

### 5-3. 주의
- `compose.yaml`은 로컬 개발 기준이라 `db`가 `5432`, `web`이 `5173`으로 열려 있습니다. 운영에서는 보안그룹으로 5432를 막고, 포트 정리는 `TODO` (운영용 `compose.prod.yaml` 분리 검토).
- `db` 데이터는 `postgres_data` 볼륨에 저장됩니다. `docker compose down -v`는 **DB 데이터를 삭제**하므로 운영에서 사용 금지.

## 6. 배포 확인

| 확인 항목 | 방법 | 기대 결과 |
|---|---|---|
| API 상태 | `curl https://<도메인>/health` (프록시 전: `http://<IP>:8000/health`) | `{"status":"ok"}` |
| 웹 접속 | 브라우저로 `https://<도메인>` | 첫 화면 표시 |
| 원장 화면 (T53 구현 후) | 같은 웹 URL에서 원장 계정으로 로그인 | 원장 화면이 표시되고 역할별 접근이 적용됨 |
| 핵심 흐름 | 로그인 → 민원·요청 제출 → 상태 확인 | 정상 동작 (T30·T63 기록 대상) |
| 리소스 | `docker stats --no-stream` | 메모리 사용량 기록 (T30 기록 대상) |

## 7. 롤백 · 백업

### 7-1. 롤백 (코드)
현재 이미지 레지스트리(ECR)를 쓰지 않으므로 커밋 기준으로 되돌립니다.

```bash
git log --oneline -5           # 정상이던 커밋 확인
git checkout <정상 커밋>
docker compose up -d --build
```
`TODO`: ECR 도입 시 이미지 태그 기준 롤백으로 변경

### 7-2. DB 백업 · 복원
배포 전에 백업을 먼저 받습니다. 상세 절차는 `infra/backup/`에 정리 예정.

```bash
# 백업
docker compose exec -T db pg_dump -U yuchion yuchion > backup_$(date +%Y%m%d_%H%M).sql
# 복원
docker compose exec -T db psql -U yuchion yuchion < backup_YYYYMMDD_HHMM.sql
```

## 8. 모바일 앱 배포 (compose와 별개)

> 현재 `apps/web/package.json`에 Capacitor 패키지가 아직 없습니다. 설치 후 아래 절차를 확정합니다. `TODO`

### 8-1. 공통
- `VITE_API_BASE_URL`을 **운영 https 주소**로 지정해서 웹 빌드
- 앱 버전 번호 규칙: `TODO`
- 설치 채널·버전·날짜를 기록 (T72·T77 기록 대상)

### 8-2. Android (APK)
```bash
cd apps/web
npm run build
npx cap sync android
# Android Studio → Build → Generate Signed Bundle / APK
```
- 서명 키(keystore)는 **레포에 올리지 않음**, 보관 위치 `TODO`
- 배포: 서명 APK 공유 / Play 비공개 테스트 (승인 시)

### 8-3. iOS (TestFlight, 예정)
```bash
cd apps/web
npm run build
npx cap sync ios
# Xcode → Product → Archive → App Store Connect 업로드
```
- 배포: App Store Connect → TestFlight → 테스터 이메일 초대
- 필요: **Mac**(담당 `TODO`), **Apple Developer 계정**(연 $99, 명의 `TODO`), **HTTPS 서버**

## 9. 트러블슈팅

| 증상 | 확인할 것 |
|---|---|
| 외부에서 접속 안 됨 | 보안그룹 인바운드 포트, `docker compose ps` 상태 |
| 웹은 뜨는데 데이터가 안 나옴 | `VITE_API_BASE_URL`이 localhost로 빌드되지 않았는지 |
| 앱에서만 API 실패 (iOS) | 서버가 https인지 |
| api가 바로 종료됨 | `docker compose logs api`, `.env`의 `DATABASE_URL` |
| 메모리 부족으로 컨테이너 재시작 | `docker stats`, 인스턴스 사양 상향 검토 |

`TODO`: 실제 배포하면서 겪은 문제를 추가합니다.

## 10. 변경 이력

| 날짜 | 작성자 | 내용 |
|---|---|---|
| 2026-11-17 | `TODO` | 초안 작성 |
