# data/fixtures

가상 통신문·일정·식단·운영 규정 등 개발용 자료를 둡니다.

## kg-demo-01 (T11)

- `kg-demo-01/`: 가상 햇살유치원(`KG-DEMO-01`) 문서 30개(통신문 12·학사 일정 5·식단 5·운영 규정 6·상담 시간표 2)와 `consult_timetable/staff_busy_blocks.json`
- 문서 목록·평가 문항 연결: [`kg-demo-01/README.md`](kg-demo-01/README.md)
- 다시 만들기·검사: `python3 data/fixtures/make_fixtures.py`

## kg-demo-01/daily_notes (알림장 AI 초안)

- 만 4세 별빛반(담임 T-DEMO-01) 가상 아이 18명, 반 공통 입력 5일치(11/16~20), 아이별 메모 90개(함정 20개 포함)
- 설명: [`kg-demo-01/daily_notes/README.md`](kg-demo-01/daily_notes/README.md) · 함정 평가 문항: [`../evaluation/daily_note/`](../evaluation/daily_note/README.md)
