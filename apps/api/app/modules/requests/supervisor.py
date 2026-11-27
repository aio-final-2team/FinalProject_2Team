"""선택 요청 유형을 보존하며 감독 AI의 분류를 검증한다. 판단은 AI가, 코드는 값이 계약 목록 안인지와 선만 본다."""

import json
import os
from pathlib import Path

import agents.llm
from agents.llm import ModelError, OpenAIModel
from agents.guardrails.sensitive import mask_sensitive
from app.core.request_rules import RISK_TYPES, child_harm, classify, scope_kind

TOPICS = {"safety", "meal", "teacher", "belongings", "fee", "pickup_bus", "peer_conflict",
          "health_hygiene", "photo_record", "communication", "other"}
RISK_CATEGORIES = {"child_safety", "staff_attack", "legal_external", "privacy_leak"}
LEVEL = {"normal": 0, "uncertain": 1, "urgent": 2}
PROMPTS = Path(agents.llm.__file__).resolve().parent / "prompts"
OUT_OF_SCOPE_KINDS = {"payment", "others_privacy", "other_family", "other_teacher"}
INTENTS = {"notice", "ask"}
RISK_REASON_MAX = 80  # 카드에 한 줄로 보이는 판단 필요 이유


def classify_request(request_type, body, writer=None):
    if not os.getenv("LLM_MODEL_SUPERVISOR") and writer is None:
        return {}
    model = writer or OpenAIModel("SUPERVISOR")
    system = ((PROMPTS / "common.md").read_text(encoding="utf-8") + "\n" +
              (PROMPTS / "supervisor.md").read_text(encoding="utf-8") +
              "\n분류 결과를 JSON으로 제안한다: topic_key, urgency, risk_level, risk_category, risk_reason, "
              "out_of_scope_kind, intent. "
              "intent는 inquiry에서만 notice 또는 ask로 판단하고, 애매하거나 알림과 부탁이 섞이면 ask로 둔다. "
              "그 밖의 요청 유형 intent는 ask다. "
              "화면의 요청 유형은 바꾸지 않는다.")
    try:
        proposal = model.json(system, json.dumps({"request_type": request_type, "body": mask_sensitive(body),
                                                   "untrusted_data_fields": ["body"]}, ensure_ascii=False))
    except ModelError:
        return {}
    return proposal if isinstance(proposal, dict) else {}


def validate_proposal(request_type, body, proposal):
    """AI 값이 계약 목록 안이면 그대로 쓴다. 빠졌거나 목록 밖인 칸만 낱말 대역(모델 없음·실패·mock)으로 채운다.

    선은 둘이다: 아이 몸에 해가 간 명백한 표현은 긴급으로 올리고, AI가 올린 위험은 코드가 내리지 않는다.
    """
    ai = proposal if isinstance(proposal, dict) else {}
    fallback = classify(request_type, body)
    result = {"topic_key": ai["topic_key"] if ai.get("topic_key") in TOPICS else fallback["topic_key"],
              "urgency": ai["urgency"] if ai.get("urgency") in ("normal", "urgent") else fallback["urgency"]}
    if request_type in RISK_TYPES:
        level = ai.get("risk_level")
        if level in LEVEL:
            category = ai.get("risk_category") if ai.get("risk_category") in RISK_CATEGORIES else None
            if level == "urgent" and category is None:
                level = "uncertain"  # 긴급은 위험 종류가 계약이에요. 종류를 못 대면 사람이 판단하게 판단 필요로 둬요.
            elif level == "normal":
                category = None
        else:
            level, category = fallback["risk_level"], fallback["risk_category"]
        if level != "urgent" and child_harm(body):
            level, category = "urgent", "child_safety"
        result.update(risk_level=level, risk_category=category)
        if level == "urgent":
            result["urgency"] = "urgent"
        reason = ai.get("risk_reason")
        if level == "uncertain" and isinstance(reason, str) and reason.strip():
            result["risk_reason"] = mask_sensitive(" ".join(reason.split()))[:RISK_REASON_MAX]
    suggested = ai.get("out_of_scope_kind", "missing")
    result["out_of_scope_kind"] = (suggested if suggested is None or suggested in OUT_OF_SCOPE_KINDS
                                   else scope_kind(body, result["topic_key"]))
    if result.get("risk_level") in ("urgent", "uncertain"):
        result["out_of_scope_kind"] = None
    result["intent"] = ai.get("intent") if request_type == "inquiry" and ai.get("intent") in INTENTS else "ask"
    return result
