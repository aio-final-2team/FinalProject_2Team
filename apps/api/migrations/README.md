# apps/api/migrations

태웅 담당 T19 마이그레이션입니다. SQLAlchemy 2.0 Core·psycopg 3·Alembic을 씁니다. 표 정의는 SQL에만 두고 ORM 모델은 만들지 않습니다.

`sql/0001_initial.sql`은 `Docs/Step2/db_schema_draft.sql` v0.7의 적용본입니다. 머리 주석만 바꿨습니다. 초기 적용은 표 27개·뷰 2개·트리거 2개·FK 57개·컬럼 266개를 만듭니다. 0002는 아이별 메모 `daily_note_inputs.child_memos`와 배열 CHECK를 더해요. 0003은 최초 초안 ai_original·아이별 events.daily_note_id와 알림장 이력 네 종류를 더해요. 현재 head는 0003이고 설계 DDL v0.9와 같아요. head는 표 27개·뷰 2개·트리거 2개·FK 58개·컬럼 269개예요. Alembic 관리 표와 확장 객체는 이 수에서 빼요.

저장소 루트에서 실행합니다. `DATABASE_URL`은 **앱 전용 DB** 주소를 넣습니다. 중앙 automation DB를 쓰면 안 됩니다.

```bash
uv pip install --python .venv/bin/python -r apps/api/requirements-dev.txt
export PATH="$PWD/.venv/bin:$PATH"
export DATABASE_URL='postgresql+psycopg://계정:비밀번호@localhost:앱전용포트/앱DB'
python -m alembic -c apps/api/alembic.ini upgrade head
PYTHONPATH=apps/api python -m db.seeds.demo
```

시드는 모의 API와 같은 UUID·로그인 ID·`demo1234`를 씁니다. 가상 원 1개, 2026학년도 반 2개, 계정 21개, 아이 21명(만 4세 별빛반 20명·만 5세 햇님반 1명), 보호자 연결 19개, 담임 배정 2개, 상담실 1개예요. 반·교사 표시 이름은 develop의 모의 시드와 같아요. 별빛반의 새 아이 18명은 PR #262 `roster_c4.json`의 이름·순서로 `C4-NN` → `demo_id("54NN")`을 써요. PR #269 `guardian_requests.json`의 요청 20개는 접수 시각·본문을 그대로 옮겨요. 요청이 있는 16명에게 `demo_id("44NN")`·`parent-c4-NN` 보호자를 연결해요. 관계는 원본 값을 쓰되, C4-15만 GR-04의 mother·GR-16의 father가 달라 먼저 나온 mother를 유지해요. 전체 요청은 기존 두 개를 합쳐 22개이고 자료·조각은 각각 3개예요. 비밀번호는 argon2id 해시로 저장합니다. `ON CONFLICT DO NOTHING`이라 다시 실행해도 기존 행·해시·토큰 판·요청 접수 시각을 덮어쓰지 않습니다. 카드는 채우지 않아요.

Compose의 DB 모드는 엔트리포인트가 설정 검사 → `alembic upgrade head` → 시드 → uvicorn을 실행해요. 이미지에 Alembic 설정·마이그레이션·시드를 함께 넣어요. mock 모드는 DB 초기화를 건너뛰어요. DB 로그인·권한·알림장은 연결됐고, 나머지 진행표는 `apps/api/README.md`를 봐요. 초기화는 API 프로세스 하나에서만 실행해요.

## 새 마이그레이션을 더할 때

적용한 0001·0002·0003은 고치지 않아요. 바꿀 표·컬럼이 생기면 다음 번호의 revision에 ALTER를 더하고 되돌리는 SQL도 함께 써요. ORM 자동 생성은 쓰지 않아요. 아래 0004는 현재 head 다음 번호예요. 새 head가 생기면 그다음 번호를 써요.

```bash
python -m alembic -c apps/api/alembic.ini revision --rev-id 0004 -m '변경 이유'
# 새 versions 파일의 upgrade()·downgrade()를 작성한 뒤
python -m alembic -c apps/api/alembic.ini upgrade head
```

`Docs/Step2/db_schema_draft.sql`도 변경 후 모양으로 고치고 버전을 올려요. `DB_스키마_설계서.md`의 변경 이력에 한 줄을 더해요. 새 revision에서 바로 앞 번호로 내렸다 올리는 시험과 base까지 내렸다 올리는 시험을 함께 확인해요. SQL 작성은 `versions/0002_daily_note_child_memos.py` 구조를 참고해요.

`downgrade base`는 초기 적용이 만든 표·뷰·함수·확장을 모두 지웁니다. 데이터도 사라져요. `downgrade 0002`는 ai_original·알림장 연결 열과 새 이력 네 종류를 지워요. 기존 알림장 행은 남아요. 기존 행을 0003으로 올릴 때 ai_original은 그때 content로 채우므로, 적용 전 사라진 원본은 복원할 수 없어요. `downgrade 0001`은 추가로 아이별 메모 컬럼과 배열 CHECK만 지우고, 기존 입력의 다른 칸은 유지해요. 이때 저장한 메모는 사라지고 다시 0002로 올리면 `[]`로 채워요. 앱 전용 DB에서만 실행해요. 새 revision을 추가하면 up/down 시험의 revision·카탈로그 기대값도 그 변경에 맞춥니다.

## 시험

```bash
PATH="$PWD/.venv/bin:$PATH" python -m pytest -q
tools/test_db.sh
```

첫 명령은 기존 mock 시험과 전환 시험을 돌립니다. `TEST_DATABASE_URL`이 없으면 DB 시험을 건너뛰고, `-rs`를 붙이면 이유를 볼 수 있습니다. 두 번째 명령은 `pgvector/pgvector:pg16`을 빈 호스트 포트에 띄웁니다. 이름은 `yuchion-test-pg-<랜덤>`이며 성공·실패·인터럽트 뒤 자기가 만든 컨테이너만 지웁니다. Docker가 필요하고 로그의 각 줄에는 `[TEST]`가 붙습니다.

DB 시험은 upgrade → downgrade → upgrade의 카탈로그 수와 `pg_dump --schema-only`를 비교합니다. pg_dump가 매번 만드는 `\restrict`·`\unrestrict` 보호 키만 비교에서 뺍니다. head와 설계 DDL v0.9의 스키마도 비교해요. 기존 0001 입력을 0002로 올릴 때 빈 배열이 채워지는지, 메모 배열 원문이 보존되는지, 배열이 아닌 JSON과 SQL NULL을 거부하는지, 0001로 되돌린 뒤 다시 올려도 다른 입력 칸이 같은지 확인해요. 시드 CLI 두 번 실행 뒤 모든 기본 행·비밀번호 해시와 모의 시드의 계정·반·21명·보호자 연결이 같은지, 트랜잭션 커밋과 롤백도 확인해요. 인증·알림장 HTTP 시험은 mock·DB 두 모드로 돌아요. 새로 DB에 연결하는 영역도 같은 방식으로 더해요.

직접 전용 시험 DB를 쓸 때는 `TEST_DATABASE_URL`을 넣고 `python -m pytest -q -rs tests/integration/db`를 실행합니다. 이 시험은 스키마를 지우므로 데이터를 남길 DB를 쓰면 안 됩니다. 직접 실행에는 호스트의 호환 버전 `pg_dump`가 필요합니다. 로컬 기본 포트 5432는 시험 fixture가 거부합니다.
