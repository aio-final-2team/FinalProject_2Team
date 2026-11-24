"""요청 협업 그래프의 인계와 병렬 합치기 뼈대."""

from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send, interrupt

from agents.graphs.request import ROUTES

MAX_REWRITES = 2


def _merge(left, right):
    """각 작업의 결과를 별도 칸에 합친다."""
    return {**left, **right}


class CollaborationState(TypedDict, total=False):
    request_id: str
    route: str
    card_id: str
    outcome: str
    parallel: Annotated[dict, _merge]
    attempt: int
    issues: list
    passed: bool
    handoff: bool
    draft: dict
    answer: dict


def build_graph(checkpointer, route_request, prepare_card, card_status,
                search=None, load_memory=None, write=None, check=None):
    """단계별 함수를 주입한다. 기본 함수는 기존 카드 처리 경로를 유지한다."""
    builder = StateGraph(CollaborationState)

    def supervisor(state):
        route = route_request(state["request_id"])
        return {"route": route if route in ROUTES else "other", "attempt": 0}

    def route_after_supervisor(state):
        if state["route"] == "consultation":
            return "memory_consultation"
        if state["route"] in ("inquiry", "complaint"):
            return [Send("docs_search", {"request_id": state["request_id"]}),
                    Send("memory_load", {"request_id": state["request_id"]})]
        return END

    def docs_search(state):
        try:
            chunks = search(state["request_id"]) if search else []
            return {"parallel": {"chunks": chunks, "search_failed": search is not None and not chunks}}
        except Exception:
            return {"parallel": {"chunks": [], "search_failed": True}}

    def memory_load(state):
        try:
            memories = load_memory(state["request_id"]) if load_memory else []
            return {"parallel": {"memories": memories, "memory_failed": False}}
        except Exception:
            return {"parallel": {"memories": [], "memory_failed": True}}

    def memory_consultation(state):
        return memory_load(state)

    def after_join(state):
        return "handoff" if (state["parallel"].get("search_failed")
                             or state["parallel"].get("memory_failed")
                             or state.get("draft", {}).get("no_evidence")
                             or state.get("draft", {}).get("conflict")) else "checker"

    def document_write(state):
        if write is None:
            return {"passed": True}
        try:
            return write(state)
        except Exception:
            return {"draft": {"text": "", "evidence": [], "no_evidence": True, "conflict": False},
                    "handoff": True}

    def checker(state):
        if check is None:
            return {"passed": True, "issues": []}
        try:
            return check(state)
        except Exception:
            return {"passed": False, "issues": [{"field": "출처", "problem": "검사하지 못했어요."}],
                    "attempt": MAX_REWRITES, "handoff": True}

    def after_check(state):
        if state.get("passed"):
            return "finish_answer"
        if state.get("attempt", 0) >= MAX_REWRITES:
            return "handoff"
        return "return_to_document"

    def return_to_document(state):
        return {"attempt": state.get("attempt", 0) + 1}

    def finish_answer(state):
        draft = state.get("draft", {})
        return {"answer": {**draft, "check_result": {"passed": True, "issues": [],
                                                       "attempt": state.get("attempt", 0) + 1}}}

    def handoff(state):
        return {"handoff": True, "answer": {"text": "", "evidence": [], "no_evidence": True, "handoff": True,
                                             "conflict": False, "check_result":
                                             {"passed": False, "issues": state.get("issues", []),
                                              "attempt": state.get("attempt", 0) + 1}}}

    def prepare(state):
        return {"card_id": prepare_card(state["request_id"], state["route"], state.get("answer")) or ""}

    def wait_for_approval(state):
        if not state.get("card_id"):
            return {"outcome": "no_card"}
        interrupt({"card_id": state["card_id"]})
        return {"outcome": card_status(state["card_id"])}

    builder.add_node("supervisor", supervisor)
    builder.add_node("docs_search", docs_search)
    builder.add_node("memory_load", memory_load)
    builder.add_node("memory_consultation", memory_consultation)
    builder.add_node("document_write", document_write)
    builder.add_node("checker", checker)
    builder.add_node("return_to_document", return_to_document)
    builder.add_node("handoff", handoff)
    builder.add_node("finish_answer", finish_answer)
    builder.add_node("prepare_card", prepare)
    builder.add_node("wait_for_approval", wait_for_approval)
    builder.add_edge(START, "supervisor")
    builder.add_conditional_edges("supervisor", route_after_supervisor)
    builder.add_edge("docs_search", "document_write")
    builder.add_edge("memory_load", "document_write")
    builder.add_edge("memory_consultation", "prepare_card")
    builder.add_conditional_edges("document_write", after_join, {"checker": "checker", "handoff": "handoff"})
    builder.add_conditional_edges("checker", after_check)
    builder.add_edge("return_to_document", "document_write")
    builder.add_edge("handoff", "prepare_card")
    builder.add_edge("finish_answer", "prepare_card")
    builder.add_edge("prepare_card", "wait_for_approval")
    builder.add_conditional_edges("wait_for_approval", lambda state: "wait_for_approval" if state["outcome"] == "pending" else END)
    return builder.compile(checkpointer=checkpointer)
