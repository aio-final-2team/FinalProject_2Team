"""모의·DB 백엔드가 함께 쓰는 알림 문구와 요청 유형이에요."""

from app.core.schedule import KST

CONSENT_VERSION = "2026-11-24"

NOTIFICATION_TITLES = {
    "needs_info": "정보가 더 필요해요", "new_card": "새 카드가 왔어요",
    "urgent_complaint": "긴급 민원", "uncertain_complaint": "AI 판단 불확실 민원",
    "director_report": "원장 보고 카드", "on_hold": "확인이 늦어지고 있어요",
    "sent_or_booked": "답변 도착", "parent_confirmed": "학부모가 확인했어요 · 처리 완료를 눌러 주세요",
    "completed": "처리 완료", "rejected": "처리할 수 없는 요청이에요", "note_sent": "오늘 알림장",
    "note_corrected": "알림장이 고쳐졌어요",
    "slot_hold_expired": "잡아 둔 시간이 풀렸어요", "hold_resumed": "보류 카드가 재개됐어요",
    "care_requested": "투약·귀가 요청이 왔어요", "care_confirmed": "선생님이 요청을 확인했어요",
    "parent_message": "학부모가 글을 더 남겼어요",
    "care_rejected": "투약·귀가 요청이 반려됐어요", "cancelled": "학부모가 요청을 취소했어요",
    "consultation_booked": "상담 예약 확정", "reassigned": "요청이 배정됐어요",
    "consultation_ending": "상담 종료가 가까워요", "consultation_delayed": "상담 대체 시간을 확인해 주세요",
}
# 위험 알림 kind는 계약이라 이름에 complaint가 남아 있어요. 사람이 보는 제목만 요청 유형에 맞춰요.
RISK_NOTICE_TYPE_NAMES = {"inquiry": "문의", "consultation": "상담", "complaint": "민원"}
REASSIGN_AFTER_INSTRUCTION = "지시를 남겼어요. 회신 카드를 담당 선생님에게 재배정해 주세요."


def notification_title(kind, request_type=None):
    title = NOTIFICATION_TITLES[kind]
    if kind in ("urgent_complaint", "uncertain_complaint") and request_type in RISK_NOTICE_TYPE_NAMES:
        return title.replace("민원", RISK_NOTICE_TYPE_NAMES[request_type])
    return title


def consultation_booking_body(start, end):
    return f"{start.astimezone(KST):%Y-%m-%d %H:%M}~{end.astimezone(KST):%H:%M}"


REJECTION_REASON_LABELS = {
    "wrong_fact": "사실이 틀림", "tone": "말투", "missing_info": "근거·정보 부족",
    "privacy": "개인정보", "policy": "원 방침과 다름", "slot_unavailable": "상담 시간 안 됨",
    "room_unavailable": "상담실 없음", "other": "기타",
}


def rejection_body(reason_code, reason_text):
    label = REJECTION_REASON_LABELS.get(reason_code, "기타")
    return f"{label} · {reason_text}" if reason_text else label


OUT_OF_SCOPE_MESSAGES = {
    "payment": "유치온에서는 원비 결제를 하지 않아요. 원비는 원에서 안내한 기존 방법으로 문의해 주세요.",
    "others_privacy": "다른 가정의 연락처 같은 개인정보는 알려 드릴 수 없어요.",
    "other_family": "다른 가정의 요청이나 내용은 볼 수 없어요. 우리 아이 일이라면 다시 적어 주세요.",
    "other_teacher": "상담은 담임 선생님과 잡을 수 있어요.",
}


CARE_REQUEST_TYPES = ("medication", "pickup")
NOTE_REQUEST_TYPES = (*CARE_REQUEST_TYPES, "inquiry")
LATE_NOTE_REQUEST_NOTICE = "초안 뒤에 보호자 요청이 왔어요. 아이 알림장을 확인해 주세요."
MEDICATION_FIELDS = ("medication_name", "medication_dose", "medication_time")
UNREGISTERED_PICKUP_CHECK = "미등록 인계자 확인"
CARE_MESSAGE_NOTICE = "보호자가 내용을 추가했어요. 다시 확인해 주세요."
CARE_UPDATED_NOTICE = "보호자가 입력을 수정했어요. 다시 확인해 주세요."
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
