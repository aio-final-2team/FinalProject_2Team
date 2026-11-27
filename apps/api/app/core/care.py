"""T46 초안의 확인 상태와 알림장 표시. 투약 수치·인계자 신원은 추측하지 않아요."""

from copy import deepcopy
import json
from uuid import uuid4

from agents.guardrails.sensitive import mask_sensitive
from app.core.errors import ApiError
from app.core.constants import CARE_REQUEST_TYPES, MEDICATION_FIELDS
from app.core.schedule import KST

RESULT_DONE = {"medication": "약 먹였어요", "pickup": "귀가했어요"}


def request_intent(req_type, intent):
    """감독 AI의 알림/부탁 분류(#408). 투약·귀가는 분류를 거치지 않고 늘 부탁이에요(지혜님 결정)."""
    return "ask" if req_type in CARE_REQUEST_TYPES else intent


def result_line(req_type, text, at):
    """완료 때 남기는 처리 결과 한 줄. 비우면 처리 시각·종류로 '13시에 약 먹였어요' 같은 기본 문장을 만들어요."""
    if (text or "").strip():
        return text.strip()
    at = at.astimezone(KST)
    return f"{at.hour}시{f' {at.minute}분' if at.minute else ''}에 {RESULT_DONE[req_type]}"


def note_result(line):
    """알림장 입력의 처리 결과. 선생님이 쓴 글이라 모델에 가기 전에 민감정보를 가려요."""
    return mask_sensitive(line) if line else None


def missed_request_check(request_type, request_id):
    return {"id": str(uuid4()), "item_key": request_type, "kind": "request_missed",
            "problem": "보호자 요청을 초안에 반영해 주세요", "sentence": None, "request_id": str(request_id)}


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
              "cancelled_by_parent": False, "rejection": None,
              "confirmed_at": None, "completed_at": None, "result_line": None,
              "missing_fields": [key for key in MEDICATION_FIELDS if not (fields.get(key) or "").strip()]
              if req_type == "medication" else []}
    for event in events:
        detail = event["detail"]
        if detail.get("care_message") or event["action"] == "care_updated":
            result["version"] += 1
            result["confirmed_at"] = None
            if event["action"] == "care_updated":
                result.update(fields)
        elif detail.get("care_decision") == "confirm":
            result.update(detail.get("pickup_snapshot", {}))
            result["confirmed_at"] = event["created_at"]
        elif detail.get("care_decision") == "complete":
            result["completed_at"] = event["created_at"]
            result["result_line"] = detail.get("result_line")
        elif detail.get("care_decision") == "reject":
            result["rejection"] = {"reason_code": "other", "reason_text": detail["reason_text"]}
        elif detail.get("cancelled_by_parent"):
            result["cancelled_by_parent"] = True
    return result


def check_decision(req_type, status, care, body):
    if req_type not in CARE_REQUEST_TYPES:
        raise ApiError(409, "INVALID_TRANSITION")
    # 요청 행을 잠근 뒤 검사해요. 새 보호자 글 뒤의 옛 확인·완료는 모두 거부해요.
    if body.version != care["version"]:
        raise ApiError(409, "CARD_VERSION_CONFLICT", current_version=care["version"])
    if body.decision == "reject":
        if status not in ("received", "assigned"):
            raise ApiError(409, "INVALID_TRANSITION")
        return "rejected"
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


def check_parent_change(req_type, status, care, version=None):
    if req_type not in CARE_REQUEST_TYPES or status not in ("received", "assigned"):
        raise ApiError(409, "INVALID_TRANSITION")
    if version is not None and version != care["version"]:
        raise ApiError(409, "CARD_VERSION_CONFLICT", current_version=care["version"])


def updated_detail(req_type, previous, body):
    changes = body.model_dump(exclude_unset=True, exclude={"version"}, mode="json")
    allowed = set(input_detail(req_type))
    invalid = changes.keys() - allowed
    if invalid:
        raise ApiError(422, "VALIDATION_FAILED", field=sorted(invalid)[0])
    # 등록 인계자를 바꾸면 이전 사람의 이름·관계를 새 사람에게 붙이지 않아요.
    if "pickup_guardian_id" in changes and changes["pickup_guardian_id"] != previous.get("pickup_guardian_id"):
        previous = {**previous, "pickup_name": None, "pickup_relation": None}
    return {**previous, **changes}, list(changes)


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
