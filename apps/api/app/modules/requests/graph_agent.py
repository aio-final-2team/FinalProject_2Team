"""LangGraph 요청 입구. REQUEST_AGENT=app.modules.requests.graph_agent:run_request 로 선택한다."""

import logging
import os
from types import SimpleNamespace
from uuid import UUID

from sqlalchemy import text

from agents.graphs.request import build_graph
from app.core.db import database_url, transaction
from app.modules.requests.agent_stub import run_request as prepare_request

log = logging.getLogger(__name__)


def thread_id(request_id) -> str:
    """원문·학부모 정보 없이 요청 UUID로 같은 체크포인트를 찾는다."""
    return f"request:{UUID(str(request_id))}"


def _route_request(request_id):
    with transaction() as connection:
        return connection.scalar(text("SELECT type FROM requests WHERE id=:id"), {"id": request_id})


def _prepare_card(request_id, route, answer=None):
    if answer is None:
        prepare_request(UUID(request_id))
    else:
        prepare_request(UUID(request_id), prepared_answer=answer)  # 기존 상태·카드·알림의 트랜잭션 경계를 그대로 쓴다
    kind = "consult_slots" if route == "consultation" else "reply_draft"
    with transaction() as connection:
        card_id = connection.scalar(text("""
            SELECT id FROM cards WHERE request_id=:id AND kind=:kind
            ORDER BY created_at DESC,id DESC LIMIT 1
        """), {"id": request_id, "kind": kind})
        if card_id is None:
            return None
        saved = connection.execute(text("""
            UPDATE cards SET graph_thread_id=:thread WHERE id=:card
              AND (graph_thread_id IS NULL OR graph_thread_id=:thread)
        """), {"card": card_id, "thread": thread_id(request_id)})
        if saved.rowcount != 1:
            raise ValueError("카드의 그래프 연결이 달라요")
    return str(card_id)


def _request_context(request_id):
    with transaction() as connection:
        return connection.execute(text("""
            SELECT r.type,r.body,r.org_id,r.classroom_id,r.requester_id,
                   (SELECT s.user_id FROM classroom_staff s WHERE s.org_id=r.org_id
                    AND s.classroom_id=r.classroom_id ORDER BY s.is_homeroom DESC,s.created_at LIMIT 1) AS teacher_id
            FROM requests r WHERE r.id=:id
        """), {"id": request_id}).mappings().one()


def _high_risk_request(request_id):
    from app.core.request_rules import classify

    req = _request_context(request_id)
    return classify(req["type"], req["body"]).get("risk_level") in ("urgent", "uncertain")


def _search_request(request_id):
    from app.modules.documents.answer import graph_enabled
    from app.modules.documents.search import search_documents

    req = _request_context(request_id)
    if req["type"] == "inquiry" and not graph_enabled():
        return [{"skip": True}]
    if req["type"] not in ("inquiry", "complaint"):
        return [{"skip": True}]
    user = SimpleNamespace(id=req["requester_id"], org_id=req["org_id"], role="parent")
    chunks = []
    types = ("notice", "policy") if req["type"] == "complaint" else ("notice", "schedule", "menu", "policy")
    for doc_type in types:
        for attempt in range(2):
            try:
                chunks.extend(search_documents(user, str(req["org_id"]), doc_type, req["body"],
                                               classroom_id=req["classroom_id"], top_k=8)["chunks"])
                break
            except Exception:
                if attempt:
                    raise
    return sorted(chunks, key=lambda item: item["score"], reverse=True)[:8]


def _load_request_memory(request_id):
    req = _request_context(request_id)
    if req["teacher_id"] is None:
        return []
    with transaction() as connection:
        return [dict(row) for row in connection.execute(text("""
            SELECT kind,content FROM memories WHERE org_id=:org AND owner_id=:owner
              AND kind='tone' AND deleted_at IS NULL ORDER BY created_at DESC LIMIT 8
        """), {"org": req["org_id"], "owner": req["teacher_id"]}).mappings()]


def _write_request(state):
    from agents.graphs import answer as answer_graph
    from app.modules.documents.answer import graph_enabled

    req = _request_context(state["request_id"])
    if req["type"] == "inquiry" and not graph_enabled():
        return {"draft": {}, "passed": True}
    chunks = state["parallel"]["chunks"]
    prompt = answer_graph._prompt("documents.md", "## 입력", "## 알림장 초안 쓰기") + answer_graph.WRITE_FORMAT
    payload = {"question": req["body"], "chunks": chunks, "memories": state["parallel"].get("memories", []),
               "review_issues": state.get("issues", [])}
    reply = answer_graph._ask_writer(answer_graph.OpenAIModel("DOCUMENT"), prompt, payload, [])
    if reply is None:
        return {"draft": {"text": "", "evidence": [], "no_evidence": True, "conflict": False}}
    return {"draft": answer_graph._verify(reply, chunks, [])}


def _check_request(state):
    from agents.graphs import answer as answer_graph
    from app.modules.documents.answer import graph_enabled

    req = _request_context(state["request_id"])
    if req["type"] == "inquiry" and not graph_enabled():
        return {"passed": True, "issues": []}
    issues = answer_graph._review(answer_graph.OpenAIModel("CHECKER"), req["body"], state["draft"],
                                  state["parallel"]["chunks"], state.get("attempt", 0) + 1, [])
    if issues is None:
        return {"passed": False, "issues": [{"field": "출처", "problem": "검사하지 못했어요."}],
                "attempt": 2}
    return {"passed": not issues, "issues": issues}


def _card_status(card_id):
    with transaction() as connection:
        status = connection.scalar(text("SELECT status FROM cards WHERE id=:id"), {"id": card_id})
    return status if status in ("done", "rejected") else "pending"


def _database_uri():
    return database_url().set(drivername="postgresql").render_as_string(hide_password=False)


def _invoke(request_id, payload, expected_card_id=None):
    import psycopg
    from langgraph.checkpoint.postgres import PostgresSaver
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
    from psycopg.rows import dict_row

    # 체크포인트에는 ID·분기·시도 횟수·인계 사유만 남긴다. 임의 Python 객체도 읽지 않는다.
    serializer = JsonPlusSerializer(allowed_msgpack_modules=[])
    request_id = str(UUID(str(request_id)))
    key = f"request-graph:{request_id}"
    with psycopg.connect(_database_uri(), autocommit=True, row_factory=dict_row) as checkpoint_connection:
        checkpointer = PostgresSaver(checkpoint_connection, serde=serializer)
        checkpointer.setup()
        # 요청별 직렬화는 이 autocommit 연결의 세션 잠금으로 한다. 트랜잭션을 쥐지 않으니
        # 그래프가 도는 동안 SQLAlchemy 풀 연결은 노드가 쓰는 짧은 순간에만 빌린다.
        checkpoint_connection.execute("SELECT pg_advisory_lock(hashtextextended(%s,0))", (key,))
        try:
            graph_builder = build_graph
            if os.getenv("REQUEST_COLLAB_GRAPH") == "1":
                from agents.graphs.request_collaboration import build_graph as graph_builder
                graph = graph_builder(checkpointer, _route_request, _prepare_card, _card_status,
                                      _search_request, _load_request_memory, _write_request, _check_request,
                                      _high_risk_request)
            else:
                graph = graph_builder(checkpointer, _route_request, _prepare_card, _card_status)
            config = {"configurable": {"thread_id": thread_id(request_id)},
                      "tags": ["request-agent"]}
            if expected_card_id is not None:
                snapshot = graph.get_state(config)
                if (snapshot.values.get("card_id") != str(expected_card_id)
                        or not any(task.interrupts for task in snapshot.tasks)):
                    return None  # 이미 재개했거나 다른 카드의 승인을 기다리는 중
            return graph.invoke(payload, config=config)
        finally:
            # 예외·타임아웃에도 푼다. 연결이 이미 끊겼다면 연결을 닫을 때 서버가 잠금을 풀어요.
            try:
                checkpoint_connection.execute("SELECT pg_advisory_unlock(hashtextextended(%s,0))", (key,))
            except psycopg.Error:
                log.warning("요청 그래프 잠금 해제 실패, 연결을 닫아 해제해요")


def run_request(request_id):
    """중복 전달은 요청별 잠금으로 직렬화한다."""
    request_id = str(UUID(str(request_id)))
    return _invoke(request_id, {"request_id": request_id})


def resume_request(card_id):
    """카드 결정이 커밋된 뒤 호출할 입구. 승인 내용은 그래프가 DB에서 다시 읽는다."""
    from langgraph.types import Command

    card_id = UUID(str(card_id))
    with transaction() as connection:
        row = connection.execute(text("""
            SELECT request_id, graph_thread_id, status, kind FROM cards WHERE id=:id
        """), {"id": card_id}).mappings().one_or_none()
    if row is None or row["request_id"] is None or row["graph_thread_id"] != thread_id(row["request_id"]):
        return None
    if row["status"] == "rejected":
        with transaction() as connection:
            next_card = connection.scalar(text("""
                SELECT id FROM cards WHERE request_id=:request AND kind=:kind AND id<>:old
                  AND status IN ('pending','in_review') AND graph_thread_id IS NULL
                ORDER BY created_at DESC,id DESC LIMIT 1
            """), {"request": row["request_id"], "kind": row["kind"], "old": card_id})
        if next_card is not None:
            return run_request(row["request_id"])  # 거절로 생긴 새 카드를 같은 thread에 연결
    return _invoke(str(row["request_id"]), Command(resume=True), expected_card_id=card_id)


def try_resume(card_id):
    """승인 DB 커밋 뒤에 호출한다. 전달 실패가 승인 API 응답을 바꾸지 않게 한다."""
    try:
        return resume_request(card_id)
    except Exception as error:  # noqa: BLE001 - 주기 점검이 승인 기록으로 다시 전달한다
        log.warning("요청 그래프 재개 실패 error_type=%s", type(error).__name__)
        return None


def sweep_approval_resumes():
    """승인·이력에 남은 종료 카드를 다시 확인한다. 재개 완료 카드에는 효과가 없다."""
    with transaction() as connection:
        card_ids = connection.execute(text("""
            SELECT c.id FROM cards c WHERE c.graph_thread_id IS NOT NULL
              AND c.status IN ('done','rejected')
              AND EXISTS (SELECT 1 FROM approvals a WHERE a.card_id=c.id AND a.org_id=c.org_id
                          AND a.decision IN ('approve','edit_approve','reject','dismiss','complete'))
              AND EXISTS (SELECT 1 FROM events e WHERE e.card_id=c.id AND e.org_id=c.org_id
                          AND e.action IN ('approved','booked','rejected','dismissed','completed'))
            ORDER BY c.created_at,c.id
        """)).scalars().all()
    for card_id in card_ids:
        try_resume(card_id)
    return len(card_ids)
