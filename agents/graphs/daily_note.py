"""알림장 초안 그래프: 자료 AI가 쓰고, 코드와 검사 AI가 메모·보호자 요청과 대조한다.

기준: Docs/Step2/알림장_에이전트_흐름.md, API 설계 문서 v0.4 3.7·3.19, agents/prompts/documents.md·checker.md '알림장'.
백엔드는 입구 함수 draft_daily_notes()만 부른다. 입력 모으기·저장·상태·이력은 백엔드가 한다.

- 반 공통 줄(day·supplies·meal)은 코드가 그대로 만든다. AI는 아이 메모 줄과 보호자 요청 줄만 쓴다.
- 쓰기·검사는 각각 1번 다시 한다. 메모에 없는 말·요청 누락은 자료 AI로 최대 2번 돌려보낸다.
- 아이들은 동시에 처리한다. 동시 실행 수는 NOTE_DRAFT_CONCURRENCY(기본 5)로 묶는다(흐름 문서 5장).
"""

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from agents.llm import JsonModel, ModelError, OpenAIModel, feature, keep_trace

PROMPTS = Path(__file__).resolve().parents[1] / "prompts"
RETURN_KINDS = {"not_in_memo", "request_missed"}       # 자료 AI가 고칠 수 있는 문제
MODEL_KINDS = {"not_in_memo", "sensitive", "other_child", "date_check", "absent"}  # 검사 AI가 낼 수 있는 값
MAX_RETURNS = 2
REQUEST_KEY = {"medication": "medication", "pickup": "pickup", "inquiry": "inquiry"}  # 계약 v0.4.1(#282)
NO_SUPPLIES = {"", "없음"}

PROBLEM = {
    "draft_failed": "이 아이 초안을 만들지 못했어요. 다시 시도하거나 직접 써 주세요.",
    "check_failed": "메모와 대조하는 검사가 끝나지 않았어요. 직접 읽고 확인해 주세요.",
    "return_limit": "AI가 두 번 고쳐도 남은 문제가 있어요. 직접 확인해 주세요.",
    "request_missed": "보호자 요청이 초안에 없어요. 요청 내용을 넣어 주세요.",
    "other_child": "다른 아이 이름이 들어 있어요. 이 아이 알림장에서는 빼 주세요.",
    "memo_left_out": "선생님 메모를 알림장에 옮기지 않았어요. 메모를 보고 직접 확인해 주세요.",
    "medication": "보호자 투약 요청이에요. 보내기 전에 직접 확인해 주세요.",
    "unanswered": "보호자 문의에 선생님 답이 필요해요. 메모에 답할 내용이 없었어요.",
}

WRITE_FORMAT = """
## 답 형식
JSON 하나로만 답한다.
{"child": "아이 메모 줄 문장, 쓰지 않으면 null", "requests": [{"request_id": "입력의 request_id", "value": "그 요청 줄 문장", "answered": true}]}
- 반 공통 활동·준비물·식단 줄은 코드가 만든다. 너는 child와 requests만 쓴다.
- requests에는 입력의 보호자 요청마다 하나씩 쓴다.
- 문의에 메모로 답했으면 answered는 true, 메모에 답할 내용이 없어 문의 내용만 옮겼으면 false다.
- 요청 줄에 아이 메모 줄과 같은 문장을 다시 쓰지 않는다.
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


def concurrency() -> int:
    return max(1, int(os.getenv("NOTE_DRAFT_CONCURRENCY", "5")))


@feature("알림장 초안")
def draft_daily_notes(payload: dict, writer: JsonModel | None = None, checker: JsonModel | None = None,
                      workers: int | None = None) -> list[dict]:
    """입구 함수. payload = {input_id, note_date, classroom, activities, supplies, children[], menu}.

    돌려주는 값: 아이마다 {child_id, content: {items[]}, open_checks[]}. 순서는 입력 children 순서와 같다.
    """
    writer = writer or OpenAIModel("DOCUMENT")
    checker = checker or OpenAIModel("CHECKER")
    names = payload.get("roster_names")
    if names is None:
        names = [child["display_name"] for child in payload["children"]]
    common = common_lines(payload)
    def run(child):
        return draft_child(payload, child, common, names, writer, checker)

    workers = workers or concurrency()
    if workers == 1:
        return [run(child) for child in payload["children"]]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(keep_trace(run), payload["children"]))


def common_lines(payload: dict) -> dict:
    lines = {"day": {"key": "day", "label": "오늘 하루", "value": payload["activities"], "source": {"type": "teacher_input"}}}
    if (payload.get("supplies") or "").strip() not in NO_SUPPLIES:
        lines["supplies"] = {"key": "supplies", "label": "준비물", "value": payload["supplies"],
                             "source": {"type": "teacher_input"}}
    menu = payload.get("menu")
    if menu:
        lines["meal"] = {"key": "meal", "label": "식사", "value": meal_text(menu["text"], payload["note_date"]),
                         "source": {"type": "document", "document_id": menu["document_id"], "document_title": menu["title"]}}
    return lines


def meal_text(text: str, note_date: str) -> str:
    """주간 식단표 본문에서 그날 행만 '점심: … / 오후 간식: …'으로. 행을 못 찾으면 원문 그대로."""
    mmdd = str(note_date)[5:10]
    lines = [line.strip() for line in text.splitlines() if line.strip().startswith("|")]
    row = next((line for line in lines if re.match(rf"\|\s*{re.escape(mmdd)}\b", line)), None)
    if row is None:
        return text
    def cells(line):
        return [cell.strip() for cell in line.strip("|").split("|")]

    header = cells(lines[0]) if lines and lines[0] != row else []
    values = cells(row)[1:]
    names = header[1:] if len(header) == len(values) + 1 else [""] * len(values)
    return " / ".join(f"{name}: {value}" if name else value for name, value in zip(names, values) if value)


def draft_child(payload, child, common, names, writer, checker) -> dict:
    memo = (child.get("memo") or "").strip()
    requests = child.get("requests") or []
    trace: list[dict] = []  # 단계·결과 요약만 남긴다. 모델의 생각 원문은 남기지 않는다(T25 4칸)
    if not memo and not requests:  # 쓸 것이 없으면 AI를 부르지 않는다(빈 메모를 채우지 않음)
        trace.append({"step": "skip", "result": "메모·요청 없음"})
        return result(child, common, [], [], trace, "done")

    issues: list[dict] = []
    for attempt in range(MAX_RETURNS + 1):
        try:
            own = twice(lambda: write(writer, payload, child, issues))
        except ModelError as error:
            trace.append({"step": "write", "attempt": attempt, "result": "failed", "error": str(error)})
            return result(child, common, [], [new_check("child", "draft_failed")], trace, "handoff", "draft_failed")
        trace.append({"step": "write", "attempt": attempt, "result": "ok",
                      "lines": [{"key": line["key"], "value": line["value"]} for line in own]})
        found = code_checks(own, child, names)
        try:
            found += twice(lambda: review(checker, payload, child, own))
            review_result = "ok"
        except ModelError as error:
            found.append(new_check("child", "check_failed"))
            review_result = f"failed: {error}"
        found = unique(found + memo_left_out(memo, own, found) + unanswered(own))
        issues = [f for f in found if f["kind"] in RETURN_KINDS]
        trace.append({"step": "check", "attempt": attempt, "result": review_result,
                      "kinds": [f["kind"] for f in found]})
        if any(f["kind"] == "check_failed" for f in found):
            return result(child, common, own, found, trace, "handoff", "check_failed")
        if not issues:
            return result(child, common, own, found, trace, "needs_check" if found else "done")
        if attempt == MAX_RETURNS:
            found.append(new_check("child", "return_limit"))
            return result(child, common, own, found, trace, "handoff", "return_limit")
        trace.append({"step": "return", "attempt": attempt, "kinds": [f["kind"] for f in issues]})
    raise AssertionError("unreachable")


def twice(call):
    """답 모양이 틀렸을 때만 1번 더 묻는다(T14 6장). 전송 오류 재시도는 llm.py(API 설계 6.2)가 이미 했다."""
    try:
        return call()
    except ModelError as error:
        if not error.format:
            raise
        return call()


def write(model: JsonModel, payload, child, issues) -> list[dict]:
    user = json.dumps({
        "note_date": payload["note_date"], "classroom": payload.get("classroom"),
        "activities": payload["activities"], "supplies": payload.get("supplies"),
        "menu": (payload.get("menu") or {}).get("text"),
        "child_name": child["display_name"], "child_memo": child.get("memo") or "",
        "requests": child.get("requests") or [], "review_issues": issues,
        "untrusted_data_fields": ["child_memo", "requests", "menu"],
    }, ensure_ascii=False)
    answer = model.json(section("common.md", "# 공통 규칙") + section("documents.md", "## 알림장 초안 쓰기") + WRITE_FORMAT, user)
    by_id = {req["request_id"]: req for req in child.get("requests") or []}
    lines = []
    text = (answer.get("child") or "").strip() if isinstance(answer.get("child"), str) else ""
    if text:
        lines.append({"key": "child", "label": "아이 메모", "value": text, "source": {"type": "teacher_input"}})
    def same(a, b):
        return re.sub(r"\s+", "", a) == re.sub(r"\s+", "", b)

    for line in answer.get("requests") or []:
        req = by_id.get(line.get("request_id"))
        value = (line.get("value") or "").strip() if isinstance(line.get("value"), str) else ""
        if not (req and value):  # 입력에 없는 요청 ID는 버린다
            continue
        answered = line.get("answered") is not False
        if text and same(value, text):  # 아이 메모 줄을 다시 쓴 것: 요청 원문을 옮기고 선생님 답으로 넘긴다
            value, answered = f"보호자 요청: {req['text']}", False
        out = {"key": REQUEST_KEY[req["type"]], "label": "보호자 요청", "value": value,
               "source": {"type": "request", "request_id": req["request_id"]}}
        if req["type"] == "inquiry" and not answered:
            out["_unanswered"] = True
        lines.append(out)
    return lines


def unanswered(own: list[dict]) -> list[dict]:
    """메모로 답하지 못한 문의는 선생님 확인으로 넘긴다(팀 1안, 11/20)."""
    found = []
    for line in own:
        if line.pop("_unanswered", False):
            found.append(new_check(line["key"], "sensitive", problem=PROBLEM["unanswered"],
                                   sentence=line["value"], request_id=line["source"]["request_id"]))
    return found


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
        "untrusted_data_fields": ["child_memo", "requests", "menu", "draft"],
    }, ensure_ascii=False)
    answer = model.json(section("common.md", "# 공통 규칙") + section("checker.md", "## 알림장: 메모와 대조한다") + CHECK_FORMAT, user)
    checks = answer.get("checks")
    if not isinstance(checks, list):
        raise ModelError("checks 목록이 없어요", format=True)
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
    """같은 줄(item_key)·같은 kind는 하나로 합친다. 요청 누락만 요청마다 따로 둔다."""
    kept: dict[tuple, dict] = {}
    for f in found:
        key = (f["kind"], f["item_key"], f.get("request_id") if f["kind"] == "request_missed" else None)
        if key not in kept:
            kept[key] = dict(f)
        elif f.get("request_id") and not kept[key].get("request_id"):
            kept[key]["request_id"] = f["request_id"]
    return list(kept.values())


def result(child, common, own, found, trace=None, end="done", handoff_reason=None) -> dict:
    """handoff일 때만 인계 이유를 돌려준다. 현재 백엔드는 trace·end·handoff_reason을 저장하지 않는다."""
    items = [common["day"], *own, *(common[k] for k in ("supplies", "meal") if k in common)]
    checks = [{"id": f"c{n}", **f} for n, f in enumerate(found, start=1)]
    output = {"child_id": child["child_id"], "content": {"items": items}, "open_checks": checks,
              "end": end, "trace": (trace or []) + [{"step": "end", "result": end}]}
    if end == "handoff":
        output["handoff_reason"] = handoff_reason
    return output
