"""요청 상태의 화면 표시 이름(T04 2장). 서버가 status_label로 붙여 준다(계약표 2.1·2.2)."""

PARENT_LABELS = {
    "received": "접수됨",
    "classified": "접수됨",
    "needs_info": "정보가 더 필요해요",
    "assigned": "선생님께 전달됨",
    "awaiting_review": "선생님 확인 중",
    "escalated": "원장님 확인 중",
    "on_hold": "확인이 늦어지고 있어요",
    "approved": "선생님 확인 완료",
    "sent_or_booked": "답변 도착",
    "completed": "완료",
    "rejected": "처리할 수 없는 요청이에요",
}

STAFF_LABELS = {
    "received": "접수",
    "classified": "미배정",
    "needs_info": "학부모 응답 대기",
    "assigned": "준비 중",
    "awaiting_review": "확인 필요",
    "escalated": "원장 보고",
    "on_hold": "보류",
    "approved": "승인됨",
    "sent_or_booked": "발송됨",
    "completed": "완료",
    "rejected": "반려",
}


def parent_label(status: str, request_type: str) -> str:
    """상담은 같은 상태라도 표시가 다르다(needs_info = 시간 고르기, sent_or_booked = 예약 확정)."""
    if request_type == "consultation":
        if status == "needs_info":
            return "시간을 골라 주세요"
        if status == "sent_or_booked":
            return "예약 확정"
    return PARENT_LABELS[status]


def staff_label(status: str, request_type: str) -> str:
    if request_type == "consultation" and status == "sent_or_booked":
        return "예약됨"
    return STAFF_LABELS[status]
