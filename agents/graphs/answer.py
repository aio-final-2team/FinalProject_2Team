"""문의 자료를 찾고, 인용과 답변을 검사한 뒤 담임에게 초안을 넘긴다."""

import json
import re
from pathlib import Path

from agents.llm import ModelError, OpenAIModel

NO_ANSWER = "자료에서 확인되지 않아 선생님 확인이 필요해요."
PROMPTS = Path(__file__).resolve().parents[1] / "prompts"
WRITE_FORMAT = "\nJSON 하나로 답한다: {\"text\": str, \"evidence\": [{\"chunk_id\": int, \"quote\": str}], \"no_evidence\": bool, \"conflict\": bool}"
CHECK_FORMAT = "\nJSON 하나로 답한다: {\"passed\": bool, \"issues\": [{\"field\": \"출처|날짜|대상|누락|민감정보\", \"problem\": str}]}"
CHECK_FIELDS = {"출처", "날짜", "대상", "누락", "민감정보"}
MAX_REWRITES = 2


def fallback(trace):
    return {"text": NO_ANSWER, "evidence": [], "no_evidence": True, "conflict": False,
            "trace": [*trace, "end"]}


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


def _verify(answer, candidates, trace):
    by_id = {str(chunk["chunk_id"]): chunk for chunk in candidates}
    evidence = []
    for item in answer["evidence"]:
        if not isinstance(item, dict):
            continue
        chunk = by_id.get(str(item.get("chunk_id")))
        quote = item.get("quote")
        if (chunk and isinstance(quote, str) and quote.strip()
                and re.sub(r"\s+", "", quote) in re.sub(r"\s+", "", chunk["content"])):
            evidence.append({"chunk_id": chunk["chunk_id"], "quote": quote, "score": chunk["score"]})
    no_evidence = bool(answer.get("no_evidence")) or not evidence
    conflict = bool(answer.get("conflict"))
    trace.append("verify")
    return {"text": NO_ANSWER if no_evidence or conflict else answer["text"], "evidence": evidence,
            "no_evidence": no_evidence, "conflict": conflict}


def _review(model, question, draft, candidates, attempt, trace):
    prompt = _prompt("checker.md", "## 입력", "## 알림장: 메모와 대조한다") + CHECK_FORMAT
    payload = {"question": question, "draft": draft["text"], "evidence": draft["evidence"],
               "chunks": candidates, "attempt": attempt}
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
        return issues
    return None


def draft_answer(question: str, search, writer=None, checker=None) -> dict:
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
    candidates = sorted(candidates, key=lambda item: item["score"], reverse=True)[:8]
    if not candidates:
        return fallback(trace)
    write_prompt = _prompt("documents.md", "## 입력", "## 알림장 초안 쓰기") + WRITE_FORMAT
    writer = writer if writer is not None else OpenAIModel("DOCUMENT")
    checker = checker if checker is not None else OpenAIModel("CHECKER")
    issues = []
    for attempt in range(MAX_REWRITES + 1):
        answer = _ask_writer(writer, write_prompt, {"question": question, "chunks": candidates,
                                                    "review_issues": issues}, trace)
        if answer is None:
            return fallback(trace)
        draft = _verify(answer, candidates, trace)
        if draft["no_evidence"] or draft["conflict"]:
            return {**draft, "trace": [*trace, "end"]}
        issues = _review(checker, question, draft, candidates, attempt + 1, trace)
        if issues is None:
            return fallback(trace)
        if not issues:
            return {**draft, "trace": [*trace, "end"]}
    return fallback(trace)
