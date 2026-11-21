"""시연용 요청 분류 규칙. 실제 감독 AI를 붙이기 전 두 백엔드가 함께 써요."""

_URGENT_WORDS = {
    "child_safety": ("다쳤", "다침", "학대", "때렸", "안전"),
    "legal_external": ("고소", "신고", "변호사", "언론"),
    "privacy_leak": ("개인정보", "사진 유출"),
    "staff_attack": ("가만두지", "협박"),
}
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
    if request_type == "complaint":
        category = next((k for k, words in _URGENT_WORDS.items() if any(w in body for w in words)), None)
        result.update(risk_level="uncertain" if "판단 필요" in body else "urgent" if category else "normal",
                      risk_category=category)
        if category:
            result["urgency"] = "urgent"
    return result
