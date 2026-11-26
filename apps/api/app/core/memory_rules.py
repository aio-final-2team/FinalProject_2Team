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


def parent_candidates(candidates, body, names):
    """자유 추측은 저장하지 않아요. 후보 문장이 보호자 원문에 그대로 있어야 해요."""
    if not isinstance(candidates, list) or len(candidates) > 2:
        raise ValueError("보호자 기억 후보 형식 오류")
    for item in candidates:
        if not isinstance(item, dict) or item.get("kind") not in ("preference", "care_note"):
            continue
        content = item.get("content")
        if (not isinstance(content, str) or not content.strip() or len(content) > TONE_MAX_LENGTH
                or content.strip() not in body or SENSITIVE.search(content)
                or re.search(r"[\r\n]|[.!?。！？].*\S", content)
                or re.search(r"오늘|내일|이번|하루만|일찍|진단|증후군|장애|질환|질병|치료|병원|확진|천식|당뇨|뇌전증|아토피|처방|복용|수술|입원|이혼|소득|채무|ADHD|자폐|우울|다른\s*아이|친구|동생|형제", body, re.I)
                or mask_child_names(content, names) != content):
            continue
        data = item.get("structured", {})
        if not isinstance(data, dict) or set(data) - {"after", "before", "weekday"}:
            continue
        try:
            validate_rule_json(data)
        except ApiError:
            continue
        if "weekday" in data and (type(data["weekday"]) is not int or not 0 <= data["weekday"] <= 6):
            continue
        times = set()
        for meridiem, hour, minute, korean_minute in re.findall(
                r"(?:(오전|오후)\s*)?(\d{1,2})(?::([0-5]\d)|시(?:\s*([0-5]?\d)분)?)", content):
            hour, minute = int(hour), int(minute or korean_minute or 0)
            if meridiem and 1 <= hour <= 12:
                hour = hour % 12 + (12 if meridiem == "오후" else 0)
            if hour < 24:
                times.add(f"{hour:02d}:{minute:02d}")
        if (any(value not in times for key, value in data.items() if key in ("after", "before"))
                or ("after" in data and not re.search(r"이후|부터", content))
                or ("before" in data and not re.search(r"이전|까지", content))
                or ("after" in data and "before" in data and data["after"] >= data["before"])
                or ("weekday" in data and "월화수목금토일"[data["weekday"]]+"요일" not in content)):
            continue
        # 돌봄은 한정된 반복 돌봄 표현만, 선호는 반복 의사를 직접 밝힌 문장만 받아요.
        if item["kind"] == "preference" and (re.search(r"알레르기|낮잠|잠들|등원|안아|낯가림|분리불안", content)
                or not re.search(r"상담|연락|안내|알림|전화|메시지|문자", content)):
            continue  # 모델이 돌봄을 선호로 잘못 분류해도 확인을 우회하지 못해요.
        pattern = r"알레르기|낮잠|잠들|등원|안아|낯가림|분리불안" if item["kind"] == "care_note" else r"선호|항상|보통|평소|매번|평일|매주"
        if re.search(pattern, content):
            yield {"kind": item["kind"], "content": content.strip(), "structured": data}


def mask_child_names(content, names):
    # 이름 앞의 한글과 뒤의 낱말을 구분하고, 조사·호칭은 원문에 남겨요.
    names = sorted({name for name in names if name}, key=lambda name: (-len(name), name))
    if not names:
        return content
    suffix = r"(?:이?(?:가|은|는|을|를|의|에게|한테|랑|와|과|도|만|아|야|님)|이네|이)?"
    pattern = r"(?<![가-힣])(?:" + "|".join(map(re.escape, names)) + r")(?=" + suffix + r"(?:\W|$))"
    return re.sub(pattern, "○○", content)
