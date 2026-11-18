"""T11 가상 원 자료 생성기 (햇살유치원·가상)

한 곳(DOCS)에서 문서 30개를 정의하고 data/fixtures/kg-demo-01/ 아래 .md 로 씁니다.
실행: python3 data/fixtures/make_fixtures.py  → 파일 생성 + 완료 기준 검사(check) 결과 출력
"""
from __future__ import annotations

import datetime as dt
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "kg-demo-01"

KG = {
    "id": "KG-DEMO-01",
    "name": "햇살유치원(가상)",
    "motto": "밝고 씩씩하며 서로 돕는 어린이",
    "director": "원장 한소망(가상)",
    "phone": "02-000-0000(가상)",
}
CLASSES = {
    "C3": "만 3세 새싹반",
    "C4": "만 4세 별빛반",
    "C5": "만 5세반(햇살반)",
}
TEACHERS = {
    "T-DEMO-01": "김하늘 선생님(가상, 만 5세반 담임)",
    "T-DEMO-02": "이바다 선생님(가상, 만 4세반 담임)",
    "T-DEMO-03": "박구름 선생님(가상, 만 3세반 담임)",
}
FICTION = "※ 이 문서는 유치온 개발·평가용 가상 자료입니다. 실제 기관·인물·아동 정보가 아닙니다."
DOC_TYPES = {"notice", "schedule", "menu", "policy", "consult_timetable"}  # DB 설계서 documents.doc_type (PR #238)

CLASS_TEACHER = {"C3": "T-DEMO-03", "C4": "T-DEMO-02", "C5": "T-DEMO-01"}
DOCS: list[dict] = []


def classroom_keys(classroom):
    """대상 반 글자 → 반 키 목록. '전체' = [] (원 공통 자료, documents.classroom_id = NULL)"""
    if classroom == "전체":
        return []
    return [k for k, v in CLASSES.items() if v in classroom]


def class_rows():
    return "\n".join(f"| {k} | {v} | {k[1]} | {CLASS_TEACHER[k]} |" for k, v in CLASSES.items())


def doc(id, doc_type, title, effective_from, classroom, body, *, published_at=None, eval_refs=(), note=None, visibility="all"):
    DOCS.append(dict(id=id, doc_type=doc_type, title=title, effective_from=effective_from, visibility=visibility,
                     classroom=classroom, body=body.strip("\n"), published_at=published_at or effective_from,
                     eval_refs=list(eval_refs), note=note))


def letter_head(no, month_label):
    """11/13 통신문 양식(원훈·원 이름·호수·연락처) 머리글"""
    return (f"| 원훈 | {KG['name']} 가정통신문 | {no} |\n| --- | --- | --- |\n"
            f"| {KG['motto']} | {month_label} | 문의 {KG['phone']} |\n")


# ───────────────────────── 통신문 (notice) 12 ─────────────────────────
doc("NT-2026-20", "notice", "9월 가정통신문 — 2학기를 시작합니다", "2026-09-01", "전체", f"""
{letter_head('2026-20호', '2026년 9월')}
## 1쪽 인사말
안녕하세요, 어머님 아버님. 여름방학을 건강하게 보낸 아이들과 2학기를 시작합니다.
2학기에는 '우리 동네'와 '겨울' 주제로 놀이를 이어 갑니다.

## 1쪽 2학기 주요 안내
- 2학기 학사 일정표는 별도 문서(2학기 학사 일정표)로 함께 보냅니다.
- 등원 시간: 오전 8:50 ~ 9:20 / 하원 시간: 오후 2:00(교육과정), 방과후 과정은 오후 6:00까지
- 개인 물품(여벌옷 1벌, 양치 도구)에 이름을 꼭 적어 보내 주세요.
""")

doc("NT-2026-22", "notice", "10월 가정통신문 — 가을 소풍과 건강검진", "2026-10-01", "전체", f"""
{letter_head('2026-22호', '2026년 10월')}
## 1쪽 인사말
선선한 가을바람과 함께 아이들이 바깥 놀이를 즐기고 있습니다.

## 1쪽 10월 행사
- 10월 15일(목) 가을 소풍(근린공원) — 도시락은 원에서 준비합니다.
- 10월 22일(목) 구강 검진(전체 반)

## 2쪽 가정 협조
- 일교차가 큽니다. 얇은 겉옷을 챙겨 주세요.
""")

doc("NT-2026-24", "notice", "11월 가정통신문 — 상담 주간과 현장체험학습", "2026-11-02", "전체", f"""
{letter_head('2026-24호', '2026년 11월')}
## 1쪽 인사말
안녕하세요. 찬바람이 불기 시작하는 11월입니다. 아이들은 요즘 낙엽 놀이에 푹 빠져 있어요.

## 1쪽 11월 주요 일정
- 11월 16일(월) ~ 20일(금) 2학기 학부모 상담 주간 (자세한 시간은 '2학기 학부모 상담 주간 안내' 참고)
- 11월 26일(목) 만 5세반 현장체험학습 (자세한 내용은 '11월 현장체험학습 안내' 참고)
- 11월 27일(금) 김장 체험(만 4·5세반)

## 2쪽 겨울방학 안내
- 겨울방학 일정은 같은 날 보내는 '겨울방학 안내' 통신문을 확인해 주세요.
""", eval_refs=["YC-N02"])

doc("NT-2026-25", "notice", "겨울방학 안내", "2026-11-02", "전체", f"""
{letter_head('2026-25호', '2026년 11월')}
## 1쪽 겨울방학 기간
- 겨울방학: **2026년 12월 24일(목) ~ 2027년 1월 3일(일)**
- 개학: 2027년 1월 4일(월)

## 1쪽 방학 중 생활
- 규칙적인 생활 습관(기상·식사·잠자는 시간)을 지켜 주세요.
- 방학 중 긴급 연락은 원 대표번호로 해 주세요.
""", eval_refs=["YC-N01", "YC-F03"],
    note="의도된 충돌: 2학기 학사 일정표(SC-2026-2H)의 방학 시작일 12/26과 다름 → FR-04 문서 충돌 시험용. 방과후 운영 여부는 일부러 적지 않음(YC-M05).")

doc("NT-2026-26", "notice", "11월 현장체험학습 안내 (만 5세반)", "2026-11-10", "만 5세반(햇살반)", f"""
{letter_head('2026-26호', '2026년 11월')}
## 1쪽 일정
- 날짜: 2026년 11월 26일(목)
- 장소: 햇살 어린이 농장(가상) — 고구마 캐기, 동물 먹이 주기
- 출발 09:30 원 앞 / 도착 13:30 예정 (버스 이동)

## 2쪽 준비물
- **도시락** (원에서 점심을 준비하지 않습니다)
- **물병** (이름 표시)
- **여벌옷** 1벌 (흙 놀이가 있어요)
- 편한 운동화, 모자

## 2쪽 안전 안내
- 차량 멀미가 있는 아이는 담임에게 미리 알려 주세요.
- 비가 오면 원내 활동으로 바뀌고 전날 오후 4시까지 알림장으로 안내합니다.
""", eval_refs=["YC-N02", "YC-M08"])

doc("NT-2026-27", "notice", "2학기 학부모 상담 주간 안내", "2026-11-02", "전체", f"""
{letter_head('2026-27호', '2026년 11월')}
## 1쪽 상담 주간
- 기간: 2026년 11월 16일(월) ~ 20일(금)
- 방법: 대면 또는 전화, 1회 30분
- 신청: 유치온 앱 '상담 신청' 또는 담임에게 알림장으로 신청

## 1쪽 확정 방법
- 앱에서 고른 시간은 '신청'이며, **담임 선생님이 확정해야 예약이 됩니다.**
- 오전(9:30~12:00)은 수업 시간이라 원칙적으로 상담이 어렵습니다. 담임이 수업 일정에 따라 예외로 열어 둔 시간만 신청할 수 있어요.
- 반별 가능 시간은 '상담 시간표'를 확인해 주세요.
""", eval_refs=["YC-N06", "YC-M04"])

doc("NT-2026-28", "notice", "12월 재롱잔치 초대장", "2026-11-16", "전체", f"""
{letter_head('2026-28호', '2026년 11월')}
## 1쪽 초대 인사
한 해 동안 자란 아이들의 모습을 보여 드리는 재롱잔치에 가족을 초대합니다.

## 1쪽 일시·장소
- 일시: **2026년 12월 18일(금) 오전 10:30 ~ 12:00**
- 장소: 햇살 구민회관 소강당(가상)
- 가족 입장은 아이 1명당 2명까지 가능합니다.

## 2쪽 준비
- 의상은 원에서 준비합니다. 흰 양말만 챙겨 주세요.
- 당일 아이들은 평소처럼 원으로 등원합니다.
""", eval_refs=["YC-N04", "YC-M01"])

doc("NT-2026-29", "notice", "독감 예방접종 및 겨울철 감염병 예방 안내", "2026-11-09", "전체", f"""
{letter_head('2026-29호', '2026년 11월')}
## 1쪽 예방접종 권장
- 만 6개월 이상 어린이는 독감 예방접종을 권장합니다(가까운 병원·보건소).
- 접종 후 이상 반응이 있으면 등원 전 담임에게 알려 주세요.

## 1쪽 등원 기준
- 발열·감염병 등원 기준은 운영 규정 '건강·감염병 등원 기준'을 따릅니다.
""", eval_refs=["YC-N05"])

doc("NT-2026-30", "notice", "김장 체험 안내 (만 4·5세반)", "2026-11-16", "만 4세 별빛반, 만 5세반(햇살반)", f"""
{letter_head('2026-30호', '2026년 11월')}
## 1쪽 일정
- 날짜: 2026년 11월 27일(금) 오전 10:00
- 장소: 원 실내 놀이실

## 1쪽 준비물
- 앞치마, 팔토시 (없으면 원에서 빌려 드려요)
- 고춧가루를 다루므로 피부가 예민한 아이는 담임에게 알려 주세요.
""")

doc("NT-2026-31", "notice", "만 3세반 숲 체험 안내", "2026-11-16", "만 3세 새싹반", f"""
{letter_head('2026-31호', '2026년 11월')}
## 1쪽 일정
- 날짜: 2026년 11월 24일(화) 오전 10:00 ~ 11:30
- 장소: 원 뒤 산책로(가상)

## 1쪽 준비물
- 모자, 장갑, 물병
""")

doc("NT-2026-32", "notice", "크리스마스 행사 안내", "2026-12-01", "전체", f"""
{letter_head('2026-32호', '2026년 12월')}
## 1쪽 행사
- 날짜: 2026년 12월 23일(수) 오전 10:00
- 산타 할아버지가 아이들에게 선물을 나눠 줍니다.

## 1쪽 가정 협조
- 선물(1만 원 이내)에 아이 이름과 반을 적어 12월 18일(금)까지 보내 주세요.
- 빨간색·초록색 옷을 입고 오면 더 즐거워요.
""", published_at="2026-11-16")

doc("NT-2026-33", "notice", "겨울철 안전한 등·하원 안내", "2026-11-16", "전체", f"""
{letter_head('2026-33호', '2026년 11월')}
## 1쪽 등·하원 안전
- 눈·결빙 시 차량 운행 시간이 10분 정도 늦어질 수 있습니다.
- 귀가 보호자가 바뀌는 날은 '등·하원 및 귀가 변경 규정'에 따라 미리 알려 주세요.
""")

# ───────────────────────── 학사 일정 (schedule) 5 ─────────────────────────
doc("SC-2026-2H", "schedule", "2학기 학사 일정표", "2026-09-01", "전체", """
| 날짜 | 내용 | 대상 |
| --- | --- | --- |
| 2026-09-01(화) | 2학기 개학 | 전체 |
| 2026-10-15(목) | 가을 소풍 | 전체 |
| 2026-11-16(월) ~ 11-20(금) | 2학기 학부모 상담 주간 | 전체 |
| 2026-11-26(목) | 현장체험학습 | 만 5세반 |
| 2026-12-18(금) | 재롱잔치 | 전체 |
| 2026-12-23(수) | 크리스마스 행사 | 전체 |
| **2026-12-26(토) ~ 2027-01-03(일)** | **겨울방학** | 전체 |
| 2027-01-04(월) | 개학 | 전체 |
| 2027-02-26(금) | 수료식·졸업식 | 전체 |
""", eval_refs=["YC-F03", "YC-N04", "YC-M01"],
    note="의도된 충돌: 겨울방학 시작 12/26. 이후 통신문(NT-2026-25)은 12/24.")

doc("SC-2026-11", "schedule", "11월 월간 일정", "2026-11-02", "전체", """
| 날짜 | 내용 | 대상 |
| --- | --- | --- |
| 11-09(월) | 독감 예방 교육 | 전체 |
| 11-16(월) ~ 11-20(금) | 학부모 상담 주간 | 전체 |
| 11-24(화) | 숲 체험 | 만 3세반 |
| 11-26(목) | 현장체험학습(햇살 어린이 농장) | 만 5세반 |
| 11-27(금) | 김장 체험 | 만 4·5세반 |
""")

doc("SC-2026-12", "schedule", "12월 월간 일정", "2026-12-01", "전체", """
| 날짜 | 내용 | 대상 |
| --- | --- | --- |
| 12-04(금) | 소방 대피 훈련 | 전체 |
| 12-11(금) | 재롱잔치 총연습 | 전체 |
| **12-18(금)** | **재롱잔치** (햇살 구민회관 소강당, 10:30) | 전체 |
| 12-23(수) | 크리스마스 행사 | 전체 |
""", published_at="2026-11-16", eval_refs=["YC-N04", "YC-M01"])

doc("SC-C5-2026-12", "schedule", "만 5세반 12월 주간 활동 계획", "2026-12-01", "만 5세반(햇살반)", """
| 주 | 주제 | 주요 활동 |
| --- | --- | --- |
| 12월 1주 | 겨울 날씨 | 눈 결정 관찰, 신문지 눈싸움 |
| 12월 2주 | 재롱잔치 준비 | 노래·율동 연습 |
| 12월 3주 | 재롱잔치 | 12/18(금) 재롱잔치 |
| 12월 4주 | 나눔 | 크리스마스 카드 만들기 |
""", published_at="2026-11-16")

doc("SC-2027-1Q", "schedule", "2027년 1~2월 일정(예정)", "2026-11-16", "전체", """
| 날짜 | 내용 | 대상 |
| --- | --- | --- |
| 2027-01-04(월) | 개학 | 전체 |
| 2027-01-15(금) | 겨울 놀이 한마당 | 전체 |
| 2027-02-26(금) | 수료식·졸업식 | 전체 |

일정은 바뀔 수 있으며 확정되면 통신문으로 다시 안내합니다.
""")

# ───────────────────────── 식단 (menu) 5 ─────────────────────────
MENU_NOTE = "알레르기 유발 식품 번호: ①난류 ②우유 ⑤대두 ⑥밀 ⑨새우 ⑬땅콩 ⑭호두(견과류)"

doc("MN-2026-W47", "menu", "11월 3주 식단표 (11/16~11/20)", "2026-11-16", "전체", f"""
| 날짜 | 점심 | 오후 간식 |
| --- | --- | --- |
| 11-16(월) | 현미밥, 미역국, 닭갈비⑤⑥, 배추김치 | 바나나, 우유② |
| 11-17(화) | 차조밥, 콩나물국, 생선까스①⑥, 깍두기 | 고구마 |
| 11-18(수) | 카레라이스②⑥, 계란국①, 단무지 | 사과 |
| 11-19(목) | 흑미밥, 된장국⑤, 불고기⑤⑥, 시금치나물 | 떡 |
| 11-20(금) | 볶음밥①, 유부국⑤, 요구르트② | 귤 |

{MENU_NOTE}
""")

doc("MN-2026-W48", "menu", "11월 4주 식단표 (11/23~11/27)", "2026-11-23", "전체", f"""
| 날짜 | 점심 | 오후 간식 |
| --- | --- | --- |
| 11-23(월) | 쌀밥, 소고기무국, 계란말이①, 배추김치 | 우유②, 시리얼⑥ |
| 11-24(화) | 보리밥, 순두부찌개⑤, **멸치호두볶음⑭**, 깍두기 | 배 |
| 11-25(수) | 짜장덮밥⑤⑥, 오이무침 | 찐 감자 |
| 11-26(목) | (만 5세반 현장체험학습: 도시락) / 그 외 반: 비빔밥①⑤, 맑은국 | 귤 |
| 11-27(금) | 쌀밥, 김장 김치, 수육, **땅콩조림⑬** | 호두과자①②⑥⑭ |

{MENU_NOTE}
견과류(⑬땅콩·⑭호두) 들어가는 날: **11/24(화) 점심, 11/27(금) 점심·간식**. 알레르기가 있는 아이는 대체식을 제공하니 담임에게 미리 알려 주세요.
""", published_at="2026-11-16", eval_refs=["YC-N03", "YC-M01"],
    note="기준일 11/16(월) 기준 '다음 주' = 이 식단표.")

doc("MN-2026-W49", "menu", "12월 1주 식단표 (11/30~12/04)", "2026-11-30", "전체", f"""
| 날짜 | 점심 | 오후 간식 |
| --- | --- | --- |
| 11-30(월) | 쌀밥, 어묵국⑥, 닭볶음탕, 배추김치 | 우유② |
| 12-01(화) | 잡곡밥, 미소된장국⑤, 연어구이, 브로콜리 | 단호박 |
| 12-02(수) | 크림스파게티②⑥, 양배추샐러드 | 귤 |
| 12-03(목) | 쌀밥, 김치찌개, 두부조림⑤ | 고구마 |
| 12-04(금) | 떡국①, 동그랑땡①⑥ | 사과 |

{MENU_NOTE}
""", published_at="2026-11-23")

doc("MN-2026-11-SNACK", "menu", "11월 오전 간식표", "2026-11-02", "전체", """
| 요일 | 오전 간식 |
| --- | --- |
| 월 | 죽(소고기 야채죽) |
| 화 | 우유②, 통밀빵⑥ |
| 수 | 두유⑤, 떡 |
| 목 | 요구르트②, 과일 |
| 금 | 누룽지 |
""")

doc("MN-ALLERGY", "menu", "알레르기 유발 식품 표시 및 대체식 안내", "2026-09-01", "전체", f"""
## 1쪽 표시 방법
- 식단표의 동그라미 번호는 식품의약품안전처 알레르기 유발 식품 번호를 따릅니다.
- {MENU_NOTE}

## 1쪽 대체식
- 입학 때 제출한 알레르기 정보를 바탕으로 대체식을 제공합니다.
- 새로 알게 된 알레르기는 진단서와 함께 담임에게 알려 주세요.
""", eval_refs=["YC-N03"])

# ───────────────────────── 운영 규정 (policy) 6 ─────────────────────────
doc("PL-HEALTH", "policy", "운영 규정 — 건강·감염병 등원 기준", "2026-09-01", "전체", """
## 제3조 발열 시 등원
1. 아침 체온이 **37.5℃ 이상**이면 등원하지 않습니다.
2. 원에서 37.5℃ 이상 열이 나면 보호자에게 연락하고, 보호자는 가능한 한 빨리 아이를 데려갑니다.
3. 해열제 없이 24시간 동안 열이 없으면 다시 등원할 수 있습니다.

## 제4조 감염병
1. 독감·수족구·장염 등 법정 감염병은 의사 소견서에 적힌 격리 기간이 끝난 뒤 등원합니다.
2. 다시 등원할 때 '등원 확인서'를 제출합니다.
""", eval_refs=["YC-N05"])

doc("PL-SAFETY", "policy", "운영 규정 — 안전사고 처리 절차", "2026-09-01", "전체", """
## 제7조 사고 발생 시
1. 담임은 즉시 응급 처치를 하고, 머리·얼굴 부상이나 출혈이 있으면 **원장에게 바로 보고**합니다.
2. 보호자에게 30분 이내에 전화로 알립니다.
3. 병원 진료가 필요하면 보호자와 협의하여 이동합니다.

## 제8조 기록·보고
1. 담임은 당일 '안전사고 보고서'를 작성하여 원장에게 제출합니다.
2. 원장은 필요 시 교육청 보고 절차를 따릅니다.
3. 보호자가 사고 경위를 문의하면 원장 또는 담임이 사실대로 안내합니다.
""", eval_refs=["YC-M07"])

doc("PL-PICKUP", "policy", "운영 규정 — 등·하원 및 귀가 변경", "2026-09-01", "전체", """
## 제10조 귀가 보호자
1. 아이는 입학 때 등록한 보호자에게만 인계합니다.
2. 다른 사람이 데리러 오는 날은 **당일 오후 1시까지** 앱 또는 전화로 이름·관계·연락처를 알려 주세요.
3. 등록되지 않은 사람이 오면 보호자에게 전화로 확인한 뒤 인계합니다.
""")

doc("PL-MEDICATION", "policy", "운영 규정 — 투약 의뢰", "2026-09-01", "전체", """
## 제12조 투약
1. 투약은 보호자가 작성한 '투약 의뢰서'가 있을 때만 합니다.
2. 의뢰서에는 약 이름·용량·시간·보관 방법을 적습니다.
3. 처방전 없는 해열제는 보호자 동의가 있어도 1회만 투약합니다.
""")

doc("PL-FEES", "policy", "운영 규정 — 원비 및 납부", "2026-09-01", "전체", """
## 제15조 원비
1. 원비는 매월 10일까지 지정 계좌로 납부합니다(가상 계좌).
2. 원비 납부·환불 문의는 행정실에서 안내합니다. 유치온 앱에서는 결제를 받지 않습니다.
3. 방과후 과정비는 신청한 달에만 청구합니다.
""", note="권한 밖 문항(P04 원비 카드 결제 요청) 참고용: 앱은 결제를 처리하지 않음.")

doc("PL-PRIVACY", "policy", "운영 규정 — 개인정보와 사진 공개", "2026-09-01", "전체", """
## 제18조 개인정보
1. 원아·보호자 정보는 해당 보호자와 담당 교직원만 볼 수 있습니다.
2. 다른 반·다른 아이의 정보는 안내하지 않습니다.

## 제19조 사진
1. 활동 사진은 공개 동의를 한 아이만 올립니다.
2. 동의하지 않은 아이의 얼굴은 가리거나 사진에서 뺍니다.
""", note="권한 밖 문항(P02 옆 반 정보 요청) 참고용.")

# ───────────────────────── 상담 시간표 (consult_timetable) 2 ─────────────────────────
# 상담 가능 시간의 원천은 이 표 하나뿐이다. 문서(CS-*.md)의 표와 staff_busy_blocks.json 을
# 모두 여기서 만들고, 검사는 생성된 두 파일을 직접 읽어 비교한다(PR #247 검토 의견).
# 값: 가능 시간 목록, [] = 가능 시간 없음, None = 하루 종일 off(교사 연수)
DAY_START, DAY_END, SLOT_MIN = "09:00", "17:30", 30
FREE_SLOTS = {
    "T-DEMO-01": {"2026-11-16": ["14:00", "15:00"], "2026-11-17": ["14:30", "16:00"],
                  "2026-11-18": ["15:00"], "2026-11-19": ["14:00", "16:30"],
                  "2026-11-20": ["10:00", "14:00", "16:30"]},
    "T-DEMO-02": {"2026-11-16": ["15:00", "16:00"], "2026-11-17": [], "2026-11-18": ["14:00"],
                  "2026-11-19": [], "2026-11-20": None},
}
SLOT_REMARKS = {
    ("T-DEMO-01", "2026-11-18"): "오후 교사 회의",
    ("T-DEMO-01", "2026-11-20"): "10:00은 수업 일정에 따라 담임이 거절할 수 있음(오전 예외 시간)",
    ("T-DEMO-02", "2026-11-20"): "교사 연수로 상담 없음",
}
MEETING_DAYS = {("T-DEMO-01", "2026-11-18")}


def timetable_table(teacher):
    rows = ["| 날짜 | 가능 시간(30분) | 비고 |", "| --- | --- | --- |"]
    for day, slots in FREE_SLOTS[teacher].items():
        d = dt.date.fromisoformat(day)
        label = f"{day[5:]}({'월화수목금토일'[d.weekday()]})"
        rows.append(f"| {label} | {', '.join(slots) if slots else '—'} | {SLOT_REMARKS.get((teacher, day), '')} |")
    return "\n".join(rows)


doc("CS-T01-2026-11", "consult_timetable", "상담 시간표 — 김하늘 선생님(만 5세반, T-DEMO-01)", "2026-11-02", "만 5세반(햇살반)", f"""
{timetable_table("T-DEMO-01")}

- 담당 교사 ID: T-DEMO-01
- 신청은 '요청'이며 담임이 확정해야 예약이 됩니다.
""", eval_refs=["YC-N06", "YC-M03", "YC-M04", "YC-F01"],
    note="11/20 후보 10:00·14:00·16:30 = YC-M03 모의 응답과 같음. 10:00 거절 이유 '오전은 수업 시간' = YC-M04.")

doc("CS-T02-2026-11", "consult_timetable", "상담 시간표 — 이바다 선생님(만 4세반, T-DEMO-02)", "2026-11-02", "만 4세 별빛반", f"""
{timetable_table("T-DEMO-02")}

- 담당 교사 ID: T-DEMO-02
""", note="빈 날짜(11/20) 사례: YC-F02 '가능한 시간 없음' 응답 유형 참고.")

# ───────────────────────── 쓰기·검사 ─────────────────────────
REQUIRED_EVAL = {
    "YC-N01": ["2026년 12월 24일"],
    "YC-F03": ["12월 24일", "12-26"],
    "YC-N02": ["도시락", "물병", "여벌옷"],
    "YC-M08": ["2쪽 준비물", "도시락"],
    "YC-N03": ["⑭", "⑬", "11-24", "11-27"],
    "YC-N04": ["12월 18일"],
    "YC-M01": ["재롱잔치", "11-23"],
    "YC-N05": ["37.5℃"],
    "YC-M07": ["원장에게 바로 보고"],
    "YC-N06": ["11-20(금)", "14:00", "16:30"],
    "YC-M03": ["10:00", "14:00", "16:30"],
    "YC-M04": ["오전"],
}


def render(d):
    lines = ["---",
             f"id: {d['id']}",
             f"title: \"{d['title']}\"",
             f"doc_type: {d['doc_type']}",
             f"kindergarten_id: {KG['id']}",
             f"kindergarten_name: {KG['name']}",
             f"classroom: \"{d['classroom']}\"",
             f"classroom_keys: [{', '.join(classroom_keys(d['classroom']))}]",
             f"effective_from: {d['effective_from']}",
             f"published_at: {d['published_at']}",
             f"visibility: {d['visibility']}",
             "source: virtual",
             "is_virtual: true"]
    lines += ["---", "", f"# {d['title']}", "", f"> {FICTION}", "",
              f"- 대상 반: {d['classroom']}", f"- 시행일: {d['effective_from']}", "", d["body"], ""]
    return "\n".join(lines)


def filename(d):
    return f"{d['doc_type']}/{d['id']}.md"


def check():
    errors = []
    ids = [d["id"] for d in DOCS]
    if len(ids) != len(set(ids)):
        errors.append("중복 id")
    for d in DOCS:
        p = OUT / filename(d)
        t = p.read_text(encoding="utf-8")
        if FICTION not in t:
            errors.append(f"{d['id']}: 가상 표시 없음")
        dt.date.fromisoformat(d["effective_from"])
        if not d["classroom"]:
            errors.append(f"{d['id']}: 대상 반 없음")
        elif d["classroom"] != "전체" and len(classroom_keys(d["classroom"])) != d["classroom"].count(",") + 1:
            errors.append(f"{d['id']}: 대상 반 '{d['classroom']}'을 반 키로 바꿀 수 없음")
        if d["doc_type"] not in DOC_TYPES:
            errors.append(f"{d['id']}: doc_type {d['doc_type']}")
        for m in re.finditer(r"(\d{4})-(\d{2})-(\d{2})\((.)\)", t):
            day = dt.date(int(m[1]), int(m[2]), int(m[3]))
            if "월화수목금토일"[day.weekday()] != m[4]:
                errors.append(f"{d['id']}: 요일 틀림 {m[0]}")
    for case, needles in REQUIRED_EVAL.items():
        texts = [(OUT / filename(d)).read_text(encoding="utf-8") for d in DOCS if case in d["eval_refs"]]
        if not texts:
            errors.append(f"{case}: 근거 문서 없음")
            continue
        blob = "\n".join(texts)
        for n in needles:
            if n not in blob:
                errors.append(f"{case}: 근거 문구 '{n}' 없음")
    blob_all = "\n".join((OUT / filename(d)).read_text(encoding="utf-8") for d in DOCS)
    # 겨울방학 정상(N01)·충돌(F03) 시나리오가 검색 범위로 갈리는지
    vac = {}
    for d in DOCS:
        t = (OUT / filename(d)).read_text(encoding="utf-8")
        if re.search(r"12월 26일|12-26", t):
            vac.setdefault("12/26", []).append((d["id"], d["doc_type"]))
        if re.search(r"12월 24일|12-24", t):
            vac.setdefault("12/24", []).append((d["id"], d["doc_type"]))
    if vac.get("12/24") != [("NT-2026-25", "notice")]:
        errors.append(f"YC-N01: 12/24 근거는 통신문 NT-2026-25 한 곳이어야 함 {vac.get('12/24')}")
    if vac.get("12/26") != [("SC-2026-2H", "schedule")]:
        errors.append(f"YC-F03: 12/26 근거는 학사 일정 SC-2026-2H 한 곳이어야 함 {vac.get('12/26')}")
    if "방학 중 방과후" in blob_all or "방학 중에도 방과후" in blob_all:
        errors.append("YC-M05: 방학 중 방과후 운영 근거가 있으면 안 됨")
    return errors


# ───────────────────────── 상담 시간표 → staff_busy_blocks (계약표 5장) ─────────────────────────
# 계약표 5장: 상담 시간표는 '교사별 요일·시간'으로 staff_busy_blocks 에 들어가고,
# 후보 시간은 코드 AI(find_consult_slots)가 '바쁜 시간의 빈틈'으로 계산한다.
# 위 FREE_SLOTS(상담 시간표의 유일한 원천)의 여집합을 바쁜 시간으로 만든다.


def _m(hhmm):
    h, m = map(int, hhmm.split(":"))
    return h * 60 + m


def _hhmm(x):
    return f"{x // 60:02d}:{x % 60:02d}"


def busy_blocks():
    out = []
    for teacher, days in FREE_SLOTS.items():
        for day, slots in days.items():
            if slots is None:
                out.append({"teacher_id": teacher, "start": f"{day}T{DAY_START}:00+09:00",
                            "end": f"{day}T{DAY_END}:00+09:00", "kind": "off"})
                continue
            free = sorted((_m(t), _m(t) + SLOT_MIN) for t in slots)
            cur, gaps = _m(DAY_START), []
            for a, b in free:
                if a > cur:
                    gaps.append((cur, a))
                cur = max(cur, b)
            if cur < _m(DAY_END):
                gaps.append((cur, _m(DAY_END)))
            for a, b in gaps:  # 12:00·13:00 경계에서 나눠 종류를 붙임
                cuts = sorted({a, b, *[c for c in (720, 780) if a < c < b]})
                for x, y in zip(cuts, cuts[1:]):
                    kind = "class" if y <= 720 else "duty" if y <= 780 else (
                        "meeting" if (teacher, day) in MEETING_DAYS else "duty")
                    out.append({"teacher_id": teacher, "start": f"{day}T{_hhmm(x)}:00+09:00",
                                "end": f"{day}T{_hhmm(y)}:00+09:00", "kind": kind})
    return out


def write_busy_blocks():
    import json
    d = OUT / "consult_timetable"
    d.mkdir(parents=True, exist_ok=True)
    data = {"kindergarten_id": KG["id"], "is_virtual": True, "table": "staff_busy_blocks",
            "note": "period = [start, end). 후보 시간은 이 바쁜 시간의 빈틈(30분 단위)으로 계산. 상담 시간표 문서(CS-*)와 같은 값.",
            "day_window": [DAY_START, DAY_END], "slot_minutes": SLOT_MIN, "blocks": busy_blocks()}
    (d / "staff_busy_blocks.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def free_from_json(path):
    """생성된 staff_busy_blocks.json 만 읽어 (교사, 날짜) → 빈틈 30분 시작 시각 목록"""
    import json
    data = json.loads(path.read_text(encoding="utf-8"))
    win_a, win_b = (_m(x) for x in data["day_window"])
    step = data["slot_minutes"]
    by_day = {}
    for b in data["blocks"]:
        by_day.setdefault((b["teacher_id"], b["start"][:10]), []).append(
            (_m(b["start"][11:16]), _m(b["end"][11:16])))
    out = {}
    for key, spans in by_day.items():
        free, cur = [], win_a
        for a, b in sorted(spans):
            free += [_hhmm(t) for t in range(cur, a, step)]
            cur = max(cur, b)
        free += [_hhmm(t) for t in range(cur, win_b, step)]
        out[key] = free
    return out


def free_from_markdown(path):
    """생성된 상담 시간표 문서(CS-*.md)만 읽어 (교사, 날짜) → 가능 시간 목록"""
    t = path.read_text(encoding="utf-8")
    teacher = re.search(r"담당 교사 ID: (T-DEMO-\d+)", t)[1]
    year = re.search(r"effective_from: (\d{4})", t)[1]
    out = {}
    for m in re.finditer(r"^\| (\d{2}-\d{2})\(.\) \| ([^|]*) \|", t, re.M):
        times = re.findall(r"\d{2}:\d{2}", m[2])
        out[(teacher, f"{year}-{m[1]}")] = times
    return out


def check_busy_blocks():
    """문서(.md)와 DB 적재용 JSON 을 서로 직접 비교한다. FREE_SLOTS 는 보지 않는다."""
    errs = []
    from_json = free_from_json(OUT / "consult_timetable" / "staff_busy_blocks.json")
    from_md = {}
    for p in sorted((OUT / "consult_timetable").glob("CS-*.md")):
        from_md.update(free_from_markdown(p))
    if not from_md:
        errs.append("상담 시간표 문서에서 시간을 읽지 못함")
    for key in sorted(set(from_md) | set(from_json)):
        a, b = from_md.get(key), from_json.get(key)
        if a != b:
            errs.append(f"상담 시간 불일치 {key[0]} {key[1]}: 문서 {a} ≠ JSON 빈틈 {b}")
    if from_md.get(("T-DEMO-01", "2026-11-20")) != ["10:00", "14:00", "16:30"]:
        errs.append("YC-M03 모의 응답(10:00·14:00·16:30)과 다름")
    return errs


def write_index():
    rows = ["| id | 종류 | 제목 | 대상 반 | 시행일 | 근거로 쓰는 평가 문항 | 메모 |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for d in DOCS:
        rows.append(f"| [{d['id']}]({filename(d)}) | {d['doc_type']} | {d['title']} | {d['classroom']} | {d['effective_from']} | {', '.join(d['eval_refs']) or '—'} | {d['note'] or ''} |")
    head = f"""# {KG['name']} 가상 원 자료 (T11)

{FICTION}

- 기관 ID `{KG['id']}` · 반: {', '.join(CLASSES.values())}
- 교사: {', '.join(f'`{k}` {v}' for k, v in TEACHERS.items())}
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
| `classroom_keys: []` (`classroom: "전체"`) | `documents.classroom_id = NULL` | 원 공통 자료 |
| `classroom_keys: [C5]` 처럼 하나 | `documents.classroom_id` = 그 반 UUID | 아래 반 표로 연결 |
| `classroom_keys: [C4, C5]` 처럼 둘 이상 | 아래 '복수 반' 참고 | 해당: `NT-2026-30` 김장 체험 |
| `staff_busy_blocks.json`의 `teacher_id: T-DEMO-0N` | `staff_busy_blocks.user_id` | 시드의 교사 계정 UUID |
| `title`·`doc_type`·`effective_from`·`visibility`·`source`·`is_virtual` | 같은 이름의 열 | 그대로 |
| 본문의 `## 1쪽 …`·`## 2쪽 준비물` 제목 | `document_chunks.location` | 제목 단위로 조각을 나누고 제목을 위치로 씀 |

반 표 (`classrooms`, 2026학년도. 이름은 시드가 나오면 시드에 맞춤)

| 반 키 | `name` | `age_group` | 담임 |
| --- | --- | --- | --- |
{class_rows()}

**복수 반 문서 (확인 필요: 태웅·#238)**
`documents.classroom_id`는 반 하나만 담고, `UNIQUE (org_id, content_sha256)` 때문에 같은 문서를 반마다 한 줄씩 넣을 수도 없습니다. 제안: 지금은 `classroom_id = NULL`(원 공통)로 넣고 본문의 '대상 반'으로 구분합니다. 반별 검색 필터가 꼭 필요해지면 `document_classrooms(document_id, classroom_id)` 연결 표를 #238에 추가하는 안을 태웅님과 정합니다.

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
"""
    (OUT / "README.md").write_text(head + "\n".join(rows) + "\n", encoding="utf-8")


def main():
    if "--check-only" in sys.argv:
        errs = check() + check_busy_blocks()
        print("검사 실패:" if errs else "검사 통과(파일만 검사)")
        for e in errs:
            print(" -", e)
        sys.exit(1 if errs else 0)
    OUT.mkdir(parents=True, exist_ok=True)
    write_index()
    for d in DOCS:
        p = OUT / filename(d)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(render(d), encoding="utf-8")
    counts = {}
    for d in DOCS:
        counts[d["doc_type"]] = counts.get(d["doc_type"], 0) + 1
    print(f"문서 {len(DOCS)}개 생성 → {OUT}")
    print("종류별:", counts)
    write_busy_blocks()
    errs = check() + check_busy_blocks()
    if errs:
        print("검사 실패:")
        for e in errs:
            print(" -", e)
        sys.exit(1)
    print("검사 통과: 가상 표시·시행일·대상 반·요일·평가 문항 근거", len(REQUIRED_EVAL), "건 + 상담 바쁜 시간", len(busy_blocks()), "개 = 시간표 빈틈 일치")


if __name__ == "__main__":
    main()
