"""요청 분류의 선과 대역이에요. 평소 주제·위험 등급·권한 밖 여부는 감독 AI가 정해요(supervisor.py).

- 선: 아이 몸에 해가 간 명백한 표현(child_harm)은 AI가 뭐라 하든 긴급으로 올려요.
- 대역: classify·scope_kind는 감독 모델이 꺼져 있거나 실패했을 때, mock 백엔드(AI 없음)일 때만 써요.
"""

import re

# 위험 등급은 보호자 글을 받는 세 유형에 붙여요. 투약·귀가 같은 돌봄 요청은 위험 등급이 없어요.
RISK_TYPES = ("inquiry", "consultation", "complaint")
# 담임 재분류는 회신 카드가 있는 문의·민원만 받아요. 상담은 시간 확정 흐름이라 대상이 아니에요.
RECLASSIFY_TYPES = ("inquiry", "complaint")
# 선: 아이 몸에 해가 간 일이 분명한 표현만 둬요. 다침·학대·때림·폭행·꼬집음·밀침·멍·피, 사람에게 맞은 일이에요.
# 낱말 경계를 맞춰 오탐을 줄여요. '맞'은 사람(한테·에게) 바로 뒤의 맞았·맞아서·맞고 왔·맞은만 봐서 '엄마한테 맞춰'·
# '주사 맞았어요'가 안 걸려요. '멍때리'·'멍멍이', '꼬집어 말하면'도 안 걸려요.
_CHILD_HARM = re.compile(
    r"다쳤|다침|학대|폭행|밀쳤|(?<!멍)(?<!멍 )때(?:렸|리|린)|꼬집(?!어\s?말)"
    r"|(?<!멍)멍이?\s?(?:들|있)|피가\s?(?:나|났|흘)|피를\s?흘|피\s?났"
    r"|(?:한테|에게)서?\s*(?:맞았|맞아서|맞고\s?왔|맞은)"
)
# 대역: 모델이 없을 때만 선에 더해 이 구로 긴급을 봐요. 낱말 하나('안전'·'신고'·'개인정보')로는 올리지 않아요.
_FALLBACK_URGENT = {
    "child_safety": ("안전을 확인", "안전이 걱정", "안전하지 않"),
    "legal_external": ("고소", "신고하겠", "신고할 거", "신고할게", "변호사", "언론", "경찰에 알", "경찰에 신고", "소송"),
    "privacy_leak": ("유출",),
    "staff_attack": ("가만두지", "협박"),
}
_TOPIC_WORDS = {
    "pickup_bus": ("버스", "등원", "하원"), "meal": ("급식", "밥", "식단", "간식"),
    "safety": ("안전", "다쳤", "다침"), "fee": ("원비", "비용", "환불"),
    "belongings": ("소지품", "가방", "옷", "분실"), "peer_conflict": ("친구", "다툼", "다퉜", "싸움"),
    "health_hygiene": ("열", "아파", "위생", "감기", "수족구"), "photo_record": ("사진", "앨범"),
    "communication": ("연락", "답장", "알림장"), "teacher": ("선생님",),
}
_OUR_CHILD = r"우리\s*(?:아이|애)|저희\s*아이"


def child_harm(body):
    return bool(_CHILD_HARM.search(body))


def classify(request_type, body):
    """대역: 주제는 순서상 첫 낱말로, 위험은 선과 대역 구로 정해요. 판단 필요는 AI만 정해요."""
    topic = "health_hygiene" if "수족구" in body else next((
        k for k, words in _TOPIC_WORDS.items() if any(w in body for w in words)), "other")
    result = {"topic_key": topic, "urgency": "normal"}
    if request_type in RISK_TYPES:
        category = "child_safety" if child_harm(body) else next((
            k for k, words in _FALLBACK_URGENT.items() if any(w in body for w in words)), None)
        result.update(risk_level="urgent" if category else "normal", risk_category=category)
        if category:
            result["urgency"] = "urgent"
    return result


def _scope_regex(body):
    other = r"다른\s*(?:엄마|아빠|학부모|부모|가정|집|아이|반)|남의|친구\s*(?:엄마|아빠)|옆\s*반"
    if re.search(other, body) and re.search(r"전화번호|연락처|휴대폰\s*번호|핸드폰\s*번호|주소", body):
        return "others_privacy"
    if re.search(r"상담", body) and re.search(r"옆\s*반\s*(?:[^\s]*\s*)?선생님|다른\s*선생님|담임\s*아닌\s*선생님", body):
        return "other_teacher"
    if re.search(r"결제\s*(?:해|할|하고|부탁)|카드로\s*결제", body):
        return "payment"
    record_owner = r"다른\s*(?:집|가정|아이)|남의|친구\s*(?:엄마|아빠)"
    if (not re.search(_OUR_CHILD, body)
            and re.search(record_owner, body)
            and re.search(r"민원|요청|알림장|기록", body)
            and re.search(r"보여|알려|볼\s*수", body)):
        return "other_family"
    return None


def scope_kind(body, topic_key):
    """대역: 분명한 권한 밖 요청만 정규식으로 잡아요. 우리 아이 일·안전·건강이 섞이면 사람이 보게 None이에요."""
    kind = _scope_regex(body)
    # '친구 엄마 전화번호'와 다른 가정의 민원은 '친구' 때문에 또래 주제로 잡힐 수 있어요. 두 종류는 안전·건강만 사람이 봐요.
    human_topics = ("safety", "health_hygiene") if kind in ("others_privacy", "other_family") else ("peer_conflict", "safety", "health_hygiene")
    if kind is None or topic_key in human_topics or re.search(_OUR_CHILD, body):
        return None
    return kind


def direct_notice_kind(request_type, body, fields):
    """권한 밖 고정 안내를 바로 남길 종류예요. 권한 밖인지는 감독 AI(모델이 없으면 scope_kind)가 정해요."""
    from app.core.constants import OUT_OF_SCOPE_MESSAGES

    if fields.get("risk_level") in ("urgent", "uncertain"):
        return None
    kind = fields.get("out_of_scope_kind")
    if kind in OUT_OF_SCOPE_MESSAGES and (request_type == "inquiry"
                                         or (request_type == "consultation" and kind == "other_teacher")):
        return kind
    return None
