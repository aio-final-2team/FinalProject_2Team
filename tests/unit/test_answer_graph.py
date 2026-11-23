"""자료 AI 답변의 인용·실패 경계를 검사한다."""

import json

import pytest

from agents.graphs.answer import NO_ANSWER, draft_answer
from agents.llm import ModelError

CHUNK = {"chunk_id": 1, "content": "겨울방학: 12월 24일부터", "score": 0.9,
         "document_title": "겨울방학 안내", "location": "1쪽 겨울방학 기간", "effective_from": "2026-11-02"}


class Writer:
    def __init__(self, answer):
        self.answer = answer
        self.calls = 0

    def json(self, system, user):
        self.calls += 1
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


class Checker:
    def __init__(self, answers=None):
        self.answers = answers or [{"passed": True, "issues": []}]
        self.calls = 0

    def json(self, system, user):
        self.calls += 1
        answer = self.answers[min(self.calls - 1, len(self.answers) - 1)]
        if isinstance(answer, Exception):
            raise answer
        return answer


def search(doc_type, query):
    return [CHUNK] if doc_type == "notice" else []


def test_valid_quote():
    result = draft_answer("겨울방학 언제부터", search, Writer({
        "text": "12월 24일부터예요.", "evidence": [{"chunk_id": 1, "quote": "12월 24일부터"}],
        "no_evidence": False, "conflict": False}), Checker())
    assert result["text"] == "12월 24일부터예요."
    assert result["evidence"][0]["chunk_id"] == 1
    assert result["trace"] == ["search", "write", "verify", "check", "end"]


def test_forged_quote_is_removed():
    result = draft_answer("겨울방학", search, Writer({
        "text": "가짜 답", "evidence": [{"chunk_id": 1, "quote": "12월 26일부터"}],
        "no_evidence": False, "conflict": False}), Checker())
    assert result["no_evidence"] and result["evidence"] == [] and result["text"] == NO_ANSWER


def test_empty_skips_writer():
    writer = Writer(ModelError("호출되면 안 됨"))
    assert draft_answer("없음", lambda kind, query: [], writer, Checker())["no_evidence"]
    assert writer.calls == 0


def test_transport_error_does_not_retry():
    writer = Writer(ModelError("전송 실패"))
    result = draft_answer("겨울방학", search, writer, Checker())
    assert result["no_evidence"] and writer.calls == 1


def test_format_error_retries_once():
    writer = Writer(ModelError("답 모양 실패", format=True))
    result = draft_answer("겨울방학", search, writer, Checker())
    assert result["no_evidence"] and writer.calls == 2


def test_conflict_uses_safe_text():
    result = draft_answer("겨울방학", search, Writer({
        "text": "추측", "evidence": [{"chunk_id": 1, "quote": "겨울방학"}],
        "no_evidence": False, "conflict": True}), Checker())
    assert result["conflict"] and result["text"] == NO_ANSWER


def test_search_retries_once():
    calls = []

    def flaky(kind, query):
        calls.append(kind)
        if len(calls) == 1:
            raise RuntimeError("일시 오류")
        return search(kind, query)

    result = draft_answer("겨울방학", flaky, Writer({
        "text": "답", "evidence": [{"chunk_id": 1, "quote": "겨울방학"}],
        "no_evidence": False, "conflict": False}), Checker())
    assert calls[:2] == ["notice", "notice"] and not result["no_evidence"]


class SequenceWriter:
    def __init__(self, answers):
        self.answers = answers
        self.payloads = []

    def json(self, system, user):
        self.payloads.append(json.loads(user))
        return self.answers[min(len(self.payloads) - 1, len(self.answers) - 1)]


def answer(text="12월 24일부터예요."):
    return {"text": text, "evidence": [{"chunk_id": 1, "quote": "12월 24일부터"}],
            "no_evidence": False, "conflict": False}


def issue(field):
    return {"passed": False, "issues": [{"field": field, "problem": f"{field} 확인 필요"}]}


@pytest.mark.parametrize("field", ["출처", "날짜", "대상", "누락", "민감정보"])
def test_each_checker_issue_reaches_writer(field):
    writer = SequenceWriter([answer("첫 초안"), answer()])
    checker = Checker([issue(field), {"passed": True, "issues": []}])
    result = draft_answer("겨울방학", search, writer, checker)
    assert result["text"] == "12월 24일부터예요."
    assert writer.payloads[1]["review_issues"] == issue(field)["issues"]
    assert checker.calls == 2


@pytest.mark.parametrize("revisions", [1, 2])
def test_rewrites_at_most_twice(revisions):
    writer = SequenceWriter([answer("첫 초안"), answer("두 번째"), answer()])
    checker = Checker([*[issue("누락") for _ in range(revisions)], {"passed": True, "issues": []}])
    result = draft_answer("겨울방학", search, writer, checker)
    assert result["text"] == ("두 번째" if revisions == 1 else "12월 24일부터예요.")
    assert len(writer.payloads) == revisions + 1
    assert checker.calls == revisions + 1


def test_repeated_checker_failure_goes_to_teacher():
    writer = SequenceWriter([answer()])
    checker = Checker([issue("날짜")])
    result = draft_answer("겨울방학", search, writer, checker)
    assert result["text"] == NO_ANSWER and result["no_evidence"]
    assert len(writer.payloads) == 3 and checker.calls == 3


def test_checker_model_error_goes_to_teacher():
    writer = SequenceWriter([answer()])
    checker = Checker([ModelError("검사 실패")])
    result = draft_answer("겨울방학", search, writer, checker)
    assert result["text"] == NO_ANSWER and result["no_evidence"]
    assert len(writer.payloads) == 1 and checker.calls == 2


def test_forged_quote_never_reaches_checker():
    checker = Checker()
    result = draft_answer("겨울방학", search, Writer({"text": "가짜 답", "evidence": [
        {"chunk_id": 1, "quote": "없는 날짜"}], "no_evidence": False, "conflict": False}), checker)
    assert result["no_evidence"] and checker.calls == 0


def test_checker_model_error_recovers_on_second_call():
    checker = Checker([ModelError("일시 오류"), {"passed": True, "issues": []}])
    result = draft_answer("겨울방학", search, Writer(answer()), checker)
    assert result["text"] == "12월 24일부터예요." and checker.calls == 2


@pytest.mark.parametrize("bad", [
    {"passed": True},
    {"passed": False, "issues": [{"field": "없는 항목", "problem": "확인 필요"}]},
])
def test_checker_bad_format_recovers_on_second_call(bad):
    checker = Checker([bad, {"passed": True, "issues": []}])
    result = draft_answer("겨울방학", search, Writer(answer()), checker)
    assert result["text"] == "12월 24일부터예요." and checker.calls == 2


def test_checker_bad_format_twice_goes_to_teacher():
    checker = Checker([{"passed": True}])
    result = draft_answer("겨울방학", search, Writer(answer()), checker)
    assert result["text"] == NO_ANSWER and result["no_evidence"] and checker.calls == 2
