"""문의 자료를 찾고, 인용과 답변을 검사한 뒤 담임에게 초안을 넘긴다."""

import json
import re
from pathlib import Path

from agents.llm import ModelError, OpenAIModel, feature
from agents.guardrails.injection import suspicious_chunk
from agents.guardrails.sensitive import SENSITIVE, mask_sensitive

NO_ANSWER = "자료에서 확인되지 않아 선생님 확인이 필요해요."
PROMPTS = Path(__file__).resolve().parents[1] / "prompts"
WRITE_FORMAT = "\nJSON 하나로 답한다: {\"text\": str, \"evidence\": [{\"chunk_id\": int, \"quote\": str}], \"no_evidence\": bool, \"conflict\": bool}"
CHECK_FORMAT = "\nJSON 하나로 답한다: {\"passed\": bool, \"issues\": [{\"field\": \"출처|날짜|대상|누락|민감정보\", \"problem\": str}]}"
CHECK_FIELDS = {"출처", "날짜", "대상", "누락", "민감정보"}
MAX_REWRITES = 2


def fallback(trace):
    return {"text": NO_ANSWER, "evidence": [], "no_evidence": True, "conflict": False,
            "check_result": {"passed": False, "issues": [{"field": "출처",
                                                               "problem": "자료 답변을 확인하지 못했어요."}],
                             "attempt": 0}, "trace": [*trace, "end"]}


def _prompt(file, start, end=None):
    source = (PROMPTS / file).read_text(encoding="utf-8")
    return source[source.index(start):source.index(end) if end else None]


def _ask_writer(model, prompt, payload, trace):
    """답 모양 오류만 한 번 더 묻는다. 전송 오류는 모델 계층에서 처리했다."""
    for attempt in range(2):
        try:
            answer = model.json(prompt, json.dumps(payload, ensure_ascii=False, default=str))
            if (not isinstance(answer, dict) or not isinstance(answer.get("evidence"), list)
                    or not isinstance(answer.get("text"), str)):
                raise ModelError("답 모양 오류", format=True)
            trace.append("write")
            return answer
        except ModelError as error:
            if attempt or not error.format:
                trace.append("write")
                return None
    raise AssertionError("도달할 수 없음")


def _quoted(quote, content):
    """인용문이 조각에 글자 그대로 있는지 본다. 떨어진 줄 여러 개를 이어 붙인 인용은 줄마다 본다."""
    body = re.sub(r"\s+", "", content)
    parts = [part for part in (re.sub(r"\s+", "", line) for line in quote.splitlines()) if part]
    return re.sub(r"\s+", "", quote) in body or (len(parts) > 1 and all(part in body for part in parts))


def _verify(answer, candidates, trace):
    by_id = {str(chunk["chunk_id"]): chunk for chunk in candidates}
    evidence = []
    seen = set()
    for item in answer["evidence"]:
        if not isinstance(item, dict):
            continue
        chunk = by_id.get(str(item.get("chunk_id")))
        if chunk and chunk["chunk_id"] in seen:
            continue  # card_evidence PK가 (card_id, chunk_id)라 같은 조각은 한 번만 남긴다
        quote = item.get("quote")
        if chunk and isinstance(quote, str) and quote.strip() and _quoted(quote, chunk["content"]):
            seen.add(chunk["chunk_id"])
            evidence.append({"chunk_id": chunk["chunk_id"], "quote": quote, "score": chunk["score"]})
    no_evidence = bool(answer.get("no_evidence")) or not evidence
    conflict = bool(answer.get("conflict"))
    trace.append("verify")
    # 모델은 근거가 있다고 했는데 인용문이 하나도 글자 그대로가 아니면, 근거 없음으로 끝내지 않고 다시 쓰게 한다.
    misquoted = bool(answer["evidence"]) and not evidence and not answer.get("no_evidence") and not conflict
    return {"text": NO_ANSWER if no_evidence or conflict else answer["text"], "evidence": evidence,
            "no_evidence": no_evidence, "conflict": conflict, "misquoted": misquoted}


def _review(model, question, draft, candidates, attempt, trace):
    prompt = _prompt("common.md", "# 공통 규칙") + _prompt("checker.md", "## 입력", "## 알림장: 메모와 대조한다") + CHECK_FORMAT
    payload = {"question": question, "draft": draft["text"], "evidence": draft["evidence"],
               "chunks": candidates, "attempt": attempt,
               "untrusted_data_fields": ["question", "chunks", "draft"]}
    for _ in range(2):
        try:
            result = model.json(prompt, json.dumps(payload, ensure_ascii=False, default=str))
        except ModelError:
            trace.append("check")
            continue
        trace.append("check")
        if not isinstance(result, dict) or not isinstance(result.get("passed"), bool) or not isinstance(result.get("issues"), list):
            continue
        issues = result["issues"]
        if any(not isinstance(issue, dict) or issue.get("field") not in CHECK_FIELDS
               or not isinstance(issue.get("problem"), str) or not issue["problem"].strip() for issue in issues):
            continue
        if result["passed"] and issues:
            continue
        if not result["passed"] and not issues:
            continue
        if SENSITIVE.search(draft["text"]) and not any(i["field"] == "민감정보" for i in issues):
            issues = [*issues, {"field": "민감정보", "problem": "초안에 민감정보 형식이 있어 담임 확인이 필요해요."}]
        return issues
    return None


def _check_result(passed, issues, attempt):
    return {"passed": passed, "issues": [{"field": issue["field"], "problem": issue["problem"]}
                                         for issue in issues], "attempt": attempt}


@feature("문의 답변 초안")
def draft_answer(question: str, search, writer=None, checker=None, *, memories=(), prior_answer=None, preferences=(), child_notes=()) -> dict:
    trace = []
    candidates = []
    for doc_type in ("notice", "schedule", "menu", "policy"):
        for attempt in range(2):
            try:
                candidates.extend(search(doc_type, question))
                break
            except Exception:  # 검색 도구 오류는 한 번 다시 시도한다
                if attempt:
                    return fallback([*trace, "search"])
    trace.append("search")
    candidates = sorted((item for item in candidates if not suspicious_chunk(item["content"])),
                        key=lambda item: item["score"], reverse=True)[:8]
    if not candidates:
        return fallback(trace)
    common = _prompt("common.md", "# 공통 규칙")
    write_prompt = common + _prompt("documents.md", "## 입력", "## 알림장 초안 쓰기") + WRITE_FORMAT
    writer = writer if writer is not None else OpenAIModel("DOCUMENT")
    checker = checker if checker is not None else OpenAIModel("CHECKER")
    issues = []
    for attempt in range(MAX_REWRITES + 1):
        answer = _ask_writer(writer, write_prompt, {"question": mask_sensitive(question), "chunks": candidates,
                                                    "memories": list(memories),
                                                    "prior_answer": prior_answer, "preferences": list(preferences), "child_notes": list(child_notes),
                                                    "review_issues": issues,
                                                    "untrusted_data_fields": ["question", "chunks", "memories", "prior_answer", "preferences", "child_notes"]}, trace)
        if answer is None:
            return fallback(trace)
        draft = _verify(answer, candidates, trace)
        misquoted = draft.pop("misquoted")
        if misquoted and attempt < MAX_REWRITES:
            issues = [{"field": "출처", "problem": "인용문이 자료 조각과 글자 그대로 일치하지 않아요. "
                       "조각의 한 줄(또는 이어진 구절)을 고치지 말고 그대로 복사해 quote에 넣어 주세요."}]
            last_check = _check_result(False, issues, attempt + 1)
            continue
        if draft["no_evidence"] or draft["conflict"]:
            problem = "자료끼리 내용이 달라요." if draft["conflict"] else "자료에서 근거를 찾지 못했어요."
            return {**draft, "check_result": _check_result(False, [{"field": "출처", "problem": problem}], attempt + 1),
                    "trace": [*trace, "end"]}
        issues = _review(checker, mask_sensitive(question), draft, candidates, attempt + 1, trace)
        if issues is None:
            return fallback(trace)
        if not issues:
            return {**draft, "check_result": _check_result(True, [], attempt + 1),
                    "trace": [*trace, "end"]}
        last_check = _check_result(False, issues, attempt + 1)
    return {**fallback(trace), "check_result": last_check}
