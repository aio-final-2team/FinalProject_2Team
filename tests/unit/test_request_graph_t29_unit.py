"""요청 그래프의 분기·대기·중복 재개를 확인한다."""

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from agents.graphs.request import build_graph
from app.modules.requests.graph_agent import thread_id


def make_graph(route="inquiry"):
    calls = []
    status = {"value": "pending"}

    def prepare(request_id, selected):
        calls.append((request_id, selected))
        return "card-1"

    graph = build_graph(InMemorySaver(), lambda request_id: route, prepare,
                        lambda card_id: status["value"])
    return graph, calls, status


def test_each_request_type_uses_its_route():
    for route in ("inquiry", "consultation", "complaint"):
        graph, calls, _ = make_graph(route)
        result = graph.invoke({"request_id": "request-1"}, {"configurable": {"thread_id": route}})
        assert result["__interrupt__"]
        assert calls == [("request-1", route)]


def test_resume_reads_external_approval_and_does_not_prepare_again():
    graph, calls, status = make_graph()
    config = {"configurable": {"thread_id": "request-1"}}
    graph.invoke({"request_id": "request-1"}, config)
    waiting = graph.invoke(Command(resume=True), config)
    assert waiting["__interrupt__"] and len(calls) == 1
    status["value"] = "done"
    result = graph.invoke(Command(resume=True), config)
    assert result["outcome"] == "done" and len(calls) == 1


def test_unhandled_type_ends_without_card():
    graph, calls, _ = make_graph("medication")
    result = graph.invoke({"request_id": "request-1"}, {"configurable": {"thread_id": "request-1"}})
    assert result["route"] == "other" and "__interrupt__" not in result and not calls


def test_thread_id_is_stable_and_contains_no_user_text():
    request = "00000000-0000-4000-8000-000000000123"
    assert thread_id(request) == thread_id(request) == f"request:{request}"
