"""요청 ID만 저장하는 그래프. 승인 결정은 카드 API가 DB에 기록한다."""

from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

ROUTES = ("inquiry", "consultation", "complaint")


class RequestState(TypedDict, total=False):
    request_id: str
    route: str
    card_id: str
    outcome: str


def build_graph(checkpointer, route_request, prepare_card, card_status):
    """DB 입출력 함수를 주입해 분기·승인 대기를 시험할 수 있게 한다."""
    builder = StateGraph(RequestState)

    def classify(state):
        route = route_request(state["request_id"])
        return {"route": route if route in ROUTES else "other"}

    def next_route(state):
        return state["route"] if state["route"] in ROUTES else END

    builder.add_node("classify", classify)
    builder.add_edge(START, "classify")
    builder.add_conditional_edges("classify", next_route)

    for route in ROUTES:
        def prepare(state, selected=route):
            card_id = prepare_card(state["request_id"], selected)
            return {"card_id": card_id or ""}

        builder.add_node(route, prepare)
        builder.add_edge(route, "wait_for_approval")

    def wait_for_approval(state):
        if not state.get("card_id"):
            return {"outcome": "no_card"}
        # 재개할 때 노드 처음부터 다시 시작한다. 앞에는 DB 쓰기를 두지 않는다.
        interrupt({"card_id": state["card_id"]})
        return {"outcome": card_status(state["card_id"])}

    def after_approval(state):
        return "wait_for_approval" if state["outcome"] == "pending" else END

    builder.add_node("wait_for_approval", wait_for_approval)
    builder.add_conditional_edges("wait_for_approval", after_approval)
    return builder.compile(checkpointer=checkpointer)
