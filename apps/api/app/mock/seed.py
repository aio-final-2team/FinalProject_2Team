"""모의 API의 데모 데이터(계약표 부록 A, API 설계 문서 부록 A).

출처 PR #262 roster_c4.json(가상): 별빛반 18명의 이름과 순서를 옮겼다.

고정 UUID 규칙: 00000000-0000-4000-8000-0000000XXXXX
  0001 기관 · 01xx 반 · 02xx 교사 · 03xx 원장 · 04xx 학부모 · 05xx 아이 · 06xx 상담실
  07xx 요청 · 08xx 카드 · 09xx 상담 예약 · 0axx 알림장 입력 · 0bxx 문서 · 0cxx 알림장 · 0dxx 개인 규칙
로그인 비밀번호는 모의 API 전용 값이다. 실제 계정·원아 정보는 넣지 않는다.
"""

from uuid import UUID


def demo_id(suffix: str) -> UUID:
    return UUID("00000000-0000-4000-8000-" + suffix.rjust(12, "0"))


DEMO_PASSWORD = "demo1234"

ORG = demo_id("1")                       # KG-DEMO-01 가상 햇살유치원
CLASS_STAR = demo_id("101")              # CL-DEMO-01 만 4세 별빛반
CLASS_SUN = demo_id("102")               # CL-DEMO-02 만 5세 햇님반
TEACHER = demo_id("201")                 # T-DEMO-01 우리 반 담임
TEACHER_OTHER = demo_id("202")           # T-DEMO-02 다른 반 교사
DIRECTOR = demo_id("301")                # D-DEMO-01 원장
PARENT = demo_id("401")                  # P-DEMO-01 우리 아이 학부모
PARENT_OTHER = demo_id("402")            # P-DEMO-02 다른 아이 학부모
CHILD = demo_id("501")                   # C-DEMO-01 우리 아이
CHILD_OTHER = demo_id("502")             # C-DEMO-02 다른 아이
ROOM = demo_id("601")                    # RM-DEMO-01 상담실

CLASSROOMS = [
    {"id": CLASS_STAR, "name": "만 4세 별빛반"},
    {"id": CLASS_SUN, "name": "만 5세 햇님반"},
]

USERS = [
    {"id": TEACHER, "role": "teacher", "login_id": "teacher01", "display_name": "별빛반 선생님"},
    {"id": TEACHER_OTHER, "role": "teacher", "login_id": "teacher02", "display_name": "햇님반 선생님"},
    {"id": DIRECTOR, "role": "director", "login_id": "director01", "display_name": "원장님"},
    {"id": PARENT, "role": "parent", "login_id": "parent01", "display_name": "하늘이 보호자"},
    {"id": PARENT_OTHER, "role": "parent", "login_id": "parent02", "display_name": "바다 보호자"},
]

# 담임 배정(classroom_staff). valid_from·valid_to가 비면 기간 제한 없음
CLASSROOM_STAFF = [
    {"classroom_id": CLASS_STAR, "user_id": TEACHER, "valid_from": None, "valid_to": None},
    {"classroom_id": CLASS_SUN, "user_id": TEACHER_OTHER, "valid_from": None, "valid_to": None},
]

CHILDREN = [
    {"id": CHILD, "classroom_id": CLASS_STAR, "display_name": "하늘", "guardian_ids": [PARENT]},
    {"id": CHILD_OTHER, "classroom_id": CLASS_SUN, "display_name": "바다", "guardian_ids": [PARENT_OTHER]},
]

ROOMS = [{"id": ROOM, "name": "상담실"}]

REQUEST_CONSULT = demo_id("701")
REQUEST_COMPLAINT = demo_id("702")
CARD_CONSULT = demo_id("801")
CARD_COMPLAINT = demo_id("802")
MENU = demo_id("b01")
NOTICE = demo_id("b02")
OLD_NOTICE = demo_id("b03")
RULE = demo_id("d01")
REQUEST_COUGH = demo_id("708")
REQUEST_PICKUP = demo_id("70a")

# 같은 반 두 아이의 일괄 발송과 학부모별 조회 범위를 함께 시연한다.
CHILDREN.append({"id": demo_id("503"), "classroom_id": CLASS_STAR, "display_name": "노을", "guardian_ids": [PARENT_OTHER]})

for number, name in enumerate(("가온", "나래", "다온", "라온", "마루", "별하", "새봄", "아라", "여름",
                               "윤슬", "이든", "지아", "지안", "채온", "하람", "한결", "해든", "로아"), start=1):
    CHILDREN.append({"id": demo_id(f"54{number:02d}"), "classroom_id": CLASS_STAR,
                     "display_name": name, "guardian_ids": []})

DEMO_REQUESTS = [
    ("701", "consultation", "아이 친구 관계 상담", "needs_info"),
    ("702", "complaint", "등원 버스가 늦었어요", "awaiting_review"),
    ("703", "complaint", "아이 안전을 확인해 주세요", "escalated"),
    ("704", "complaint", "급식 관련 판단 필요 민원", "escalated"),
    ("705", "complaint", "원비 설명을 부탁드려요", "on_hold"),
    ("706", "inquiry", "지난 행사 안내를 확인했어요", "completed"),
    ("707", "inquiry", "새 행사 일정이 궁금해요", "classified"),
]

# 알림장에 보호자 요청을 반영하거나 누락 확인을 띄우는 가상 사례 두 개예요.
DEMO_NOTE_REQUESTS = [
    {"id": REQUEST_COUGH, "child_id": CHILD, "requester_id": PARENT,
     "type": "inquiry", "body": "기침해요"},
    {"id": REQUEST_PICKUP, "child_id": demo_id("503"), "requester_id": PARENT_OTHER,
     "type": "pickup", "body": "오늘 할머니가 데리러 가요"},
]

DEMO_DOCUMENTS = [
    (MENU, "가상 식단표", "menu", "active", "점심: 카레라이스, 채소와 과일"),
    (NOTICE, "가상 행사 안내", "notice", "active", "행사는 별빛반과 햇님반이 함께 참여해요."),
    (OLD_NOTICE, "가상 행사 안내 옛 판", "notice", "superseded", "지난 행사 안내입니다."),
]
