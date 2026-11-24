"""선택 요청 유형을 보존하며 모델 분류 제안을 검증한다."""

import json
import os
import re
from pathlib import Path

from agents.llm import ModelError, OpenAIModel
from agents.guardrails.sensitive import mask_sensitive
from app.core.request_rules import RISK_TYPES, classify

TOPICS = {"safety", "meal", "teacher", "belongings", "fee", "pickup_bus", "peer_conflict",
          "health_hygiene", "photo_record", "communication", "other"}
RISK_CATEGORIES = {"child_safety", "staff_attack", "legal_external", "privacy_leak"}
LEVEL = {"normal": 0, "uncertain": 1, "urgent": 2}
PROMPTS = Path(__file__).resolve().parents[5] / "agents" / "prompts"
OUT_OF_SCOPE_KINDS = {"payment", "others_privacy", "other_family", "other_teacher"}


def _scope_kind(body):
    """분명한 권한 밖 요청만 코드로 잡고, 애매하면 모델 판단에 맡긴다."""
    other = r"다른\s*(?:엄마|아빠|학부모|부모|가정|집|아이|반)|남의|친구\s*(?:엄마|아빠)|옆\s*반"
    if re.search(other, body) and re.search(r"전화번호|연락처|휴대폰\s*번호|핸드폰\s*번호|주소", body):
        return "others_privacy"
    if re.search(r"상담", body) and re.search(r"옆\s*반\s*(?:[^\s]*\s*)?선생님|다른\s*선생님|담임\s*아닌\s*선생님", body):
        return "other_teacher"
    if re.search(r"결제\s*(?:해|할|하고|부탁)|카드로\s*결제", body):
        return "payment"
    if re.search(other, body) and re.search(r"민원|요청|알림장|기록|정보|내용|보여|알려", body):
        return "other_family"
    return None


def _code_classification(request_type, body):
    result = classify(request_type, body)
    # 등원이라는 낱말이 있어도 수족구 문의의 주제는 건강이다.
    if "수족구" in body:
        result["topic_key"] = "health_hygiene"
    return result


def classify_request(request_type, body, writer=None):
    if not os.getenv("LLM_MODEL_SUPERVISOR") and writer is None:
        return {}
    model = writer or OpenAIModel("SUPERVISOR")
    system = ((PROMPTS / "common.md").read_text(encoding="utf-8") + "\n" +
              (PROMPTS / "supervisor.md").read_text(encoding="utf-8") +
              "\n분류 결과를 JSON으로 제안한다: topic_key, urgency, risk_level, risk_category, out_of_scope_kind. "
              "화면의 요청 유형은 바꾸지 않는다.")
    try:
        proposal = model.json(system, json.dumps({"request_type": request_type, "body": mask_sensitive(body),
                                                   "untrusted_data_fields": ["body"]}, ensure_ascii=False))
    except ModelError:
        return {}
    return proposal if isinstance(proposal, dict) else {}


def validate_proposal(request_type, body, proposal):
    base = _code_classification(request_type, body)
    base["out_of_scope_kind"] = _scope_kind(body)
    if not isinstance(proposal, dict):
        if base.get("risk_level") in ("urgent", "uncertain"):
            base["out_of_scope_kind"] = None
        return base
    result = dict(base)
    if proposal.get("topic_key") in TOPICS and (base["topic_key"] == "other" or proposal["topic_key"] == base["topic_key"]):
        result["topic_key"] = proposal["topic_key"]
    if proposal.get("urgency") in ("normal", "urgent"):
        result["urgency"] = "urgent" if base["urgency"] == "urgent" else proposal["urgency"]
    if request_type in RISK_TYPES:
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
    suggested = proposal.get("out_of_scope_kind")
    if result["out_of_scope_kind"] is None and suggested in OUT_OF_SCOPE_KINDS:
        result["out_of_scope_kind"] = suggested
    if result.get("risk_level") in ("urgent", "uncertain"):
        result["out_of_scope_kind"] = None
    return result


def topic_conflict(request_type, body, proposal):
    """코드가 특정한 주제를 고른 경우, 다른 모델 제안을 이력에 표시한다."""
    base_topic = _code_classification(request_type, body)["topic_key"]
    return (isinstance(proposal, dict) and base_topic != "other"
            and proposal.get("topic_key") in TOPICS and proposal["topic_key"] != base_topic)
