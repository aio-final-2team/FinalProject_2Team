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
        self.system = ""

    def json(self, system, user):
        self.calls += 1
        self.system = system
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


class Checker:
    def __init__(self, answers=None):
        self.answers = answers or [{"passed": True, "issues": []}]
        self.calls = 0
        self.payloads = []
        self.system = ""

    def json(self, system, user):
        self.calls += 1
        self.system = system
        self.payloads.append(json.loads(user))
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


def test_writer_prompt_requires_named_event_match():
    writer = Writer({"text": "확인 중이에요.", "evidence": [{"chunk_id": 1, "quote": "겨울방학"}],
                     "no_evidence": False, "conflict": False})
    draft_answer("우리 동네 장터 일정이 언제예요?", search, writer, Checker())
    # 행사 이름이 다른 자료를 근거로 대신 답하지 않는 규칙이 작성 프롬프트에 포함된다.
    assert "같은 행사·대상임을 확인할 수 있는 이름이나 연결 정보" in writer.system
    assert "no_evidence = true" in writer.system


def test_partial_answer_keeps_cited_facts_and_adds_fixed_unanswered_text():
    question = "재롱잔치 날짜랑 준비물이랑 그날 하원 시간 바뀌는지 알려주세요"
    chunks = [{"chunk_id": 21, "content": "재롱잔치는 12월 12일이고 준비물은 흰 양말입니다.", "score": 0.9}]
    writer = Writer({"text": "재롱잔치는 12월 12일이고 준비물은 흰 양말이에요.",
                     "evidence": [{"chunk_id": 21, "quote": "재롱잔치는 12월 12일이고 준비물은 흰 양말입니다."}],
                     "facts": [{"text": "재롱잔치는 12월 12일이고 준비물은 흰 양말이에요.",
                                "evidence": [{"chunk_id": 21, "quote": "재롱잔치는 12월 12일이고 준비물은 흰 양말입니다."}]}],
                     "no_evidence": True, "conflict": False, "partial": True,
                     "unanswered": ["그날 하원 시간 바뀌는지"]})
    checker = Checker()

    result = draft_answer(question, lambda *_: chunks, writer, checker)

    assert result["partial"] and result["no_evidence"]
    assert result["text"] == ("재롱잔치는 12월 12일이고 준비물은 흰 양말이에요.\n"
                              "질문하신 ‘그날 하원 시간 바뀌는지’에 대해서는 자료에서 확인하지 못했어요. "
                              "선생님이 확인한 뒤 알려 드릴게요.")
    assert result["evidence"][0]["quote"] == chunks[0]["content"]
    assert result["check_result"]["passed"] and checker.calls == 1
    assert checker.payloads[0]["partial"] is True
    assert "미답 자체는 누락 오류로 돌려보내지 않는다" in checker.system
    assert "facts의 각 사실 문장을 같은 facts 항목의 evidence 인용과 따로 대조" in checker.system


def test_partial_answer_requires_verbatim_citation_and_question_substring():
    question = "재롱잔치 날짜와 하원 시간이 바뀌는지 알려주세요"
    chunks = [{"chunk_id": 21, "content": "재롱잔치는 12월 12일입니다.", "score": 0.9}]
    reply = {"text": "재롱잔치는 12월 12일이에요.",
             "evidence": [{"chunk_id": 21, "quote": "12월 12일"}],
             "facts": [{"text": "재롱잔치는 12월 12일이에요.",
                        "evidence": [{"chunk_id": 21, "quote": "12월 12일"}]}],
             "no_evidence": True, "conflict": False, "partial": True,
             "unanswered": ["하원 시간이 바뀌는지"]}
    from agents.graphs.answer import _verify

    verified = _verify(reply, chunks, [], question)
    assert verified["partial"] and verified["evidence"]
    invalid = _verify({**reply, "facts": [{"text": "재롱잔치는 12월 12일이에요.",
                                           "evidence": [{"chunk_id": 21, "quote": "12월 13일"}]}]},
                      chunks, [], question)
    assert invalid["no_evidence"] and not invalid["partial"] and invalid["text"] == NO_ANSWER
    invalid_fact = _verify({**reply, "facts": [{"text": "근처 과학관에 갑니다.", "evidence": []}]},
                           chunks, [], question)
    assert invalid_fact["no_evidence"] and not invalid_fact["partial"] and invalid_fact["text"] == NO_ANSWER
    mixed_fact = _verify({**reply, "facts": [{"text": "재롱잔치는 12월 12일이에요. 근처 과학관에 갑니다.",
                                              "evidence": [{"chunk_id": 21, "quote": "12월 12일"}]}]},
                         chunks, [], question)
    assert mixed_fact["no_evidence"] and not mixed_fact["partial"] and mixed_fact["text"] == NO_ANSWER
    unrelated = _verify({**reply, "unanswered": ["독감 접종 날짜"]}, chunks, [], question)
    assert unrelated["no_evidence"] and not unrelated["partial"] and unrelated["text"] == NO_ANSWER


def test_checker_rejection_does_not_release_partial_facts():
    question = "재롱잔치 날짜와 하원 시간이 바뀌는지 알려주세요"
    chunks = [{"chunk_id": 21, "content": "재롱잔치는 12월 12일입니다.", "score": 0.9}]
    writer = Writer({"text": "재롱잔치는 12월 12일이에요. 근처 과학관에도 갑니다.",
                     "evidence": [{"chunk_id": 21, "quote": "재롱잔치는 12월 12일입니다."}],
                     "facts": [{"text": "근처 과학관에도 갑니다.",
                                "evidence": [{"chunk_id": 21, "quote": "재롱잔치는 12월 12일입니다."}]}],
                     "no_evidence": True, "conflict": False, "partial": True,
                     "unanswered": ["하원 시간이 바뀌는지"]})
    checker = Checker([{"passed": False, "issues": [{"field": "출처", "problem": "근거 없는 사실 문장이 있어요."}]}])

    result = draft_answer(question, lambda *_: chunks, writer, checker)

    assert result["text"] == NO_ANSWER and result["no_evidence"] and not result.get("partial")
    assert writer.calls == 3 and checker.calls == 3


def test_same_chunk_cited_twice_is_kept_once():
    # card_evidence 기본키가 (card_id, chunk_id)라 같은 조각이 두 번 들어가면 저장이 실패한다.
    result = draft_answer("겨울방학", search, Writer({
        "text": "12월 24일부터예요.", "evidence": [{"chunk_id": 1, "quote": "12월 24일"},
                                                  {"chunk_id": "1", "quote": "겨울방학"}],
        "no_evidence": False, "conflict": False}), Checker())
    assert [item["chunk_id"] for item in result["evidence"]] == [1]
    assert result["evidence"][0]["quote"] == "12월 24일"


def test_forged_quote_is_removed():
    result = draft_answer("겨울방학", search, Writer({
        "text": "가짜 답", "evidence": [{"chunk_id": 1, "quote": "12월 26일부터"}],
        "no_evidence": False, "conflict": False}), Checker())
    assert result["no_evidence"] and result["evidence"] == [] and result["text"] == NO_ANSWER
    assert [issue["field"] for issue in result["check_result"]["issues"]] == ["출처"]


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
    assert [issue["field"] for issue in result["check_result"]["issues"]] == ["출처"]


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


LINES = {"chunk_id": 2, "content": "1. 아침 체온이 37.5℃ 이상이면 등원하지 않습니다.\n2. 열이 내려도 하루는 쉽니다.\n"
         "3. 해열제 없이 24시간 동안 열이 없으면 다시 등원할 수 있습니다.", "score": 0.8,
         "document_title": "운영 규정", "location": "건강", "effective_from": "2026-03-02"}


class Writers:
    """부를 때마다 다음 답을 준다."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = 0
        self.payloads = []

    def json(self, system, user):
        self.payloads.append(json.loads(user))
        self.calls += 1
        return self.answers[min(self.calls - 1, len(self.answers) - 1)]


def health_answer(quote, chunk_id=2):
    return {"text": "37.5℃ 이상이면 쉬어요.", "evidence": [{"chunk_id": chunk_id, "quote": quote}],
            "no_evidence": False, "conflict": False}


def test_quote_stitched_from_separate_lines_is_accepted():
    # 팀 서버에서 버려졌던 인용(11/25): 1번 줄과 3번 줄을 이어 붙였어요
    quote = "1. 아침 체온이 37.5℃ 이상이면 등원하지 않습니다.\n3. 해열제 없이 24시간 동안 열이 없으면 다시 등원할 수 있습니다."
    result = draft_answer("열이 나면 등원해도 되나요", lambda t, q: [LINES] if t == "policy" else [],
                          Writers(health_answer(quote)), Checker())
    assert not result["no_evidence"] and result["evidence"][0]["quote"] == quote


def test_stitched_quote_with_a_made_up_line_is_rejected():
    quote = "1. 아침 체온이 37.5℃ 이상이면 등원하지 않습니다.\n열이 나도 등원할 수 있습니다."
    result = draft_answer("열이 나면", lambda t, q: [LINES] if t == "policy" else [],
                          Writers(health_answer(quote)), Checker())
    assert result["no_evidence"] and result["evidence"] == [] and result["text"] == NO_ANSWER


def test_misquote_is_asked_again_with_the_reason_then_accepted():
    writer = Writers(health_answer("체온이 37.5도 넘으면 등원 안 함"), health_answer("아침 체온이 37.5℃ 이상이면 등원하지 않습니다."))
    result = draft_answer("열이 나면", lambda t, q: [LINES] if t == "policy" else [], writer, Checker())
    assert writer.calls == 2 and not result["no_evidence"]
    assert "글자 그대로" in writer.payloads[1]["review_issues"][0]["problem"]
    assert result["check_result"] == {"passed": True, "issues": [], "attempt": 2}


def test_misquote_every_time_ends_as_no_evidence():
    writer = Writers(health_answer("체온이 37.5도 넘으면 등원 안 함"))
    result = draft_answer("열이 나면", lambda t, q: [LINES] if t == "policy" else [], writer, Checker())
    assert writer.calls == 3 and result["no_evidence"] and result["text"] == NO_ANSWER
    assert result["check_result"]["passed"] is False


def test_model_saying_no_evidence_is_not_asked_again():
    writer = Writers({"text": "", "evidence": [], "no_evidence": True, "conflict": False})
    result = draft_answer("열이 나면", lambda t, q: [LINES] if t == "policy" else [], writer, Checker())
    assert writer.calls == 1 and result["no_evidence"]
