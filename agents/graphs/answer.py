"""문의에 쓸 근거를 찾아 검증한 답변 초안을 만든다."""

import json
import re
from pathlib import Path

from agents.llm import ModelError, OpenAIModel

NO_ANSWER = "자료에서 확인되지 않아 선생님 확인이 필요해요."
PROMPT = Path(__file__).resolve().parents[1] / "prompts" / "documents.md"
FORMAT = "\nJSON 하나로 답한다: {\"text\": str, \"evidence\": [{\"chunk_id\": int, \"quote\": str}], \"no_evidence\": bool, \"conflict\": bool}"


def fallback(trace):
    return {"text": NO_ANSWER, "evidence": [], "no_evidence": True, "conflict": False,
            "trace": [*trace, "end"]}


def draft_answer(question: str, search, writer=None) -> dict:
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
    prompt = PROMPT.read_text(encoding="utf-8")
    prompt = prompt[prompt.index("## 입력"):prompt.index("## 알림장 초안 쓰기")] + FORMAT
    model = writer if writer is not None else OpenAIModel("DOCUMENT")
    payload = json.dumps({"question": question, "chunks": candidates}, ensure_ascii=False, default=str)
    for attempt in range(2):
        try:
            answer = model.json(prompt, payload)
            if not isinstance(answer, dict) or not isinstance(answer.get("evidence"), list) or not isinstance(answer.get("text"), str):
                raise ModelError("답 모양 오류", format=True)
            break
        except ModelError as error:
            if attempt or not error.format:
                return fallback([*trace, "write"])
    trace.append("write")
    by_id = {str(chunk["chunk_id"]): chunk for chunk in candidates}
    evidence = []
    for item in answer["evidence"]:
        if not isinstance(item, dict):
            continue
        chunk = by_id.get(str(item.get("chunk_id")))
        quote = item.get("quote")
        if chunk and isinstance(quote, str) and quote.strip() and re.sub(r"\s+", "", quote) in re.sub(r"\s+", "", chunk["content"]):
            evidence.append({"chunk_id": chunk["chunk_id"], "quote": quote, "score": chunk["score"]})
    no_evidence = bool(answer.get("no_evidence")) or not evidence
    conflict = bool(answer.get("conflict"))
    return {"text": NO_ANSWER if no_evidence or conflict else answer["text"], "evidence": evidence,
            "no_evidence": no_evidence, "conflict": conflict, "trace": [*trace, "verify", "end"]}
