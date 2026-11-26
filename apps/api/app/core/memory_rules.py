"""두 저장소가 같은 규칙 입력과 기억의 이름 가림을 써요."""

import re

from app.core.errors import ApiError
from app.core.constants import TONE_MAX_LENGTH
from agents.guardrails.sensitive import SENSITIVE


def tone_contents(candidates, names):
    for candidate in candidates:
        if not isinstance(candidate, dict) or candidate.get("kind") != "tone":
            continue
        content = candidate.get("content")
        if not isinstance(content, str):
            continue
        content = mask_child_names(content.strip(), names)
        if (not content or len(content) > TONE_MAX_LENGTH or SENSITIVE.search(content)
                or re.search(r"\d|[\r\n]|[.!?。！？].*\S", content)):
            continue
        yield content


def validate_rule_json(rule_json):
    if not isinstance(rule_json, dict):
        raise ApiError(422, "VALIDATION_FAILED", fields=[{"field": "rule_json", "problem": "객체여야 해요"}])
    for key in ("after", "before"):
        if key in rule_json and (not isinstance(rule_json[key], str)
                or not re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", rule_json[key])):
            raise ApiError(422, "VALIDATION_FAILED",
                           fields=[{"field": f"rule_json.{key}", "problem": "HH:MM이어야 해요"}])


def mask_child_names(content, names):
    # 이름 앞의 한글과 뒤의 낱말을 구분하고, 조사·호칭은 원문에 남겨요.
    names = sorted({name for name in names if name}, key=lambda name: (-len(name), name))
    if not names:
        return content
    suffix = r"(?:이?(?:가|은|는|을|를|의|에게|한테|랑|와|과|도|만|아|야|님)|이네|이)?"
    pattern = r"(?<![가-힣])(?:" + "|".join(map(re.escape, names)) + r")(?=" + suffix + r"(?:\W|$))"
    return re.sub(pattern, "○○", content)
