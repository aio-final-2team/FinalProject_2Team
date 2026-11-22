"""모의 API의 데모 데이터(계약표 부록 A, API 설계 문서 부록 A).

출처 PR #262 roster_c4.json(가상): 별빛반 18명의 이름과 순서를 옮겼다.
출처 PR #269 guardian_requests.json(가상): 요청 20개와 해당 아이의 보호자를 옮겼다.

고정 UUID 규칙: 00000000-0000-4000-8000-0000000XXXXX
  0001 기관 · 01xx 반 · 02xx 교사 · 03xx 원장 · 04xx 학부모 · 05xx 아이 · 06xx 상담실
  07xx 요청 · 08xx 카드 · 09xx 상담 예약 · 0axx 알림장 입력 · 0bxx 문서 · 0cxx 알림장 · 0dxx 개인 규칙
로그인 비밀번호는 모의 API 전용 값이다. 실제 계정·원아 정보는 넣지 않는다.
"""

from datetime import datetime
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
VIDEO_BOOKING = demo_id("901")
VIDEO_REQUEST = demo_id("790")
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

# 출처 PR #269 guardian_requests.json(가상), develop 8d77964. 요청 원문·접수 시각을 유지해요.
GUARDIAN_REQUEST_DATA = [
    (1, 12, "mother", "medication",
     "점심 먹고 약 먹여 주세요. 투약의뢰서 가방에 넣었어요.", "2026-11-18T08:20:00+09:00"),
    (2, 12, "mother", "medication",
     "약은 오늘까지만 먹여 주세요. 감사합니다.", "2026-11-20T08:15:00+09:00"),
    (3, 6, "father", "medication",
     "어제 다친 무릎에 연고 한 번 발라 주세요. 가방 앞주머니에 있어요.", "2026-11-17T08:30:00+09:00"),
    (4, 15, "mother", "medication",
     "콧물약 점심 먹고 먹여 주세요.", "2026-11-18T08:40:00+09:00"),
    (5, 18, "father", "medication",
     "점심 먹고 시럽 2.5ml 먹여 주세요. 투약의뢰서 냈어요.", "2026-11-19T08:10:00+09:00"),
    (6, 1, "mother", "pickup",
     "오늘은 할머니가 4시에 데리러 가요.", "2026-11-16T08:25:00+09:00"),
    (7, 5, "mother", "pickup",
     "병원 예약이 있어서 2시에 일찍 데리러 갈게요.", "2026-11-17T08:05:00+09:00"),
    (8, 9, "father", "pickup",
     "오늘은 아빠 대신 이모가 데리러 가요. 이모 연락처는 앱에 적어 뒀어요.", "2026-11-18T08:35:00+09:00"),
    (9, 11, "mother", "pickup",
     "오늘은 차량 말고 엄마가 직접 데리러 가요.", "2026-11-19T08:20:00+09:00"),
    (10, 16, "mother", "pickup",
     "오늘 할머니가 5시에 데리러 가요.", "2026-11-20T08:30:00+09:00"),
    (11, 14, "mother", "pickup",
     "내일은 할머니가 데리러 가요.", "2026-11-19T08:10:00+09:00"),
    (12, 4, "father", "pickup",
     "오늘 3시에 일찍 데리러 가요.", "2026-11-18T08:15:00+09:00"),
    (13, 4, "father", "inquiry",
     "콧물이 조금 나요. 바깥놀이 때 잘 봐 주세요.", "2026-11-18T08:16:00+09:00"),
    (14, 7, "mother", "inquiry",
     "요즘 기침을 조금 해요. 낮잠 때 잘 봐 주세요.", "2026-11-16T08:40:00+09:00"),
    (15, 2, "mother", "inquiry",
     "어제 밥 잘 먹었나요?", "2026-11-17T08:30:00+09:00"),
    (16, 15, "father", "inquiry",
     "내일 준비물 있나요?", "2026-11-19T08:45:00+09:00"),
    (17, 11, "mother", "inquiry",
     "아침을 못 먹고 갔어요. 점심은 많이 먹었는지 알려 주세요.", "2026-11-18T08:05:00+09:00"),
    (18, 13, "mother", "inquiry",
     "지아랑 다퉜다고 들었는데 괜찮았나요?", "2026-11-17T08:50:00+09:00"),
    (19, 8, "mother", "inquiry",
     "이제 열은 안 나죠? 오늘 점심도 잘 먹었는지 궁금해요.", "2026-11-20T08:20:00+09:00"),
    (20, 10, "father", "inquiry",
     "요즘 친구랑 잘 지내나요?", "2026-11-19T08:35:00+09:00"),
]

# 한 아이당 44NN 계정 하나예요. C4-15는 GR-04(mother)·GR-16(father)가 달라
# 먼저 나온 mother를 유지해요. 두 요청의 본문·시각은 모두 그대로 보존해요.
GUARDIAN_RELATIONS = {}
for request_number, child_number, relation, request_type, body, created_at in GUARDIAN_REQUEST_DATA:
    child_id, guardian_id = demo_id(f"54{child_number:02d}"), demo_id(f"44{child_number:02d}")
    child = next(child for child in CHILDREN if child["id"] == child_id)
    if guardian_id not in child["guardian_ids"]:
        child["guardian_ids"].append(guardian_id)
        USERS.append({"id": guardian_id, "role": "parent", "login_id": f"parent-c4-{child_number:02d}",
                      "display_name": f"{child['display_name']} 보호자"})
        GUARDIAN_RELATIONS[(child_id, guardian_id)] = relation
    DEMO_NOTE_REQUESTS.append({
        "id": demo_id(f"72{request_number:02d}"), "child_id": child_id, "requester_id": guardian_id,
        "type": request_type, "body": body, "created_at": datetime.fromisoformat(created_at),
    })


DEMO_DOCUMENTS = [
    (MENU, "가상 식단표", "menu", "active", "점심: 카레라이스, 채소와 과일"),
    (NOTICE, "가상 행사 안내", "notice", "active", "행사는 별빛반과 햇님반이 함께 참여해요."),
    (OLD_NOTICE, "가상 행사 안내 옛 판", "notice", "superseded", "지난 행사 안내입니다."),
]

# [제안] T54 가상 사진. 반·원 글 두 개씩, 단색 PNG 다섯 장이에요.
PHOTO_SCOPES = {CHILD: "family", demo_id("503"): "class", demo_id("5401"): "org"}
FEED_POSTS = [
    {"id": demo_id("e01"), "lane": "class", "classroom_id": CLASS_STAR, "author_id": PARENT,
     "body": "함께 블록 놀이를 했어요."},
    {"id": demo_id("e02"), "lane": "class", "classroom_id": CLASS_STAR, "author_id": PARENT_OTHER,
     "body": "가상 소풍 사진을 나눠요."},
    {"id": demo_id("e03"), "lane": "org", "classroom_id": None, "author_id": TEACHER,
     "body": "우리 원 가상 행사예요."},
    {"id": demo_id("e04"), "lane": "org", "classroom_id": None, "author_id": PARENT_OTHER,
     "body": "가상 전시를 구경해요."},
]
FEED_PHOTOS = [
    (demo_id("f01"), demo_id("e01"), [demo_id("503")]),
    (demo_id("f02"), demo_id("e02"), [CHILD]),
    (demo_id("f03"), demo_id("e03"), [demo_id("5401")]),
    (demo_id("f04"), demo_id("e03"), [CHILD, demo_id("503")]),
    (demo_id("f05"), demo_id("e04"), []),
]
FEED_CREATED_AT = datetime.fromisoformat("2026-11-21T09:00:00+09:00")

# [제안][선택] T60. 플래그를 켠 데모에서만 두 가상 기관을 더해요.
NEIGHBORHOOD_ORGS = [
    {"id": demo_id("2"), "name": "가상 달빛어린이집", "region": "가상동", "classroom_id": demo_id("103"),
     "child_id": demo_id("504"), "parent_id": demo_id("403"), "login_id": "parent-n01"},
    {"id": demo_id("3"), "name": "가상 별빛어린이집", "region": "가상 별동", "classroom_id": demo_id("104"),
     "child_id": demo_id("505"), "parent_id": demo_id("404"), "login_id": "parent-x01"},
]


def video_period():
    """선택 기능 시연용 오늘 14:00~14:30 가상 예약이에요."""
    from datetime import timedelta
    from app.core.schedule import KST
    start = datetime.now(KST).replace(hour=14, minute=0, second=0, microsecond=0)
    return {"start": start, "end": start + timedelta(minutes=30)}


def feed_png():
    """실제 인물 대신 코드로 만든 2×2 단색 PNG예요."""
    import struct
    import zlib

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress((b"\x00" + b"\x70\xb0\x90" * 2) * 2)) + chunk(b"IEND", b""))
