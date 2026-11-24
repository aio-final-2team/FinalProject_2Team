"""T46 초안의 확인 상태와 알림장 표시. 투약 수치·인계자 신원은 추측하지 않아요."""

from copy import deepcopy
import json

from app.core.errors import ApiError
from app.core.constants import CARE_REQUEST_TYPES, MEDICATION_FIELDS


def unregistered_pickup_key(request_id, snapshot):
    identity = json.dumps([snapshot.get("pickup_name"), snapshot.get("pickup_relation")],
                          ensure_ascii=False, separators=(",", ":"))
    return f"unregistered_pickup:{request_id}:{identity}"


def input_detail(req_type, *, pickup_guardian_id=None, pickup_name=None, pickup_relation=None,
                 medication_name=None, medication_dose=None, medication_time=None):
    if req_type == "pickup":
        return {"pickup_guardian_id": str(pickup_guardian_id) if pickup_guardian_id else None,
                "pickup_name": pickup_name, "pickup_relation": pickup_relation}
    if req_type == "medication":
        return dict(zip(MEDICATION_FIELDS, (medication_name, medication_dose, medication_time), strict=True))
    return {}


def care_view(events, req_type, care_detail):
    fields = input_detail(req_type, **{k: care_detail.get(k) for k in (
        "pickup_guardian_id", "pickup_name", "pickup_relation", *MEDICATION_FIELDS)})
    result = {**fields, "version": 1, "unregistered_pickup": req_type == "pickup" and not fields.get("pickup_guardian_id"),
              "confirmed_at": None, "completed_at": None,
              "missing_fields": [key for key in MEDICATION_FIELDS if not (fields.get(key) or "").strip()]
              if req_type == "medication" else []}
    for event in events:
        detail = event["detail"]
        if detail.get("care_message"):
            result["version"] += 1
            result["confirmed_at"] = None
        elif detail.get("care_decision") == "confirm":
            result.update(detail.get("pickup_snapshot", {}))
            result["confirmed_at"] = event["created_at"]
        elif detail.get("care_decision") == "complete":
            result["completed_at"] = event["created_at"]
    return result


def check_decision(req_type, status, care, body):
    if req_type not in CARE_REQUEST_TYPES:
        raise ApiError(409, "INVALID_TRANSITION")
    # 요청 행을 잠근 뒤 검사해요. 새 보호자 글 뒤의 옛 확인·완료는 모두 거부해요.
    if body.version != care["version"]:
        raise ApiError(409, "CARD_VERSION_CONFLICT", current_version=care["version"])
    expected_guardian = care.get("pickup_guardian_id")
    if (str(body.pickup_guardian_id) if body.pickup_guardian_id else None) != expected_guardian:
        raise ApiError(422, "VALIDATION_FAILED", field="pickup_guardian_id")
    target = "assigned" if body.decision == "confirm" else "completed"
    # 같은 입력 판의 같은 단계 재전송은 이력·알림을 늘리지 않아요.
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
