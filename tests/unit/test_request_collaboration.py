"""협업 그래프의 인계·합치기·돌려보내기 시험."""

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
