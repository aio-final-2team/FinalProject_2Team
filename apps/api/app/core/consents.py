"""[제안] 역할별 필수 동의와 현재 약관 판을 함께 검사해요."""

from app.core.constants import CONSENT_VERSION
from app.core.errors import ApiError

LABELS = {
    "terms": "이용약관", "privacy": "개인정보 수집·이용",
    "ai_processing": "쓴 글이 AI 처리를 위해 국외 AI 사업자에게 전송됨",
    "child_info": "자녀 개인정보", "child_health": "자녀 건강·투약 정보", "child_face": "자녀 얼굴로 찾기",
}


def required_items(role):
    return list(LABELS) if role == "parent" else list(LABELS)[:3]


def validate(user, items, terms_version):
    required = required_items(user.role)
    if terms_version != CONSENT_VERSION:
        raise ApiError(409, "CONSENT_VERSION_MISMATCH", terms_version=CONSENT_VERSION)
    if set(items) - set(required):
        raise ApiError(422, "VALIDATION_FAILED", items=sorted(set(items) - set(required)))
    missing = [item for item in required if item not in items]
    if missing:
        raise ApiError(422, "CONSENT_INCOMPLETE", missing_items=missing)
    return required


def view(role, agreed):
    items = [{"item": item, "label": LABELS[item], "required": True, "agreed_at": agreed.get(item)}
             for item in required_items(role)]
    return {"terms_version": CONSENT_VERSION, "complete": all(i["agreed_at"] is not None for i in items),
            "items": items}


def complete(user):
    from app import backend
    return backend.consents.get(user)["complete"]


def require_complete(user):
    if not complete(user):
        raise ApiError(403, "CONSENT_REQUIRED")


def check_classroom(user, classroom_id, org_id):
    from app import backend
    if org_id != user.org_id:
        raise ApiError(404, "NOT_FOUND")
    if user.role == "parent" or (user.role == "teacher"
                                and classroom_id not in backend.users.classroom_ids_of(user.id)):
        raise ApiError(403, "FORBIDDEN_ROLE")


def child_view(child_id, display_name, guardians, completed):
    count = len(set(guardians) & completed)
    return {"child_id": child_id, "display_name": display_name, "guardians_total": len(guardians),
            "guardians_complete": count, "complete": count > 0}
