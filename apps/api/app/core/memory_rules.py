"""두 저장소가 같은 규칙 입력과 기억의 이름 가림을 써요."""

import re

from app.core.errors import ApiError
from app.core.constants import RULE_TEXT_MAX_LENGTH, TONE_MAX_LENGTH
from agents.guardrails.sensitive import SENSITIVE

HHMM = r"(?:[01][0-9]|2[0-3]):[0-5][0-9]"
CLOCK = r"(?:(오전|오후)\s*)?(\d{1,2})(?::([0-5]\d)|시(?:\s*([0-5]?\d)분)?)"
# 선: 진단·질환·가정사가 든 글과 돌봄 낱말이 든 선호는 AI가 무엇이라 하든 확인 없이 기억하지 않아요.
PRIVATE_WORDS = r"진단|증후군|장애|질환|질병|치료|병원|확진|천식|당뇨|뇌전증|아토피|처방|복용|수술|입원|이혼|소득|채무|ADHD|자폐|우울"
CARE_WORDS = r"알레르기|낮잠|잠들|등원|안아|낯가림|분리불안"
# 대역: 기억 모델이 없거나 실패했을 때만 일회성·종류·반복을 이 낱말로 가려요. 모델이 있으면 AI 판단을 따라요.
FALLBACK_ONE_OFF = r"오늘|내일|이번|하루만|일찍|다른\s*아이|친구|동생|형제"
FALLBACK_CONTACT = r"상담|연락|안내|알림|전화|메시지|문자"
FALLBACK_REPEAT = r"선호|항상|보통|평소|매번|평일|매주"
RULE_KEYS = ("after", "before", "weekdays")


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
    """규칙 계약: 객체이고, 상담 시간 조건 after·before는 HH:MM, weekdays는 적용할 요일(월=0~일=6) 목록이에요."""
    def invalid(field, problem):
        return ApiError(422, "VALIDATION_FAILED", fields=[{"field": field, "problem": problem}])
    if not isinstance(rule_json, dict):
        raise invalid("rule_json", "객체여야 해요")
    for key in ("after", "before"):
        if key in rule_json and (not isinstance(rule_json[key], str) or not re.fullmatch(HHMM, rule_json[key])):
            raise invalid(f"rule_json.{key}", "HH:MM이어야 해요")
    if "after" in rule_json and "before" in rule_json and rule_json["after"] >= rule_json["before"]:
        raise invalid("rule_json.before", "after보다 늦어야 해요")
    days = rule_json.get("weekdays")
    if "weekdays" in rule_json and (not isinstance(days, list) or not days
                                    or any(type(day) is not int or not 0 <= day <= 6 for day in days)):
        raise invalid("rule_json.weekdays", "0(월)~6(일) 정수 목록이어야 해요")


def clock_times(content):
    """'오후 4시'·'16:00' 같은 시각을 HH:MM으로 읽어요."""
    times = []
    for meridiem, hour, minute, korean_minute in re.findall(CLOCK, content):
        hour, minute = int(hour), int(minute or korean_minute or 0)
        if meridiem and 1 <= hour <= 12:
            hour = hour % 12 + (12 if meridiem == "오후" else 0)
        if hour < 24:
            times.append(f"{hour:02d}:{minute:02d}")
    return times


def parent_candidates(candidates, body, names):
    """기억 AI가 고른 후보에서 선만 지켜요. 반복인지·어떤 종류인지는 AI 판단을 따라요.

    선: 보호자 원문 그대로 한 문장, 아이 이름·민감정보·진단·질환·가정사 차단, 시각 구조값은 원문과 일치.
    """
    if not isinstance(candidates, list) or len(candidates) > 2:
        raise ValueError("보호자 기억 후보 형식 오류")
    if re.search(PRIVATE_WORDS, body, re.I):
        return
    for item in candidates:
        if not isinstance(item, dict) or item.get("kind") not in ("preference", "care_note"):
            continue
        content = item.get("content")
        if (not isinstance(content, str) or not content.strip() or len(content) > TONE_MAX_LENGTH
                or content.strip() not in body or SENSITIVE.search(content)
                or re.search(r"[\r\n]|[.!?。！？].*\S", content)
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
        times = set(clock_times(content))
        if (any(value not in times for key, value in data.items() if key in ("after", "before"))
                or ("after" in data and not re.search(r"이후|부터", content))
                or ("before" in data and not re.search(r"이전|까지", content))
                or ("weekday" in data and "월화수목금토일"[data["weekday"]]+"요일" not in content)):
            continue
        if item["kind"] == "preference" and re.search(CARE_WORDS, content):
            continue  # 모델이 돌봄을 선호로 잘못 분류해도 보호자 확인을 우회하지 못해요.
        yield {"kind": item["kind"], "content": content.strip(), "structured": data}


def fallback_parent_candidates(body):
    """기억 모델이 없거나 실패했을 때만 쓰는 낱말 대역이에요. 결과는 parent_candidates의 선을 그대로 거쳐요.

    AI의 반복 판단을 대신하니 반복 낱말이 있는 평서문만 고르고, 일회성·다른 아이 낱말이 있으면 아무것도 고르지 않아요.
    """
    if re.search(FALLBACK_ONE_OFF, body):
        return []
    found = []
    for sentence in re.findall(r"[^.!?。！？\r\n]+[.!?。！？]*", body):
        content = sentence.strip()
        if re.search(r"[?？]$", content) or not re.search(FALLBACK_REPEAT, content):
            continue
        if re.search(CARE_WORDS, content):
            found.append({"kind": "care_note", "content": content, "structured": {}})
        elif re.search(FALLBACK_CONTACT, content):
            times, data = clock_times(content), {}
            if len(times) == 1:
                data = ({"after": times[0]} if re.search(r"이후|부터", content)
                        else {"before": times[0]} if re.search(r"이전|까지", content) else {})
            days = [n for n, word in enumerate("월화수목금토일") if word+"요일" in content]
            found.append({"kind": "preference", "content": content,
                          "structured": {**data, **({"weekday": days[0]} if len(days) == 1 else {})}})
    return found[:2]


def checked_rule(reply, reason_code, names):
    """기억 AI의 규칙 제안에서 선만 지켜요. 공통 규칙이 없다고 하면 None, 모양이 틀리면 ValueError예요."""
    if not isinstance(reply, dict) or "rule" not in reply:
        raise ValueError("규칙 제안 형식 오류")
    rule = reply["rule"]
    if rule is None:
        return None
    rule_text = rule.get("rule_text") if isinstance(rule, dict) else None
    data = rule.get("rule_json", {}) if isinstance(rule, dict) else None
    if (not isinstance(rule_text, str) or not rule_text.strip() or len(rule_text.strip()) > RULE_TEXT_MAX_LENGTH
            or re.search(r"[\r\n]", rule_text) or SENSITIVE.search(rule_text) or re.search(PRIVATE_WORDS, rule_text, re.I)
            or mask_child_names(rule_text, names) != rule_text or not isinstance(data, dict)):
        raise ValueError("규칙 제안 형식 오류")
    data = {key: data[key] for key in RULE_KEYS if key in data}
    validate_rule_json(data)
    return rule_text.strip(), {"reason_code": reason_code, **data}


def mask_child_names(content, names):
    # 이름 앞의 한글과 뒤의 낱말을 구분하고, 조사·호칭은 원문에 남겨요.
    names = sorted({name for name in names if name}, key=lambda name: (-len(name), name))
    if not names:
        return content
    suffix = r"(?:이?(?:가|은|는|을|를|의|에게|한테|랑|와|과|도|만|아|야|님)|이네|이)?"
    pattern = r"(?<![가-힣])(?:" + "|".join(map(re.escape, names)) + r")(?=" + suffix + r"(?:\W|$))"
    return re.sub(pattern, "○○", content)


def memory_page(items, saved, rules, kind, page, size, sort):
    """두 저장소가 같은 한 목록과 기존 종류별 칸을 돌려줘요."""
    items = [dict(row, title=(row.get("child_name") or "아이")+" 돌봄 메모" if row["kind"] == "care_note"
                  else {"tone": "말투", "preference": "선호", "rejection_reason": "거절 이유"}[row["kind"]],
                  source="memory") for row in items]
    for row in saved:
        items.append(dict(id=row["id"], kind="saved_answer", title=row["question"], content=row["answer"],
                          reason_code=None, structured={"status": row["status"]}, created_at=row["approved_at"], source="saved_answer"))
    for row in rules:
        items.append(dict(id=row["id"], kind="rule", title="상담·답변 규칙", content=row["rule_text"],
                          reason_code=row["reason_code"], structured={"status": row["status"], **row["rule_json"]},
                          created_at=row["created_at"], source="rule"))
    items = [row for row in items if kind is None or row["kind"] == kind]
    items.sort(key=lambda row: (row["created_at"], (0, row["id"]) if isinstance(row["id"], int) else (1, str(row["id"]))), reverse=sort.startswith("-"))
    return {"items": items[(page-1)*size:page*size], "total": len(items), "page": page, "size": size,
            "saved_answers": saved if kind in (None, "saved_answer") else [], "rules": rules if kind in (None, "rule") else []}
