"""모의·DB 백엔드가 함께 쓰는 알림 문구와 요청 유형이에요."""

NOTIFICATION_TITLES = {
    "needs_info": "정보가 더 필요해요", "new_card": "새 카드가 왔어요",
    "urgent_complaint": "긴급 민원", "uncertain_complaint": "AI 판단 불확실 민원",
    "director_report": "원장 보고 카드", "on_hold": "확인이 늦어지고 있어요",
    "sent_or_booked": "답변 도착", "parent_confirmed": "학부모가 확인했어요 · 처리 완료를 눌러 주세요",
    "completed": "처리 완료", "rejected": "처리할 수 없는 요청이에요", "note_sent": "오늘 알림장",
    "slot_hold_expired": "잡아 둔 시간이 풀렸어요", "hold_resumed": "보류 카드가 재개됐어요",
    "care_requested": "투약·귀가 요청이 왔어요", "care_confirmed": "선생님이 요청을 확인했어요",
    "consultation_ending": "상담 종료가 가까워요", "consultation_delayed": "상담 대체 시간을 확인해 주세요",
}
CARE_REQUEST_TYPES = ("medication", "pickup")
MEDICATION_FIELDS = ("medication_name", "medication_dose", "medication_time")
UNREGISTERED_PICKUP_CHECK = "미등록 인계자 확인"
CARE_MESSAGE_NOTICE = "보호자가 내용을 추가했어요. 다시 확인해 주세요."
REJECTION_RULE_THRESHOLD = 3

# 자유 글에서 시간·선호를 추측하지 않는 기억 대역이에요. 구체적인 조건 추출은 기억 AI가 맡아요.
REJECTION_RULE_TEXTS = {
    "wrong_fact": "담임이 지적한 사실을 확인한 뒤 초안을 제안해 주세요.",
    "tone": "담임이 남긴 말투 관련 거절 이유를 확인해 초안을 제안해 주세요.",
    "missing_info": "담임이 지적한 정보와 근거를 확인한 뒤 초안을 제안해 주세요.",
    "privacy": "개인정보 관련 거절 이유를 확인한 뒤 초안을 제안해 주세요.",
    "policy": "담임이 지적한 원 방침을 확인한 뒤 초안을 제안해 주세요.",
    "slot_unavailable": "담임이 남긴 상담 시간 거절 이유를 확인해 후보를 제안해 주세요.",
    "room_unavailable": "담임이 남긴 상담실 거절 이유를 확인해 후보를 제안해 주세요.",
}

# [제안] T54 사진 업로드 제한이에요.
MAX_PHOTO_BYTES = 5 * 1024 * 1024
MAX_DOCUMENT_BYTES = 2 * 1024 * 1024
MAX_PHOTOS = 10
MAX_POST_BYTES = MAX_PHOTOS * MAX_PHOTO_BYTES + 1024 * 1024
