"""요청 협업 그래프. 체크포인트에는 승인 재개에 필요한 작은 값만 둔다."""

from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send, interrupt

from agents.graphs.request import ROUTES

MAX_REWRITES = 2


def _merge(left, right):
    """병렬 작업의 성공 여부만 합친다. 내용은 실행 중 지역 변수에 둔다."""
    return {**left, **right}


class CollaborationState(TypedDict, total=False):
    request_id: str
    route: str
    card_id: str
    outcome: str
    parallel: Annotated[dict, _merge]
    attempt: int
    passed: bool
    handoff: bool
    handoff_reason: str
    draft_no_evidence: bool
    draft_conflict: bool
    draft_partial: bool
    skip_draft: bool


def build_graph(checkpointer, route_request, prepare_card, card_status,
                search=None, load_memory=None, write=None, check=None, high_risk=None):
    """한 번의 실행에서만 자료를 들고 다닌다. 승인 재개에는 카드 ID만 쓴다."""
    builder = StateGraph(CollaborationState)
    work = {"chunks": [], "memories": [], "draft": {}, "issues": [], "answer": None, "classification": None}

    def supervisor(state):
        route = route_request(state["request_id"])
        work["classification"] = high_risk(state["request_id"]) if high_risk and route in ROUTES else None
        risk = work["classification"]
        # 긴급만 초안을 건너뛴다. 판단 필요도 초안을 써 두고, 승인은 재분류 전까지 카드 API가 막는다.
        return {"route": route if route in ROUTES else "other", "attempt": 0,
                "skip_draft": (risk.get("risk_level") == "urgent" if isinstance(risk, dict) else bool(risk))}

    def route_after_supervisor(state):
        if state.get("skip_draft"):
            return "prepare_card"
        if state["route"] == "consultation":
            return "memory_consultation"
        if state["route"] in ("inquiry", "complaint"):
            return [Send("docs_search", {"request_id": state["request_id"]}),
                    Send("memory_load", {"request_id": state["request_id"]})]
        return END

    def docs_search(state):
        try:
            chunks = search(state["request_id"]) if search else []
            work["chunks"] = chunks
            return {"parallel": {"search_failed": search is not None and not chunks}}
        except Exception:
            return {"parallel": {"search_failed": True}}

    def memory_load(state):
        try:
            work["memories"] = load_memory(state["request_id"]) if load_memory else []
            return {"parallel": {"memory_failed": False}}
        except Exception:
            return {"parallel": {"memory_failed": True}}

    def after_write(state):
        return "handoff" if (state["parallel"].get("search_failed")
                             or (state.get("draft_no_evidence") and not state.get("draft_partial"))
                             or state.get("draft_conflict")) else "checker"

    def document_write(state):
        if state["parallel"].get("search_failed"):
            return {"draft_no_evidence": True}
        if write is None:
            return {"draft_no_evidence": False, "draft_conflict": False, "draft_partial": False}
        try:
            result = write({**state, "parallel": {**state["parallel"],
                                                    "chunks": work["chunks"],
                                                    "memories": work["memories"],
                                                    "memory_failed": state["parallel"].get("memory_failed", False)},
                            "issues": work["issues"]})
            work["draft"] = result.get("draft", {})
            return {"draft_no_evidence": bool(work["draft"].get("no_evidence")),
                    "draft_conflict": bool(work["draft"].get("conflict")),
                    "draft_partial": bool(work["draft"].get("partial"))}
        except Exception:
            return {"draft_no_evidence": True, "draft_partial": False, "handoff_reason": "write_failed"}

    def checker(state):
        if check is None:
            return {"passed": True}
        try:
            result = check({**state, "draft": work["draft"],
                            "parallel": {**state["parallel"], "chunks": work["chunks"]}})
            work["issues"] = result.get("issues", [])
            return {"passed": result["passed"],
                    "attempt": result.get("attempt", state.get("attempt", 0))}
        except Exception:
            work["issues"] = [{"field": "출처", "problem": "검사하지 못했어요."}]
            return {"passed": False, "attempt": MAX_REWRITES, "handoff_reason": "check_failed"}

    def after_check(state):
        if state.get("passed"):
            return "finish_answer"
        if state.get("attempt", 0) >= MAX_REWRITES:
            return "handoff"
        return "return_to_document"

    def return_to_document(state):
        return {"attempt": state.get("attempt", 0) + 1}

    def finish_answer(state):
        work["answer"] = {**work["draft"], "check_result": {
            "passed": True, "issues": [], "attempt": state.get("attempt", 0) + 1,
            **({"memory_unavailable": True} if state.get("parallel", {}).get("memory_failed") else {})}}
        return {}

    def handoff(state):
        draft = work["draft"]
        issues = work["issues"]
        if draft and (state.get("draft_no_evidence") or state.get("draft_conflict")):
            problem = "자료끼리 내용이 달라요." if state.get("draft_conflict") else "자료에서 근거를 찾지 못했어요."
            issues = [{"field": "출처", "problem": problem}]
        work["answer"] = {"text": "", "evidence": draft.get("evidence", []),
                          "no_evidence": draft.get("no_evidence", True),
                          "partial": draft.get("partial", False),
                          "handoff": True, "conflict": draft.get("conflict", False),
                          "check_result": {"passed": False, "issues": issues,
                                           "attempt": state.get("attempt", 0) + 1,
                                           **({"memory_unavailable": True}
                                              if state.get("parallel", {}).get("memory_failed") else {})}}
        reason = state.get("handoff_reason")
        if not reason:
            if state.get("parallel", {}).get("search_failed"):
                reason = "search_failed"
            elif state.get("draft_conflict"):
                reason = "conflict"
            elif state.get("draft_no_evidence"):
                reason = "no_evidence"
            else:
                reason = "check_limit"
        return {"handoff": True, "handoff_reason": reason}

    def prepare(state):
        return {"card_id": prepare_card(state["request_id"], state["route"],
                                        work["answer"], work["classification"]) or ""}

    def wait_for_approval(state):
        if not state.get("card_id"):
            return {"outcome": "no_card"}
        interrupt({"card_id": state["card_id"]})
        return {"outcome": card_status(state["card_id"])}

    builder.add_node("supervisor", supervisor)
    builder.add_node("docs_search", docs_search)
    builder.add_node("memory_load", memory_load)
    builder.add_node("memory_consultation", memory_load)
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
    builder.add_conditional_edges("document_write", after_write, {"checker": "checker", "handoff": "handoff"})
    builder.add_conditional_edges("checker", after_check)
    builder.add_edge("return_to_document", "document_write")
    builder.add_edge("handoff", "prepare_card")
    builder.add_edge("finish_answer", "prepare_card")
    builder.add_edge("prepare_card", "wait_for_approval")
    builder.add_conditional_edges("wait_for_approval", lambda state: "wait_for_approval" if state["outcome"] == "pending" else END)
    return builder.compile(checkpointer=checkpointer)
