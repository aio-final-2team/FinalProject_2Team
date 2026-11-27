"""협업 그래프의 인계·합치기·돌려보내기 시험."""

import pytest

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from agents.graphs.request_collaboration import build_graph


def run_graph(route="inquiry", **steps):
    calls = []

    def prepare(request_id, selected, answer=None, classification=None):
        calls.append((request_id, selected))
        return "card-1"

    graph = build_graph(InMemorySaver(), lambda _: route, prepare, lambda _: "done", **steps)
    config = {"configurable": {"thread_id": "request-1"}}
    result = graph.invoke({"request_id": "request-1"}, config)
    return graph, config, result, calls


def test_supervisor_hands_consultation_to_memory_and_card():
    graph, config, result, calls = run_graph("consultation")
    assert result["__interrupt__"] and calls == [("request-1", "consultation")]
    assert graph.invoke(Command(resume=True), config)["outcome"] == "done"


def test_send_merges_search_and_memory_before_writing():
    seen = []

    def write(state):
        seen.append(state["parallel"])
        return {"passed": True}

    _, _, result, _ = run_graph(search=lambda _: [1], load_memory=lambda _: [2], write=write)
    assert result["__interrupt__"]
    assert seen == [{"chunks": [1], "search_failed": False, "memories": [2], "memory_failed": False}]


def test_checker_returns_once_then_passes():
    attempts = []

    def check(state):
        attempts.append(state["attempt"])
        return {"passed": bool(state["attempt"]), "issues": [] if state["attempt"] else ["고칠 문제"]}

    _, _, result, _ = run_graph(check=check)
    assert result["__interrupt__"] and attempts == [0, 1]


def test_checker_limit_hands_off_to_person():
    _, _, result, calls = run_graph(check=lambda _: {"passed": False, "issues": ["고칠 문제"]})
    assert result["handoff"] and result["attempt"] == 2
    assert result["__interrupt__"] and len(calls) == 1


def test_search_failure_hands_off_and_memory_failure_continues():
    def fail(_):
        raise RuntimeError("도구 실패")

    _, _, search_result, _ = run_graph(search=fail)
    assert search_result["handoff"] and search_result["__interrupt__"]
    _, _, memory_result, _ = run_graph(load_memory=fail)
    assert memory_result["parallel"]["memory_failed"] and not memory_result.get("handoff")


def test_same_fake_card_and_outcome_as_original_graph():
    from agents.graphs.request import build_graph as build_original

    for route in ("inquiry", "consultation", "complaint", "other"):
        for build in (build_original, build_graph):
            graph = build(InMemorySaver(), lambda _: route, lambda *_: "card-1", lambda _: "done")
            config = {"configurable": {"thread_id": f"{route}-{build.__module__}"}}
            result = graph.invoke({"request_id": "request-1"}, config)
            if route == "other":
                assert result["route"] == "other" and "__interrupt__" not in result
            else:
                assert result["card_id"] == "card-1" and result["__interrupt__"]
                assert graph.invoke(Command(resume=True), config)["outcome"] == "done"


def test_supervisor_skips_send_for_risky_inquiry_and_complaint():
    for route in ("inquiry", "complaint"):
        calls = []

        def forbidden(_):
            raise AssertionError("위험 요청에서는 자료·기억을 읽지 않아요")

        def prepare(request_id, selected, answer, classification):
            calls.append((selected, classification["risk_level"]))
            return "card-1"

        graph = build_graph(InMemorySaver(), lambda _: route, prepare, lambda _: "done",
                            search=forbidden, load_memory=forbidden, write=forbidden, check=forbidden,
                            high_risk=lambda _: {"risk_level": "urgent"})
        result = graph.invoke({"request_id": "request-1"},
                              {"configurable": {"thread_id": f"risk-{route}"}})
        assert result["__interrupt__"] and result["skip_draft"]
        assert calls == [(route, "urgent")]


@pytest.mark.parametrize("route", ["inquiry", "complaint"])
def test_uncertain_still_writes_and_checks_draft(route):
    # 판단 필요도 초안을 써 둬요. 승인은 재분류 전까지 카드 API가 막아요(긴급만 초안을 건너뛰어요).
    saved = []

    def prepare(request_id, selected, answer, classification):
        saved.append((answer["text"], classification["risk_level"]))
        return "card-1"

    graph = build_graph(InMemorySaver(), lambda _: route, prepare, lambda _: "done",
                        search=lambda _: [{"chunk_id": 1}], load_memory=lambda _: [],
                        write=lambda _: {"draft": {"text": "[TEST] 초안", "no_evidence": False}},
                        check=lambda _: {"passed": True},
                        high_risk=lambda _: {"risk_level": "uncertain", "risk_reason": "[TEST] 이유"})
    result = graph.invoke({"request_id": "request-1"}, {"configurable": {"thread_id": f"uncertain-{route}"}})
    assert result["__interrupt__"] and not result["skip_draft"]
    assert saved == [("[TEST] 초안", "uncertain")]


def test_memory_failure_keeps_draft_and_marks_warning():
    answers = []

    def broken(_):
        raise RuntimeError("기억 읽기 실패")

    def prepare(request_id, selected, answer, classification):
        answers.append(answer)
        return "card-1"

    graph = build_graph(InMemorySaver(), lambda _: "inquiry", prepare, lambda _: "done",
                        search=lambda _: [{"chunk_id": 1}], load_memory=broken,
                        write=lambda _: {"draft": {"text": "확인된 답", "evidence": [],
                                                    "no_evidence": False, "conflict": False}},
                        check=lambda _: {"passed": True, "issues": []})
    graph.invoke({"request_id": "request-1"}, {"configurable": {"thread_id": "memory-warning"}})
    assert answers[0]["text"] == "확인된 답"
    assert answers[0]["check_result"]["memory_unavailable"] is True


def test_partial_answer_reaches_teacher_card_with_evidence_and_warning():
    from agents.graphs.answer import draft_answer

    question = "재롱잔치 날짜랑 준비물이랑 그날 하원 시간 바뀌는지 알려주세요"
    chunks = [{"chunk_id": 21, "content": "재롱잔치는 12월 12일이고 준비물은 흰 양말입니다.", "score": 0.9}]

    class Writer:
        def json(self, *_):
            return {"text": "재롱잔치는 12월 12일이고 준비물은 흰 양말이에요.",
                    "evidence": [{"chunk_id": 21, "quote": chunks[0]["content"]}],
                    "facts": [{"text": "재롱잔치는 12월 12일이고 준비물은 흰 양말이에요.",
                               "evidence": [{"chunk_id": 21, "quote": chunks[0]["content"]}]}],
                    "no_evidence": True, "conflict": False, "partial": True,
                    "unanswered": ["그날 하원 시간 바뀌는지"]}

    class Checker:
        def json(self, *_):
            return {"passed": True, "issues": []}

    draft = draft_answer(question, lambda *_: chunks, Writer(), Checker())
    cards = []
    graph = build_graph(
        InMemorySaver(), lambda _: "inquiry",
        lambda _id, route, answer, _fields: cards.append((route, answer)) or "card-1",
        lambda _: "done", search=lambda _: chunks, load_memory=lambda _: [],
        write=lambda _: {"draft": draft},
        check=lambda state: {"passed": state["draft"]["check_result"]["passed"], "issues": []},
    )

    result = graph.invoke({"request_id": "request-1"}, {"configurable": {"thread_id": "partial"}})

    assert result["__interrupt__"] and not result.get("handoff")
    route, answer = cards[0]
    assert route == "inquiry"
    assert answer["partial"] and answer["no_evidence"]
    assert answer["evidence"] == draft["evidence"]
    assert "재롱잔치는 12월 12일" in answer["text"]
    assert "선생님이 확인한 뒤 알려 드릴게요." in answer["text"]
    assert answer["check_result"]["passed"]


@pytest.mark.parametrize("question, reply, expected_count", [
    ("겨울방학은 언제부터 언제까지예요?", {"text": "날짜가 달라요", "no_evidence": False,
      "conflict": True, "evidence": [{"chunk_id": 1, "quote": "12월 24일"},
                                      {"chunk_id": 2, "quote": "12월 26일"}]}, 2),
    ("소풍 준비물이 뭐예요?", {"text": "확인 필요", "no_evidence": True,
      "conflict": False, "evidence": [{"chunk_id": 1, "quote": "12월 24일"},
                                       {"chunk_id": 2, "quote": "12월 26일"}]}, 2),
    ("김장 준비물이 뭐예요?", {"text": "앞치마와 팔토시", "no_evidence": False,
      "conflict": False, "evidence": [{"chunk_id": 1, "quote": "12월 24일"}]}, 1),
])
def test_handoff_matches_original_answer_with_fake_model(question, reply, expected_count):
    from agents.graphs.answer import _verify, draft_answer

    chunks = [{"chunk_id": 1, "content": "12월 24일 앞치마와 팔토시", "score": 0.9},
              {"chunk_id": 2, "content": "12월 26일", "score": 0.8}]

    class FakeModel:
        def json(self, *_):
            return reply

    class FakeChecker:
        def json(self, *_):
            return {"passed": True, "issues": []}

    original = draft_answer(question, lambda kind, _: chunks if kind == "notice" else [],
                            FakeModel(), FakeChecker())
    captured = []
    graph = build_graph(InMemorySaver(), lambda _: "inquiry",
                        lambda _id, _route, answer, _fields: captured.append(answer) or "card-1",
                        lambda _: "done", search=lambda _: chunks,
                        write=lambda _: {"draft": _verify(reply, chunks, [])},
                        check=lambda _: {"passed": True, "issues": []})
    config = {"configurable": {"thread_id": question}}
    state = graph.invoke({"request_id": "request-1"}, config)
    answer = captured[0]
    assert state["__interrupt__"]
    assert len(answer["evidence"]) == expected_count
    assert answer["evidence"] == original["evidence"]
    assert answer["no_evidence"] == original["no_evidence"]
    assert answer["conflict"] == original["conflict"]
    assert answer["check_result"] == original["check_result"]
    assert answer["text"] == ("" if answer.get("handoff") else original["text"])
    assert "evidence" not in graph.get_state(config).values
