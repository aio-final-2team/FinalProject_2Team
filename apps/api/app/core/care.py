"""T46 초안의 확인 상태와 알림장 표시. 투약 수치·인계자 신원은 추측하지 않아요."""

from copy import deepcopy

from app.core.errors import ApiError
from app.core.constants import CARE_REQUEST_TYPES


def care_view(events):
    created = next((e for e in events if e["action"] == "created" and e["to_status"] == "received"), None)
    confirmed = next((e for e in events if e["detail"].get("care_decision") == "confirm"), None)
    completed = next((e for e in events if e["detail"].get("care_decision") == "complete"), None)
    return {"pickup_guardian_id": created["detail"].get("pickup_guardian_id") if created else None,
            "confirmed_at": confirmed["created_at"] if confirmed else None,
            "completed_at": completed["created_at"] if completed else None}


def check_decision(req_type, status, care, body):
    if req_type not in CARE_REQUEST_TYPES:
        raise ApiError(409, "INVALID_TRANSITION")
    if req_type == "pickup":
        if (body.pickup_guardian_id is None or care["pickup_guardian_id"] is None
                or str(body.pickup_guardian_id) != str(care["pickup_guardian_id"])):
            raise ApiError(422, "VALIDATION_FAILED", field="pickup_guardian_id")
    elif body.pickup_guardian_id is not None:
        raise ApiError(422, "VALIDATION_FAILED", field="pickup_guardian_id")
    target = "assigned" if body.decision == "confirm" else "completed"
    # 같은 단계 재전송은 이력·알림을 늘리지 않아요. 완료 뒤 확인으로 돌아갈 수는 없어요.
    if status == target and care["confirmed_at"] is not None:
        return None
    expected = "received" if body.decision == "confirm" else "assigned"
    if status != expected or (body.decision == "complete" and care["confirmed_at"] is None):
        raise ApiError(409, "INVALID_TRANSITION")
    return target


def note_content(content, requests):
    result = deepcopy(content)
    for line in result["items"]:
        line.pop("request_status", None)
        source = line.get("source", {})
        req = requests.get(str(source.get("request_id")))
        if (line["key"] in CARE_REQUEST_TYPES and source.get("type") == "request"
                and req and req["type"] == line["key"]):
            line["request_status"] = req["status"]
    return result
