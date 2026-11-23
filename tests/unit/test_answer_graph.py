"""자료 AI 답변의 인용·실패 경계를 검사한다."""

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


def search(doc_type, query):
    return [CHUNK] if doc_type == "notice" else []


def test_valid_quote():
    result = draft_answer("겨울방학 언제부터", search, Writer({
        "text": "12월 24일부터예요.", "evidence": [{"chunk_id": 1, "quote": "12월 24일부터"}],
        "no_evidence": False, "conflict": False}))
    assert result["text"] == "12월 24일부터예요."
    assert result["evidence"][0]["chunk_id"] == 1
    assert result["trace"] == ["search", "write", "verify", "end"]


def test_forged_quote_is_removed():
    result = draft_answer("겨울방학", search, Writer({
        "text": "가짜 답", "evidence": [{"chunk_id": 1, "quote": "12월 26일부터"}],
        "no_evidence": False, "conflict": False}))
    assert result["no_evidence"] and result["evidence"] == [] and result["text"] == NO_ANSWER


def test_empty_skips_writer():
    writer = Writer(ModelError("호출되면 안 됨"))
    assert draft_answer("없음", lambda kind, query: [], writer)["no_evidence"]
    assert writer.calls == 0


def test_transport_error_does_not_retry():
    writer = Writer(ModelError("전송 실패"))
    result = draft_answer("겨울방학", search, writer)
    assert result["no_evidence"] and writer.calls == 1


def test_format_error_retries_once():
    writer = Writer(ModelError("답 모양 실패", format=True))
    result = draft_answer("겨울방학", search, writer)
    assert result["no_evidence"] and writer.calls == 2


def test_conflict_uses_safe_text():
    result = draft_answer("겨울방학", search, Writer({
        "text": "추측", "evidence": [{"chunk_id": 1, "quote": "겨울방학"}],
        "no_evidence": False, "conflict": True}))
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
        "no_evidence": False, "conflict": False}))
    assert calls[:2] == ["notice", "notice"] and not result["no_evidence"]
