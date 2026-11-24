"""시연용 요청 분류 규칙. 실제 감독 AI를 붙이기 전 두 백엔드가 함께 써요."""

# 위험 등급은 보호자 글을 받는 세 유형에 붙여요. 투약·귀가 같은 돌봄 요청은 위험 등급이 없어요.
RISK_TYPES = ("inquiry", "consultation", "complaint")
# 담임 재분류는 회신 카드가 있는 문의·민원만 받아요. 상담은 시간 확정 흐름이라 대상이 아니에요.
RECLASSIFY_TYPES = ("inquiry", "complaint")
# 문의에도 붙으므로 '안전 수칙'·'결석 신고'·'개인정보 동의서' 같은 평범한 글이 걸리지 않게 짧은 구로 봐요.
_URGENT_WORDS = {
    "child_safety": ("다쳤", "다침", "학대", "때렸", "안전을 확인", "안전이 걱정", "안전하지 않"),
    "legal_external": ("고소", "신고하겠", "신고할 거", "신고할게", "변호사", "언론", "경찰에", "소송"),
    "privacy_leak": ("유출",),
    "staff_attack": ("가만두지", "협박"),
}
# 민원은 예전처럼 낱말 하나로도 봐요. '구청에 신고합니다'·'안전벨트를 안 채워 줬어요' 같은 민원을 놓치지 않게요.
_COMPLAINT_WORDS = {"child_safety": ("안전",), "legal_external": ("신고",), "privacy_leak": ("개인정보",)}
_TOPIC_WORDS = {
    "pickup_bus": ("버스", "등원", "하원"), "meal": ("급식", "밥", "식단", "간식"),
    "safety": ("안전", "다쳤", "다침"), "fee": ("원비", "비용", "환불"),
    "belongings": ("소지품", "가방", "옷", "분실"), "peer_conflict": ("친구", "다툼", "싸움"),
    "health_hygiene": ("열", "아파", "위생", "감기"), "photo_record": ("사진", "앨범"),
    "communication": ("연락", "답장", "알림장"), "teacher": ("선생님",),
}


def classify(request_type, body):
    result = {"topic_key": next((k for k, words in _TOPIC_WORDS.items()
                                 if any(w in body for w in words)), "other"), "urgency": "normal"}
    if request_type in RISK_TYPES:
        extra = _COMPLAINT_WORDS if request_type == "complaint" else {}
        category = next((k for k, words in _URGENT_WORDS.items()
                         if any(w in body for w in (*words, *extra.get(k, ())))), None)
        result.update(risk_level="uncertain" if "판단 필요" in body else "urgent" if category else "normal",
                      risk_category=category)
        if category:
            result["urgency"] = "urgent"
    return result
