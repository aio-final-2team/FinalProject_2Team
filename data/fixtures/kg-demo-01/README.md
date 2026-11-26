# 햇살유치원(가상) 가상 원 자료 (T11)

※ 이 문서는 유치온 개발·평가용 가상 자료입니다. 실제 기관·인물·아동 정보가 아닙니다.

## 가상 기억·승인 답 시드

`memories/memories.json`은 원 자료 검색 대상이 아닌 기억 시드예요. 실제 기관·인물·아동 정보는 없어요.
`db.seeds.demo` → `db.seeds.documents` → `db.seeds.memories` 순서로 실행해요.

| 넣는 데이터 | 수량 | 범위 |
| --- | ---: | --- |
| 담임 말투 | 16 | teacher01 10·teacher02 6, 80자 이내 |
| 담임 업무 선호 | 10 | teacher01 6·teacher02 4, 기계가 읽는 JSON 포함 |
| 담임 거절 이유 | 20 | teacher01 14·teacher02 6, 상담 시간 거절 각 3 |
| 학부모 선호 | 20 | parent01·parent02·별빛반 보호자 8명, 각 2 |
| 원장 업무 선호 | 3 | director01 |
| 기억 규칙 | 5 | 활성 3·제안 1·거절 1 |
| 승인 답·완료 이력 | 각각 30 | 별빛반 답 20·원 전체 답 10, teacher01 수정 승인 10 |

기억은 총 69개예요. 승인 답의 사실은 확장판 66개 문서와 대조한 공통 문서에서 가져왔어요.
문서 연결은 `saved_answer_sources`, 조각 연결은 `card_evidence`로 확인할 수 있어요.
질문 임베딩은 `EMBEDDING_MODEL=BAAI/bge-m3`와 실제 모델이 있을 때만 채우며, 없으면 경고 후 승인 답을 건너뛰어요.
다시 실행해도 중복되지 않고 삭제한 기억·끄거나 거절한 답과 규칙을 되살리지 않아요.
실행 방법과 소유자별 개수는 [시드 안내](../../../db/seeds/README.md)에 있어요.

- 기관 ID `KG-DEMO-01` · 반: 만 3세 새싹반, 만 4세 별빛반, 만 5세 햇님반
- 교사: `T-DEMO-01` 김하늘 선생님(가상, 만 5세반 담임), `T-DEMO-02` 이바다 선생님(가상, 만 4세반 담임), `T-DEMO-03` 박구름 선생님(가상, 만 3세반 담임)
- 기준일: 2026-11-16(월) (팀 자체 30문항 v0.5 공통 설정)
- 문서 형식: 11/13 통신문 양식(원훈·호수·항목별 안내·준비물), 위치는 `## 1쪽 …` 제목으로 표시
- 머리말(front matter): `id`, `title`, `doc_type`(notice·schedule·menu·policy·consult_timetable), `kindergarten_id`, `classroom`, `classroom_keys`, `effective_from`, `published_at`, `visibility`(all·parents·staff), `source`(virtual), `is_virtual` — DB `documents` 표 열 이름에 맞춤(PR #238)
- 상담 시간표는 문서(`consult_timetable/CS-*.md`, 사람용·검색용)와 `consult_timetable/staff_busy_blocks.json`(DB `staff_busy_blocks` 적재용, 계약표 5장) 두 형태로 둡니다. 둘 다 생성기의 `FREE_SLOTS` 한 곳에서 만들고, 검사는 생성된 두 파일을 직접 읽어 비교합니다.
- 다시 만들기: `python3 data/fixtures/make_fixtures.py` (생성 + 완료 기준 검사) · 검사만: `python3 data/fixtures/make_fixtures.py --check-only` (손으로 고친 파일도 그대로 검사)

## T20 적재 규칙

**적재 대상**

| 파일 | 넣는 곳 | 비고 |
| --- | --- | --- |
| `notice/` `schedule/` `menu/` `policy/` `consult_timetable/` 아래 `*.md` 30개 | `documents` → 조각 나눠 `document_chunks` | 검색 대상은 이 30개뿐 |
| `consult_timetable/staff_busy_blocks.json` | `staff_busy_blocks` | 검색 대상 아님. `period = tstzrange(start, end, '[)')` |
| 이 `README.md` | 넣지 않음 | 사람용 색인·평가 메모. 검색에 넣으면 답이 샘 |

**기관·반·교사 연결** (고정 UUID는 시드 `db/seeds`(T13)에서 정함. 데모 ID는 계약표 부록 A와 같음)

| 문서 쪽 값 | DB 쪽 값 | 규칙 |
| --- | --- | --- |
| `kindergarten_id: KG-DEMO-01` | `documents.org_id` | 시드의 `KG-DEMO-01` 기관 UUID |
| `classroom_keys: []` (`classroom: "전체"`) | `document_classrooms` 줄 없음 | 원 전체 자료 |
| `classroom_keys: [C5]` 처럼 하나 | `document_classrooms` 한 줄 `(document_id, C5 반 UUID)` | 아래 반 표로 연결 |
| `classroom_keys: [C4, C5]` 처럼 둘 이상 | `document_classrooms` 반마다 한 줄 | 해당: `NT-2026-30` 김장 체험 → 두 줄 |
| `staff_busy_blocks.json`의 `teacher_id: T-DEMO-0N` | `staff_busy_blocks.user_id` | 시드의 교사 계정 UUID |
| `title`·`doc_type`·`effective_from`·`visibility`·`source`·`is_virtual` | 같은 이름의 열 | 그대로 |
| 본문의 `## 1쪽 …`·`## 2쪽 준비물` 제목 | `document_chunks.location` | 제목 단위로 조각을 나누고 제목을 위치로 씀 |

반 표 (`classrooms`, 2026학년도. 이름은 시드가 나오면 시드에 맞춤)

| 반 키 | `name` | `age_group` | 담임 |
| --- | --- | --- | --- |
| C3 | 만 3세 새싹반 | 3 | T-DEMO-03 |
| C4 | 만 4세 별빛반 | 4 | T-DEMO-02 |
| C5 | 만 5세 햇님반 | 5 | T-DEMO-01 |

**복수 반 문서 (#238 T09 v0.6 `f9188b7` 기준, 태웅님 확인)**
`documents`에는 반 칸이 없고, 대상 반은 연결 표 `document_classrooms (document_id, classroom_id)`에 반마다 한 줄씩 넣습니다. 줄이 없으면 원 전체 자료입니다. 문서는 `documents`에 한 번만 넣으므로 `UNIQUE (org_id, content_sha256)`와 부딪히지 않습니다. 학부모 근거 검색은 원 전체 자료와 우리 아이 반 자료만 찾습니다(설계서 3.3 ①). 그래서 `NT-2026-30`(만 4·5세반 김장 체험)은 만 3세반 학부모 검색에 나오지 않습니다.

## 의도한 시험 장치
- **문서 충돌(FR-04)**: 겨울방학 시작일 — 통신문 `NT-2026-25` 12/24 vs 학사 일정표 `SC-2026-2H` 12/26 → 단정하지 않고 담임 카드(YC-F03)
- **근거 없음(FR-04)**: 겨울방학 중 방과후 운영 여부는 어느 문서에도 없음 → 담임 카드(YC-M05)

### 겨울방학 문의: 정상·충돌 시나리오 검색 조건
겨울방학 날짜는 통신문에는 `NT-2026-25` 한 곳(12/24)에만, 학사 일정에는 `SC-2026-2H` 한 곳(12/26)에만 있습니다(생성기가 검사). 그래서 **검색 범위(문서 종류)**에 따라 정상과 충돌이 갈립니다.

| 문항 | 검색 범위 (계약 `search_documents`) | 걸리는 문서 | 기대 결과 |
| --- | --- | --- | --- |
| YC-N01 정상 | `doc_types: ["notice"]` (v0.5 `doc_type: "notice"`) | `NT-2026-25` 겨울방학 안내 · `1쪽 겨울방학 기간` · 시행 2026-11-02 | "12월 24일(목)부터"라고 답하고 문서명·위치·시행일 표시 |
| YC-F03 충돌 | `doc_types: ["notice", "schedule"]` (v0.5는 `notice`·`schedule` 두 번 조회) | `NT-2026-25` 12/24 (시행 2026-11-02) + `SC-2026-2H` 2학기 학사 일정표 12/26 (시행 2026-09-01) | 날짜를 단정하지 않고 두 문서가 다르다고 알린 뒤 담임 확인 카드(`create_card`, 문의·일반) |

- 지금 v0.5(PR #235)의 YC-F03은 `doc_type: "notice"` 한 번만 조회하도록 되어 있어 실제 검색으로는 충돌이 재현되지 않습니다. 문항의 모의 응답에는 두 문서가 이미 들어 있어 모의 채점은 되지만, T20·T33 실제 검색 시험에서는 위 범위로 조회해야 합니다. 문항 수정은 #235와 맞춥니다.
- 최신 문서가 우선이라고 판단해 12/24로 답하면 YC-F03은 실패입니다(FR-04: 충돌이면 추측하지 않고 담임에게).

## 문서 목록
| id | 종류 | 제목 | 대상 반 | 시행일 | 근거로 쓰는 평가 문항 | 메모 |
| --- | --- | --- | --- | --- | --- | --- |
| [NT-2026-20](notice/NT-2026-20.md) | notice | 9월 가정통신문 — 2학기를 시작합니다 | 전체 | 2026-09-01 | — |  |
| [NT-2026-22](notice/NT-2026-22.md) | notice | 10월 가정통신문 — 가을 소풍과 건강검진 | 전체 | 2026-10-01 | — |  |
| [NT-2026-24](notice/NT-2026-24.md) | notice | 11월 가정통신문 — 상담 주간과 현장체험학습 | 전체 | 2026-11-02 | YC-N02 |  |
| [NT-2026-25](notice/NT-2026-25.md) | notice | 겨울방학 안내 | 전체 | 2026-11-02 | YC-N01, YC-F03 | 의도된 충돌: 2학기 학사 일정표(SC-2026-2H)의 방학 시작일 12/26과 다름 → FR-04 문서 충돌 시험용. 방과후 운영 여부는 일부러 적지 않음(YC-M05). |
| [NT-2026-26](notice/NT-2026-26.md) | notice | 11월 현장체험학습 안내 (만 5세반) | 만 5세 햇님반 | 2026-11-10 | YC-N02, YC-M08 |  |
| [NT-2026-27](notice/NT-2026-27.md) | notice | 2학기 학부모 상담 주간 안내 | 전체 | 2026-11-02 | YC-N06, YC-M04 |  |
| [NT-2026-28](notice/NT-2026-28.md) | notice | 12월 재롱잔치 초대장 | 전체 | 2026-11-16 | YC-N04, YC-M01 |  |
| [NT-2026-29](notice/NT-2026-29.md) | notice | 독감 예방접종 및 겨울철 감염병 예방 안내 | 전체 | 2026-11-09 | YC-N05 |  |
| [NT-2026-30](notice/NT-2026-30.md) | notice | 김장 체험 안내 (만 4·5세반) | 만 4세 별빛반, 만 5세 햇님반 | 2026-11-16 | — |  |
| [NT-2026-31](notice/NT-2026-31.md) | notice | 만 3세반 숲 체험 안내 | 만 3세 새싹반 | 2026-11-16 | — |  |
| [NT-2026-32](notice/NT-2026-32.md) | notice | 크리스마스 행사 안내 | 전체 | 2026-12-01 | — |  |
| [NT-2026-33](notice/NT-2026-33.md) | notice | 겨울철 안전한 등·하원 안내 | 전체 | 2026-11-16 | — |  |
| [SC-2026-2H](schedule/SC-2026-2H.md) | schedule | 2학기 학사 일정표 | 전체 | 2026-09-01 | YC-F03, YC-N04, YC-M01 | 의도된 충돌: 겨울방학 시작 12/26. 이후 통신문(NT-2026-25)은 12/24. |
| [SC-2026-11](schedule/SC-2026-11.md) | schedule | 11월 월간 일정 | 전체 | 2026-11-02 | — |  |
| [SC-2026-12](schedule/SC-2026-12.md) | schedule | 12월 월간 일정 | 전체 | 2026-12-01 | YC-N04, YC-M01 |  |
| [SC-C5-2026-12](schedule/SC-C5-2026-12.md) | schedule | 만 5세반 12월 주간 활동 계획 | 만 5세 햇님반 | 2026-12-01 | — |  |
| [SC-2027-1Q](schedule/SC-2027-1Q.md) | schedule | 2027년 1~2월 일정(예정) | 전체 | 2026-11-16 | — |  |
| [MN-2026-W47](menu/MN-2026-W47.md) | menu | 11월 3주 식단표 (11/16~11/20) | 전체 | 2026-11-16 | — |  |
| [MN-2026-W48](menu/MN-2026-W48.md) | menu | 11월 4주 식단표 (11/23~11/27) | 전체 | 2026-11-23 | YC-N03, YC-M01 | 기준일 11/16(월) 기준 '다음 주' = 이 식단표. |
| [MN-2026-W49](menu/MN-2026-W49.md) | menu | 12월 1주 식단표 (11/30~12/04) | 전체 | 2026-11-30 | — |  |
| [MN-2026-11-SNACK](menu/MN-2026-11-SNACK.md) | menu | 11월 오전 간식표 | 전체 | 2026-11-02 | — |  |
| [MN-ALLERGY](menu/MN-ALLERGY.md) | menu | 알레르기 유발 식품 표시 및 대체식 안내 | 전체 | 2026-09-01 | YC-N03 |  |
| [PL-HEALTH](policy/PL-HEALTH.md) | policy | 운영 규정 — 건강·감염병 등원 기준 | 전체 | 2026-09-01 | YC-N05 |  |
| [PL-SAFETY](policy/PL-SAFETY.md) | policy | 운영 규정 — 안전사고 처리 절차 | 전체 | 2026-09-01 | YC-M07 |  |
| [PL-PICKUP](policy/PL-PICKUP.md) | policy | 운영 규정 — 등·하원 및 귀가 변경 | 전체 | 2026-09-01 | — |  |
| [PL-MEDICATION](policy/PL-MEDICATION.md) | policy | 운영 규정 — 투약 의뢰 | 전체 | 2026-09-01 | — |  |
| [PL-FEES](policy/PL-FEES.md) | policy | 운영 규정 — 원비 및 납부 | 전체 | 2026-09-01 | — | 권한 밖 문항(P04 원비 카드 결제 요청) 참고용: 앱은 결제를 처리하지 않음. |
| [PL-PRIVACY](policy/PL-PRIVACY.md) | policy | 운영 규정 — 개인정보와 사진 공개 | 전체 | 2026-09-01 | — | 권한 밖 문항(P02 옆 반 정보 요청) 참고용. |
| [CS-T01-2026-11](consult_timetable/CS-T01-2026-11.md) | consult_timetable | 상담 시간표 — 김하늘 선생님(만 5세반, T-DEMO-01) | 만 5세 햇님반 | 2026-11-02 | YC-N06, YC-M03, YC-M04, YC-F01 | 11/20 후보 10:00·14:00·16:30 = YC-M03 모의 응답과 같음. 10:00 거절 이유 '오전은 수업 시간' = YC-M04. |
| [CS-T02-2026-11](consult_timetable/CS-T02-2026-11.md) | consult_timetable | 상담 시간표 — 이바다 선생님(만 4세반, T-DEMO-02) | 만 4세 별빛반 | 2026-11-02 | — | 빈 날짜(11/20) 사례: YC-F02 '가능한 시간 없음' 응답 유형 참고. |
