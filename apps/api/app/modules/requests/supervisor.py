"""선택 요청 유형을 보존하며 모델 분류 제안을 검증한다."""

import json
import os

from agents.llm import ModelError, OpenAIModel
from app.core.request_rules import classify

TOPICS = {"safety", "meal", "teacher", "belongings", "fee", "pickup_bus", "peer_conflict",
          "health_hygiene", "photo_record", "communication", "other"}
RISK_CATEGORIES = {"child_safety", "staff_attack", "legal_external", "privacy_leak"}
LEVEL = {"normal": 0, "uncertain": 1, "urgent": 2}


def classify_request(request_type, body, writer=None):
    if not os.getenv("LLM_MODEL_SUPERVISOR") and writer is None:
        return {}
    model = writer or OpenAIModel("SUPERVISOR")
    system = """요청을 분류해 JSON으로 topic_key, urgency, risk_level, risk_category를 제안한다.
화면의 요청 유형은 바꾸지 않는다. topic_key는 safety, meal, teacher, belongings, fee, pickup_bus,
peer_conflict, health_hygiene, photo_record, communication, other 중 하나다.
urgency는 normal/urgent, risk_level은 normal/uncertain/urgent, risk_category는
child_safety/staff_attack/legal_external/privacy_leak/null이다."""
    try:
        proposal = model.json(system, json.dumps({"request_type": request_type, "body": body}, ensure_ascii=False))
    except ModelError:
        return {}
    return proposal if isinstance(proposal, dict) else {}


def validate_proposal(request_type, body, proposal):
    base = classify(request_type, body)
    if not isinstance(proposal, dict):
        return base
    result = dict(base)
    if proposal.get("topic_key") in TOPICS:
        result["topic_key"] = proposal["topic_key"]
    if proposal.get("urgency") in ("normal", "urgent"):
        result["urgency"] = "urgent" if base["urgency"] == "urgent" else proposal["urgency"]
    if request_type == "complaint":
        level = proposal.get("risk_level")
        if level in LEVEL:
            result["risk_level"] = max((base["risk_level"], level), key=LEVEL.get)
        if result["risk_level"] == "urgent":
            result["urgency"] = "urgent"
        category = base.get("risk_category") or proposal.get("risk_category")
        if category not in RISK_CATEGORIES:
            category = None
        if result["risk_level"] == "urgent" and category is None:
            result["risk_level"] = "uncertain"
        result["risk_category"] = category
    return result
