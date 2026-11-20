"""알림장 초안 그래프: 자료 AI가 쓰고, 코드와 검사 AI가 메모·보호자 요청과 대조한다.

기준: Docs/Step2/알림장_에이전트_흐름.md, API 설계 문서 v0.4 3.7·3.19, agents/prompts/documents.md·checker.md '알림장'.
백엔드는 입구 함수 draft_daily_notes()만 부른다. 입력 모으기·저장·상태·이력은 백엔드가 한다.

- 반 공통 줄(day·supplies·meal)은 코드가 그대로 만든다. AI는 아이 메모 줄과 보호자 요청 줄만 쓴다.
- 쓰기·검사는 각각 1번 다시 한다. 메모에 없는 말·요청 누락은 자료 AI로 최대 2번 돌려보낸다.
"""

import json
from pathlib import Path

from agents.llm import JsonModel, ModelError, OpenAIModel

PROMPTS = Path(__file__).resolve().parents[1] / "prompts"
RETURN_KINDS = {"not_in_memo", "request_missed"}       # 자료 AI가 고칠 수 있는 문제
MODEL_KINDS = {"not_in_memo", "sensitive", "other_child", "date_check", "absent"}  # 검사 AI가 낼 수 있는 값
MAX_RETURNS = 2
REQUEST_KEY = {"medication": "medication", "pickup": "pickup", "inquiry": "day"}
NO_SUPPLIES = {"", "없음"}

PROBLEM = {
    "draft_failed": "이 아이 초안을 만들지 못했어요. 다시 시도하거나 직접 써 주세요.",
    "check_failed": "메모와 대조하는 검사가 끝나지 않았어요. 직접 읽고 확인해 주세요.",
    "request_missed": "보호자 요청이 초안에 없어요. 요청 내용을 넣어 주세요.",
    "other_child": "다른 아이 이름이 들어 있어요. 이 아이 알림장에서는 빼 주세요.",
    "memo_left_out": "선생님 메모를 알림장에 옮기지 않았어요. 메모를 보고 직접 확인해 주세요.",
    "medication": "보호자 투약 요청이에요. 보내기 전에 직접 확인해 주세요.",
}

WRITE_FORMAT = """
## 답 형식
JSON 하나로만 답한다.
{"child": "아이 메모 줄 문장, 쓰지 않으면 null", "requests": [{"request_id": "입력의 request_id", "value": "그 요청을 옮긴 문장"}]}
- 반 공통 활동·준비물·식단 줄은 코드가 만든다. 너는 child와 requests만 쓴다.
- requests에는 입력의 보호자 요청마다 하나씩 쓴다.
"""

CHECK_FORMAT = """
## 답 형식
JSON 하나로만 답한다. 문제가 없으면 checks는 빈 목록이다.
{"checks": [{"item_key": "child 또는 줄 key", "kind": "not_in_memo|sensitive|other_child|date_check|absent", "problem": "선생님이 읽을 설명 한 문장", "sentence": "걸린 초안 문장 또는 null"}]}
- 보호자 요청 누락은 코드가 따로 본다. 너는 위 다섯 값만 쓴다.
"""


def section(file: str, heading: str) -> str:
    text = (PROMPTS / file).read_text(encoding="utf-8")
    return text[text.index(heading):]


def draft_daily_notes(payload: dict, writer: JsonModel | None = None, checker: JsonModel | None = None) -> list[dict]:
    """입구 함수. payload = {input_id, note_date, classroom, activities, supplies, children[], menu}.

    돌려주는 값: 아이마다 {child_id, content: {items[]}, open_checks[]}.
    """
    writer = writer or OpenAIModel("DOCUMENT")
    checker = checker or OpenAIModel("CHECKER")
    names = [child["display_name"] for child in payload["children"]]
    common = common_lines(payload)
    return [draft_child(payload, child, common, names, writer, checker) for child in payload["children"]]


def common_lines(payload: dict) -> dict:
    lines = {"day": {"key": "day", "label": "오늘 하루", "value": payload["activities"], "source": {"type": "teacher_input"}}}
    if (payload.get("supplies") or "").strip() not in NO_SUPPLIES:
        lines["supplies"] = {"key": "supplies", "label": "준비물", "value": payload["supplies"],
                             "source": {"type": "teacher_input"}}
    menu = payload.get("menu")
    if menu:
        lines["meal"] = {"key": "meal", "label": "식사", "value": menu["text"],
                         "source": {"type": "document", "document_id": menu["document_id"], "document_title": menu["title"]}}
    return lines


def draft_child(payload, child, common, names, writer, checker) -> dict:
    memo = (child.get("memo") or "").strip()
    requests = child.get("requests") or []
    if not memo and not requests:  # 쓸 것이 없으면 AI를 부르지 않는다(빈 메모를 채우지 않음)
        return result(child, common, [], [])

    issues: list[dict] = []
    for attempt in range(MAX_RETURNS + 1):
        try:
            own = twice(lambda: write(writer, payload, child, issues))
        except ModelError:
            return result(child, common, [], [new_check("child", "draft_failed")])
        found = code_checks(own, child, names)
        try:
            found += twice(lambda: review(checker, payload, child, own))
        except ModelError:
            found.append(new_check("child", "check_failed"))
        found = unique(found + memo_left_out(memo, own, found))
        issues = [f for f in found if f["kind"] in RETURN_KINDS]
        if not issues or attempt == MAX_RETURNS or any(f["kind"] == "check_failed" for f in found):
            return result(child, common, own, found)
    raise AssertionError("unreachable")


def twice(call):
    """1번 다시(T14 6장). 두 번째도 실패하면 ModelError를 그대로 올린다."""
    try:
        return call()
    except ModelError:
        return call()


def write(model: JsonModel, payload, child, issues) -> list[dict]:
    user = json.dumps({
        "note_date": payload["note_date"], "classroom": payload.get("classroom"),
        "activities": payload["activities"], "supplies": payload.get("supplies"),
        "menu": (payload.get("menu") or {}).get("text"),
        "child_name": child["display_name"], "child_memo": child.get("memo") or "",
        "requests": child.get("requests") or [], "review_issues": issues,
    }, ensure_ascii=False)
    answer = model.json(section("documents.md", "## 알림장 초안 쓰기") + WRITE_FORMAT, user)
    by_id = {req["request_id"]: req for req in child.get("requests") or []}
    lines = []
    text = (answer.get("child") or "").strip() if isinstance(answer.get("child"), str) else ""
    if text:
        lines.append({"key": "child", "label": "아이 메모", "value": text, "source": {"type": "teacher_input"}})
    for line in answer.get("requests") or []:
        req = by_id.get(line.get("request_id"))
        value = (line.get("value") or "").strip() if isinstance(line.get("value"), str) else ""
        if req and value:  # 입력에 없는 요청 ID는 버린다
            lines.append({"key": REQUEST_KEY[req["type"]], "label": "보호자 요청", "value": value,
                          "source": {"type": "request", "request_id": req["request_id"]}})
    return lines


def code_checks(own: list[dict], child: dict, names: list[str]) -> list[dict]:
    """AI 없이 확실히 잡을 수 있는 것: 다른 아이 이름(메모·초안), 보호자 요청 누락."""
    found = []
    others = [n for n in names if n != child["display_name"] and n not in child["display_name"]]
    for line in own:
        hit = [n for n in others if n in line["value"]]
        if hit:
            found.append(new_check(line["key"], "other_child", sentence=line["value"]))
    memo = child.get("memo") or ""
    if not found and any(n in memo for n in others):  # 초안에서 이름을 뺐어도 누구 이야기인지는 선생님이 본다
        found.append(new_check("child", "other_child", problem="메모에 다른 아이 이름이 있어요. 누구 이야기인지 확인해 주세요."))
    covered = {line["source"].get("request_id") for line in own if line["source"]["type"] == "request"}
    for req in child.get("requests") or []:
        if req["request_id"] not in covered:
            found.append(new_check(REQUEST_KEY[req["type"]], "request_missed", request_id=req["request_id"]))
        elif req["type"] == "medication":  # 투약은 늘 사람이 본다(NFR-03)
            found.append(new_check("medication", "sensitive", problem=PROBLEM["medication"], request_id=req["request_id"]))
    return found


def memo_left_out(memo: str, own: list[dict], found: list[dict]) -> list[dict]:
    """안전장치: 메모가 있는데 아이 메모 줄이 없고 아이 메모 확인도 없으면 선생님 확인을 남긴다."""
    if not memo or any(line["key"] == "child" for line in own):
        return []
    if any(f["item_key"] == "child" and f["kind"] in MODEL_KINDS for f in found):
        return []
    return [new_check("child", "sensitive", problem=PROBLEM["memo_left_out"])]


def review(model: JsonModel, payload, child, own) -> list[dict]:
    user = json.dumps({
        "activities": payload["activities"], "supplies": payload.get("supplies"),
        "menu": (payload.get("menu") or {}).get("text"),
        "child_memo": child.get("memo") or "", "requests": child.get("requests") or [], "draft": own,
    }, ensure_ascii=False)
    answer = model.json(section("checker.md", "## 알림장: 메모와 대조한다") + CHECK_FORMAT, user)
    checks = answer.get("checks")
    if not isinstance(checks, list):
        raise ModelError("checks 목록이 없어요")
    found = []
    for check in checks:
        if isinstance(check, dict) and check.get("kind") in MODEL_KINDS:
            found.append(new_check(check.get("item_key") or "child", check["kind"],
                                   problem=check.get("problem"), sentence=check.get("sentence")))
    return found


def new_check(item_key, kind, problem=None, sentence=None, request_id=None) -> dict:
    check = {"item_key": item_key, "kind": kind, "problem": problem or PROBLEM.get(kind) or "선생님 확인이 필요해요.",
             "sentence": sentence}
    if request_id:
        check["request_id"] = request_id
    return check


def unique(found: list[dict]) -> list[dict]:
    seen, out = set(), []
    for f in found:
        key = (f["kind"], f["item_key"], f.get("request_id"), f.get("sentence"))
        if key not in seen:
            seen.add(key)
            out.append(f)
    return out


def result(child, common, own, found) -> dict:
    items = [common["day"], *own, *(common[k] for k in ("supplies", "meal") if k in common)]
    checks = [{"id": f"c{n}", **f} for n, f in enumerate(found, start=1)]
    return {"child_id": child["child_id"], "content": {"items": items}, "open_checks": checks}
