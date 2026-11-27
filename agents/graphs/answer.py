"""문의 자료를 찾고, 인용과 답변을 검사한 뒤 담임에게 초안을 넘긴다."""

import json
import os
import re
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from agents.llm import ModelError, OpenAIModel, feature
from agents.guardrails.injection import suspicious_chunk
from agents.guardrails.sensitive import SENSITIVE, mask_sensitive

NO_ANSWER = "자료에서 확인되지 않아 선생님 확인이 필요해요."
PROMPTS = Path(__file__).resolve().parents[1] / "prompts"
WRITE_FORMAT = "\nJSON 하나로 답한다: {\"text\": str, \"evidence\": [{\"chunk_id\": int, \"quote\": str}], \"facts\": [{\"text\": str, \"evidence\": [{\"chunk_id\": int, \"quote\": str}]}], \"no_evidence\": bool, \"conflict\": bool, \"partial\": bool, \"unanswered\": [str]}"
WRITE_FORMAT += '\n보낸 알림장 인용은 {"chunk_id": null, "source": "daily_note", "note_id": "입력의 UUID", "quote": "원문 구절"}로 적는다. 기억은 사실 근거가 아니다.'
WRITE_FORMAT += '\n담임 관찰 기록 인용은 {"chunk_id": null, "source": "daily_record", "record_id": "입력의 UUID", "quote": "원문 구절"}로 적는다. quote는 원문 그대로, text는 담임 메모 말투 대신 보호자에게 보낼 말로 쓴다.'
WRITE_FORMAT += '\n투약·귀가 요청 인용은 {"chunk_id": null, "source": "care_request", "request_id": "입력의 UUID", "quote": "원문 구절"}로 적는다. quote는 원문 그대로 적는다.'
CHECK_FORMAT = "\nJSON 하나로 답한다: {\"passed\": bool, \"issues\": [{\"field\": \"출처|날짜|대상|누락|민감정보\", \"problem\": str}]}"
CHECK_FIELDS = {"출처", "날짜", "대상", "누락", "민감정보"}
MAX_REWRITES = 2
KST = ZoneInfo("Asia/Seoul")
WEEKDAYS = "월화수목금토일"
# 문서 조각이 아닌 아이 개인 근거. card_evidence 대신 카드 초안에 남기고 이 칸들로 원 후보와 대조해요.
PERSONAL = {"daily_note": ("note_id", "note_date"), "daily_record": ("record_id", "record_date"),
            "care_request": ("request_id", "request_date")}
WRITE_FORMAT += "\n입력의 today는 이 질문을 받은 날이다. 질문과 자료에 나오는 오늘·내일·이번 주는 today 기준 날짜로 바꿔 읽는다."


def child_day_question(body):
    return bool(re.search(r"낮잠.*(?:잤|잔|잠들)|(?:점심|밥|식사).*먹었|(?:오늘|어제|그제).*(?:뭐|무엇).*했|(?:오늘|어제|그제).*어땠", body))


def child_about_question(body):
    """관찰 기록은 하루 질문보다 조금 넓게, 아이의 몸·마음·친구 이야기를 물을 때도 붙여요."""
    return child_day_question(body) or bool(re.search(r"친구|지내|기침|콧물|열이|열나|아프|아파|다쳤|울었|낮잠|먹었", body))


def note_chunk(note_id, note_date, content):
    quote = "\n".join(line["value"] for line in content.get("items", []) if isinstance(line.get("value"), str))
    if not quote.strip() or suspicious_chunk(quote):
        return None
    day = date.fromisoformat(str(note_date))
    return {"chunk_id": None, "source": "daily_note", "note_id": str(note_id), "note_date": str(day),
            "title": f"{day.month}월 {day.day}일 알림장", "quote": quote, "content": quote, "score": 1.0}


def record_chunk(record_id, record_date, body):
    """담임 관찰 기록은 보호자에게 바로 안 보이는 메모라, 담임이 검토하는 초안의 근거로만 써요.
    선생님이 쓴 글이라 알림장 그래프처럼 민감정보 형식을 가려서 넘겨요(T55 G-5)."""
    quote = mask_sensitive(body or "").strip()
    if not quote or suspicious_chunk(quote):
        return None
    day = date.fromisoformat(str(record_date))
    return {"chunk_id": None, "source": "daily_record", "record_id": str(record_id), "record_date": str(day),
            "title": f"{day.month}월 {day.day}일 관찰 기록", "quote": quote, "content": quote, "score": 1.0}


def gather_on():
    """ANSWER_GATHER=agent(기본)면 자료 찾는 AI가 근거를 모으고, fixed면 질문 문장으로 고정 검색한다."""
    return os.getenv("ANSWER_GATHER", "agent") == "agent"


def _evidence_key(item):
    source = item.get("source")
    if source in PERSONAL and item.get("chunk_id") is None:
        return source, str(item.get(PERSONAL[source][0]))
    return "document", str(item.get("chunk_id"))


def fallback(trace):
    return {"text": NO_ANSWER, "evidence": [], "no_evidence": True, "conflict": False,
            "check_result": {"passed": False, "issues": [{"field": "출처",
                                                               "problem": "자료 답변을 확인하지 못했어요."}],
                             "attempt": 0}, "trace": [*trace, "end"]}


def _prompt(file, start, end=None):
    source = (PROMPTS / file).read_text(encoding="utf-8")
    return source[source.index(start):source.index(end) if end else None]


def day_label(day=None):
    """질문을 받은 날. 없으면 한국 시각 오늘이다. 예: 2026-11-27(금)"""
    day = day or datetime.now(KST).date()
    return f"{day.isoformat()}({WEEKDAYS[day.weekday()]})"


def _common(today=None):
    """공통 규칙의 '오늘' 칸을 채운다. 비워 두면 모델이 '내일'을 자료 문구 그대로 믿는다."""
    return _prompt("common.md", "# 공통 규칙").replace("{today}", day_label(today))


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


def _verified_evidence(items, by_id, *, strict=False):
    evidence = []
    seen = set()
    valid = True
    for item in items:
        if not isinstance(item, dict):
            valid = False
            continue
        key = _evidence_key(item)
        chunk = by_id.get(key)
        quote = item.get("quote")
        if not chunk or not isinstance(quote, str) or not quote.strip() or not _quoted(quote, chunk["content"]):
            valid = False
            continue
        if key in seen:
            continue  # card_evidence PK가 (card_id, chunk_id)라 같은 조각은 한 번만 남긴다
        seen.add(key)
        entry = {"chunk_id": chunk["chunk_id"], "quote": quote, "score": chunk["score"]}
        if key[0] in PERSONAL:
            entry.update({k: chunk[k] for k in ("source", *PERSONAL[key[0]], "title")})
        evidence.append(entry)
    return evidence, valid if strict else True


def _single_sentence(text):
    return len([part for part in re.split(r"[.!?。！？\n]+", text) if part.strip()]) == 1


def _verify(answer, candidates, trace, question=None):
    by_id = {_evidence_key(chunk): chunk for chunk in candidates}
    evidence, _ = _verified_evidence(answer["evidence"], by_id)
    conflict = bool(answer.get("conflict"))
    no_evidence = bool(answer.get("no_evidence")) or not evidence
    unanswered = answer.get("unanswered")
    question_text = re.sub(r"\s+", "", question or "")
    unanswered = list(dict.fromkeys(
        item.strip() for item in unanswered
        if isinstance(item, str) and item.strip()
        and re.sub(r"\s+", "", item.strip()) in question_text
    )) if isinstance(unanswered, list) else []
    raw_facts = answer.get("facts")
    facts, facts_valid = [], isinstance(raw_facts, list) and bool(raw_facts)
    if facts_valid:
        for fact in raw_facts:
            if (not isinstance(fact, dict) or not isinstance(fact.get("text"), str)
                    or not fact["text"].strip() or not _single_sentence(fact["text"])
                    or not isinstance(fact.get("evidence"), list)
                    or not fact["evidence"]):
                facts_valid = False
                break
            citations, citations_valid = _verified_evidence(fact["evidence"], by_id, strict=True)
            if not citations_valid or not citations:
                facts_valid = False
                break
            facts.append({"text": fact["text"].strip(), "evidence": citations})
    if not facts_valid:
        facts = []
    if bool(answer.get("partial")) and facts_valid:
        evidence = []
        seen = set()
        for fact in facts:
            for item in fact["evidence"]:
                key = _evidence_key(item)
                if key not in seen:
                    seen.add(key)
                    evidence.append(item)
        no_evidence = bool(answer.get("no_evidence")) or not evidence
    partial = (bool(answer.get("partial")) and facts_valid and bool(evidence) and bool(unanswered)
               and (no_evidence or conflict))
    trace.append("verify")
    # 모델은 근거가 있다고 했는데 인용문이 하나도 글자 그대로가 아니면, 근거 없음으로 끝내지 않고 다시 쓰게 한다.
    misquoted = (bool(answer["evidence"]) and not evidence and not conflict
                 or bool(answer.get("partial")) and isinstance(raw_facts, list) and bool(raw_facts) and not facts_valid)
    supported_text = "\n".join(fact["text"] for fact in facts) if partial else answer["text"]
    text = supported_text if not no_evidence or partial else NO_ANSWER
    if partial:
        text += "\n" + "\n".join(
            f"질문하신 ‘{item}’에 대해서는 자료에서 확인하지 못했어요. 선생님이 확인한 뒤 알려 드릴게요."
            for item in unanswered
        )
    return {"text": NO_ANSWER if conflict else text, "evidence": evidence,
            "no_evidence": no_evidence, "conflict": conflict, "partial": partial,
            "facts": facts if partial else [], "unanswered": unanswered if partial else [], "misquoted": misquoted}


def _review(model, question, draft, candidates, attempt, trace, today=None):
    prompt = _common(today) + _prompt("checker.md", "## 입력", "## 알림장: 메모와 대조한다") + CHECK_FORMAT
    prompt += "\nsource=daily_note는 요청 아이에게 실제 보낸 알림장 근거다. note_id와 note_date·quote를 대조하고 다른 날짜의 일을 오늘 일로 단정하지 않는다."
    prompt += "\nsource=daily_record는 담임이 그 아이에 대해 남긴 관찰 기록이다. record_id와 record_date·quote를 대조하고 기록에 없는 일을 초안이 덧붙였는지 본다."
    prompt += "\nsource=care_request는 그 아이 보호자가 낸 투약·귀가 요청과 처리 상태다. request_id와 request_date·quote를 대조하고 요청·처리 상태에 없는 일을 초안이 덧붙였는지 본다."
    if draft.get("partial"):
        prompt += ("\n부분 답변에서는 unanswered에 든 질문 항목이 고정 담임 확인 문구와 함께 남아 있으면 그 항목의 미답 자체는 누락 오류로 돌려보내지 않는다. "
                   "facts의 각 사실 문장을 같은 facts 항목의 evidence 인용과 따로 대조하고, 인용이 없거나 실제 조각이 뒷받침하지 않는 사실은 통과시키지 않는다. "
                   "질문한 항목과 관련된 자료끼리 날짜·숫자·사실이 서로 다르면 부분 답을 통과시키지 말고 날짜 또는 출처 문제로 돌려보낸다. "
                   "고정 문구 형식은 ‘질문하신 …에 대해서는 자료에서 확인하지 못했어요. 선생님이 확인한 뒤 알려 드릴게요.’이다.")
    payload = {"question": question, "today": day_label(today), "draft": draft["text"], "evidence": draft["evidence"],
               "chunks": candidates, "attempt": attempt, "partial": draft.get("partial", False),
               "facts": draft.get("facts", []),
               "unanswered": draft.get("unanswered", []),
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
def draft_answer(question: str, search, writer=None, checker=None, *, memories=(), prior_answer=None, preferences=(), child_notes=(),
                 today: date | None = None, gather_tools=None) -> dict:
    """gather_tools가 있고 ANSWER_GATHER가 agent(기본)면 자료 찾는 AI가 도구로 근거를 모은다.
    못 모았거나(None) 하나도 없으면([]) 아래 고정 검색 그대로 간다."""
    trace = []
    candidates = None
    if gather_tools is not None and gather_on():
        from agents.graphs.gather import gather
        candidates = gather(question, gather_tools, OpenAIModel("GATHER"), today=today, trace=trace) or None
    if candidates is None:
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
                            key=lambda item: (item.get("source") in PERSONAL, item["score"]), reverse=True)[:8]
    if not candidates:
        return fallback(trace)
    common = _common(today)
    write_prompt = common + _prompt("documents.md", "## 입력", "## 알림장 초안 쓰기") + WRITE_FORMAT
    writer = writer if writer is not None else OpenAIModel("DOCUMENT")
    checker = checker if checker is not None else OpenAIModel("CHECKER")
    issues = []
    for attempt in range(MAX_REWRITES + 1):
        answer = _ask_writer(writer, write_prompt, {"question": mask_sensitive(question), "today": day_label(today), "chunks": candidates,
                                                    "memories": list(memories),
                                                    "prior_answer": prior_answer, "preferences": list(preferences), "child_notes": list(child_notes),
                                                    "review_issues": issues,
                                                    "untrusted_data_fields": ["question", "chunks", "memories", "prior_answer", "preferences", "child_notes"]}, trace)
        if answer is None:
            return fallback(trace)
        draft = _verify(answer, candidates, trace, question)
        misquoted = draft.pop("misquoted")
        if misquoted and attempt < MAX_REWRITES:
            issues = [{"field": "출처", "problem": "인용문이 자료 조각과 글자 그대로 일치하지 않아요. "
                       "조각의 한 줄(또는 이어진 구절)을 고치지 말고 그대로 복사해 quote에 넣어 주세요."}]
            last_check = _check_result(False, issues, attempt + 1)
            continue
        if (draft["no_evidence"] and not draft["partial"]) or draft["conflict"]:
            problem = "자료끼리 내용이 달라요." if draft["conflict"] else "자료에서 근거를 찾지 못했어요."
            return {**draft, "check_result": _check_result(False, [{"field": "출처", "problem": problem}], attempt + 1),
                    "trace": [*trace, "end"]}
        issues = _review(checker, mask_sensitive(question), draft, candidates, attempt + 1, trace, today)
        if issues is None:
            return fallback(trace)
        if not issues:
            return {**draft, "check_result": _check_result(True, [], attempt + 1),
                    "trace": [*trace, "end"]}
        last_check = _check_result(False, issues, attempt + 1)
    return {**fallback(trace), "check_result": last_check}
