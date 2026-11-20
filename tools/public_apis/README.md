# tools/public_apis

실제 호출을 확인한 국가법령정보·기상청 공개 API 클라이언트예요(WBS T15, 기획서 FR-27).

| API | 상태 | 쓰는 곳 |
| --- | --- | --- |
| 국가법령정보 공동활용 Open API (법령 검색 `lawSearch.do` + 조문 `lawService.do`) | 받아서 씀 | 자료 AI 도구 `get_law_article`(API 설계 문서 5.4). 민원 답변의 법령 근거 |
| 기상청 단기예보 조회서비스 (`getVilageFcst`, 공공데이터포털) | 받아서 씀 | 행사 문의 예보(T52). 도구 계약은 아직 없어서 하루 기온·강수 요약만 둬요 |

## 파일

| 파일 | 내용 |
| --- | --- |
| `law.py` | `get_law_article(law_name, article)` 도구와 `LawClient` |
| `weather.py` | `WeatherClient.get_daily_forecast(nx, ny, day)` |
| `common.py` | 10초 시간 제한, 실패를 도구 실패 코드로 바꾸기, 공통 출력 형식 |
| `check.py` | 실제 호출 확인 명령 |
| `tests/` | 녹화한 응답(`fixtures/`)으로만 하는 시험. 실제 호출은 하지 않아요 |

## 쓰는 법

```python
from tools.public_apis.law import get_law_article

get_law_article("영유아보육법", "제33조", trace_id=request_id)
# {"ok": true, "trace_id": "…",
#  "data": {"text": "제33조(급식 관리) 어린이집의 원장은 …",
#           "source_url": "https://www.law.go.kr/법령/영유아보육법/제33조",
#           "fetched_at": "2026-11-20T16:42:22+09:00"}}
```

- `article`은 `제33조`·`33`·`제31조의2`처럼 써요. 항·호가 있으면 `text`에 줄을 바꿔 이어 붙여요.
- 법령 이름은 정확히 같은 현행 법령만 찾아요. `영유아보육법`을 찾을 때 시행령·시행규칙은 고르지 않아요.
- `source_url`은 키가 없는 공개 주소예요. 카드 근거에 그대로 붙여도 돼요.

```python
from tools.public_apis.weather import WeatherClient

WeatherClient().get_daily_forecast(60, 127)   # 격자 nx·ny, 날짜를 안 주면 오늘
# {"date": "2026-11-20", "base": "20261120 0500", "temp_min": -3.0, "temp_max": 3.0,
#  "pop_max": 0, "precipitation": [], "source_url": "…", "fetched_at": "…"}
```

- 오늘 예보는 05시 발표를 써요(그날 최저·최고 기온이 들어 있어요). 다른 날은 가장 최근 발표를 써요.
- `precipitation`은 비·눈이 오는 시각 목록이에요. 예: `[{"time": "1500", "type": "비"}]`
- 기본 격자 60·127은 서울 중구예요. 원 주소가 정해지면 원마다 바꿔요.

## 실패하면

| 경우 | 코드 | `retryable` |
| --- | --- | --- |
| 10초 안에 응답 없음, 연결 실패, HTTP 429·5xx | `UPSTREAM_UNAVAILABLE` | 참 |
| 키 없음·키 오류(HTTP 401·403 등), JSON이 아닌 응답 | `UPSTREAM_UNAVAILABLE` | 거짓 |
| 법령 이름이 없음, 그 법령에 조문이 없음, 조문 번호를 못 읽음, 그날 예보 없음 | `NOT_FOUND` | 거짓 |

`get_law_article`은 예외 대신 `{"ok": false, "error": {code, message, retryable}}`를 돌려줘요. 에이전트는 계약대로 1번 다시 부르고, 그래도 실패하면 법령 인용 없이 초안을 쓰고 '법령 확인 못 함'을 표시해요(T14 명세). 날씨 클라이언트는 `PublicApiError`를 던져요.

## 실제 호출 기록

`python -m tools.public_apis.check`로 확인했어요. 키는 지운 주소예요.

| 시각(KST) | API | 요청 조건 | 응답 | 결과 건수 | 받은 값 예시 |
| --- | --- | --- | --- | --- | --- |
| 2026-11-20 16:42 | 법령 검색 `lawSearch.do` | `target=law`, `query=영유아보육법`, `type=JSON` | HTTP 200, `resultCode 00` | 3건(법률·시행령·시행규칙) | `법령명한글 영유아보육법`, `법령일련번호 286057`, `시행일자 20261120` |
| 2026-11-20 16:42 | 법령 조문 `lawService.do` | `MST=286057`, `JO=003300`(제33조) | HTTP 200 | 조문 1개 | `조문제목 급식 관리`, `조문내용 제33조(급식 관리) 어린이집의 원장은 …` |
| 2026-11-20 16:42 | 단기예보 `getVilageFcst` | `base_date=20261120`, `base_time=0500`, `nx=60`, `ny=127` | HTTP 200, `resultCode 00 NORMAL_SERVICE` | 907건(5일치 14항목) | `TMN -3`, `TMX 3`, `POP 0`, `PTY 0` |

같은 날 확인한 실패 응답도 시험에 넣었어요.

- 법령: 없는 이름 검색은 HTTP 200에 `totalCnt 0`이에요. 없는 조문(`JO=099900`)은 HTTP 200인데 `조문` 칸이 없어요. 둘 다 `NOT_FOUND`로 바꿔요.
- 기상청: 등록 안 된 키는 HTTP 403 `SERVICE_KEY_IS_NOT_REGISTERED_ERROR`(코드 30)예요. `UPSTREAM_UNAVAILABLE`(다시 해도 안 됨)으로 바꿔요.
- 법령 검색 응답의 `법령상세링크`에는 호출한 키(OC)가 그대로 들어 있어요. 녹화 파일에서는 `OC=***`로 지웠어요. 응답을 로그에 통째로 남기지 마세요.

## 자기 키로 돌리기

1. 키 받기
   - 국가법령정보: 국가법령정보 공동활용 사이트에서 Open API를 신청해요. 승인되면 신청한 이메일의 `@` 앞부분이 `OC` 값이에요.
   - 기상청: 공공데이터포털에서 '기상청_단기예보 조회서비스'를 활용 신청하고, 마이페이지의 일반 인증키(Decoding)를 써요. 인코딩된 키를 넣어도 돼요.
2. 레포 루트 `.env`에 넣어요(`.env.example`에 이름이 있어요). `.env`는 커밋하지 않아요.

   ```bash
   LAW_GO_KR_OC=내_OC
   DATA_GO_KR_API_KEY=내_인증키
   ```

3. 레포 루트에서 실행해요.

   ```bash
   set -a; . ./.env; set +a
   python -m tools.public_apis.check                         # 영유아보육법 제33조 + 서울 오늘 예보
   python -m tools.public_apis.check --law 유아교육법 --article 제21조의2 --nx 59 --ny 125
   ```

   둘 다 '받아서 씀'이면 0, 하나라도 '안 됨'이면 1로 끝나요.

## 시험

```bash
pytest -q tools/public_apis
```

녹화한 응답만 써서 키와 인터넷이 없어도 돌아요. 레포 기본 `pytest -q`는 `tests/` 폴더만 모아서, 이 시험은 경로를 줘야 돌아요.
