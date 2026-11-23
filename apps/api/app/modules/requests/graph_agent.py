"""LangGraph 요청 입구. REQUEST_AGENT=app.modules.requests.graph_agent:run_request 로 선택한다."""

import logging
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


def _prepare_card(request_id, route):
    prepare_request(UUID(request_id))  # 기존 상태·카드·알림의 트랜잭션 경계를 그대로 쓴다
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

    # 체크포인트는 UUID·카드 ID·분기만 저장하고, 임의 Python 객체는 읽지 않는다.
    serializer = JsonPlusSerializer(allowed_msgpack_modules=[])
    request_id = str(UUID(str(request_id)))
    with psycopg.connect(_database_uri(), autocommit=True, row_factory=dict_row) as checkpoint_connection:
        checkpointer = PostgresSaver(checkpoint_connection, serde=serializer)
        # setup()의 동시 인덱스 생성은 열린 업무 트랜잭션 밖에서 끝낸다.
        checkpointer.setup()
        with transaction() as connection:
            connection.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
                               {"key": f"request-graph:{request_id}"})
            graph = build_graph(checkpointer, _route_request, _prepare_card, _card_status)
            config = {"configurable": {"thread_id": thread_id(request_id)},
                      "tags": ["request-agent"]}
            if expected_card_id is not None:
                snapshot = graph.get_state(config)
                if (snapshot.values.get("card_id") != str(expected_card_id)
                        or not any(task.interrupts for task in snapshot.tasks)):
                    return None  # 이미 재개했거나 다른 카드의 승인을 기다리는 중
            return graph.invoke(payload, config=config)


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
