"""LangGraph 요청 입구. REQUEST_AGENT=app.modules.requests.graph_agent:run_request 로 선택한다."""

import logging
import os
from types import SimpleNamespace
from datetime import datetime
from uuid import UUID

from sqlalchemy import text

from agents.graphs.request import build_graph
from agents.guardrails.sensitive import mask_sensitive
from app.core.db import database_url, transaction
from app.core.schedule import KST
from app.modules.requests.agent_stub import run_request as prepare_request

log = logging.getLogger(__name__)


def thread_id(request_id) -> str:
    """원문·학부모 정보 없이 요청 UUID로 같은 체크포인트를 찾는다."""
    return f"request:{UUID(str(request_id))}"


def _route_request(request_id):
    with transaction() as connection:
        return connection.scalar(text("SELECT type FROM requests WHERE id=:id"), {"id": request_id})


def _prepare_card(request_id, route, answer=None, classification=None):
    if answer is None and classification is None:
        prepare_request(UUID(request_id))
    else:
        prepare_request(UUID(request_id), prepared_answer=answer, prepared_fields=classification)
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


class Gathered(list):
    """자료 찾는 AI가 모은 근거 조각. 협업 그래프는 조각 목록을 그대로 작성 노드에 넘기므로, 법령을 못 가져왔는지도
    목록에 실어 카드까지 보낸다(체크포인트에는 남지 않음)."""

    def __init__(self, chunks, law_unchecked=False):
        super().__init__(chunks)
        self.law_unchecked = law_unchecked


def _request_context(request_id):
    with transaction() as connection:
        return connection.execute(text("""
            SELECT r.type,r.body,r.org_id,r.classroom_id,r.requester_id,r.child_id,r.created_at,
                   (SELECT c.display_name FROM children c WHERE c.org_id=r.org_id AND c.id=r.child_id) AS child_name,
                   (SELECT s.user_id FROM classroom_staff s
                    JOIN users u ON (u.id,u.org_id)=(s.user_id,s.org_id)
                    WHERE s.org_id=r.org_id AND s.classroom_id=r.classroom_id
                      AND u.role='teacher' AND u.is_active
                      AND (s.valid_from IS NULL OR s.valid_from<=:today)
                      AND (s.valid_to IS NULL OR s.valid_to>=:today)
                    ORDER BY s.is_homeroom DESC,s.created_at,s.user_id LIMIT 1) AS teacher_id
            FROM requests r WHERE r.id=:id
        """), {"id": request_id, "today": datetime.now(KST).date()}).mappings().one()


def _high_risk_request(request_id):
    from app.modules.requests.supervisor import classify_request, validate_proposal

    req = _request_context(request_id)
    proposal = classify_request(req["type"], req["body"])
    return validate_proposal(req["type"], req["body"], proposal)


def _search_request(request_id):
    from agents.graphs import answer as answer_graph
    from agents.graphs.answer import PERSONAL, gather_on
    from agents.graphs.gather import gather
    from app.modules.documents.answer import (asked_on, graph_enabled, daily_note_chunks, daily_record_chunks,
                                              request_who)
    from app.modules.documents.tools import RequestToolbox
    from app.modules.documents.search import search_documents
    from app.modules.documents.public_sources import question_forecast

    req = _request_context(request_id)
    if req["type"] == "inquiry" and not graph_enabled():
        return [{"skip": True}]
    if req["type"] not in ("inquiry", "complaint"):
        return [{"skip": True}]
    user = SimpleNamespace(id=req["requester_id"], org_id=req["org_id"], role="parent")
    chunks = []
    if gather_on():  # 자료 찾는 AI가 같은 요청 범위의 도구(예보·법령 포함)로 모으고, 못 모으면 아래 고정 검색 그대로
        tools = RequestToolbox(req)
        found = gather(req["body"], tools, answer_graph.OpenAIModel("GATHER"), today=asked_on(req), who=request_who(req))
        if found:
            return Gathered(found, law_unchecked=tools.law_unchecked)
    # 고정 검색(대역)에서만 질문 낱말(event_day)로 예보를 가져와요. 외부 API는 트랜잭션 밖이에요.
    forecast = question_forecast(req["org_id"], req["body"], datetime.now(KST).date()) if req["type"] == "inquiry" else None
    types = ("notice", "policy") if req["type"] == "complaint" else ("notice", "schedule", "menu", "policy")
    for doc_type in types:
        for attempt in range(2):
            try:
                found = search_documents(user, str(req["org_id"]), doc_type, req["body"],
                                         classroom_id=req["classroom_id"], top_k=8)["chunks"]
                chunks.extend(([forecast] if forecast and doc_type == "schedule" else []) + found)
                break
            except Exception:
                if attempt:
                    raise
    chunks.extend(daily_note_chunks(req) + daily_record_chunks(req))
    return sorted(chunks, key=lambda item: (item.get("source") in PERSONAL, item["score"]), reverse=True)[:8]


ANSWER_RULE_CODES = ("wrong_fact", "tone", "missing_info", "privacy", "policy", "other")  # 상담 시간 규칙(slot·room)은 상담 후보 쪽에서 읽어요


def _load_request_memory(request_id):
    """담임 말투 기억과, 담임이 켠 답변 규칙(거절 이유가 쌓여 기억 AI가 제안한 것)을 답변 AI에 맞춤 참고로 줘요."""
    from app.modules.memories.memories import active_rules, load_tones
    req = _request_context(request_id)
    if req["teacher_id"] is None:
        return []
    with transaction() as connection:
        rules = active_rules(connection, req["org_id"], req["teacher_id"], ANSWER_RULE_CODES)
        return load_tones(connection, req["org_id"], req["teacher_id"]) + [
            {"kind": "rule", "content": rule["rule_text"]} for rule in rules]


def _write_request(state):
    from agents.graphs import answer as answer_graph
    from app.modules.documents.answer import asked_on, graph_enabled, request_who
    from app.modules.memories.saved_answers import find_saved_answer

    req = _request_context(state["request_id"])
    if req["type"] == "inquiry" and not graph_enabled():
        return {"draft": {}, "passed": True}
    chunks = state["parallel"]["chunks"]
    # 기본 경로(draft_answer)처럼 공통 규칙(지시 무시·개인정보·발송 금지)과 질문 받은 날·이 요청의 아이를 앞에 붙여요.
    prompt = (answer_graph._common(asked_on(req), request_who(req))
              + answer_graph._prompt("documents.md", "## 입력", "## 알림장 초안 쓰기")
              + answer_graph.WRITE_FORMAT)
    # 보호자 글은 문의 답변 그래프(answer.py)처럼 가려서 모델에 보낸다(T55 G-5). 원 자료 조각은 그대로 둔다.
    payload = {"question": mask_sensitive(req["body"]), "today": answer_graph.day_label(asked_on(req)), "chunks": chunks, "memories": state["parallel"].get("memories", []),
               "prior_answer": find_saved_answer(req),
               "review_issues": state.get("issues", [])}
    from app.modules.memories.memories import load_preferences, load_child_notes
    try:
        with transaction() as connection:
            payload["preferences"] = load_preferences(connection, req["org_id"], req["requester_id"])
            payload["child_notes"] = load_child_notes(connection, req["org_id"], req["child_id"], req["requester_id"])
    except Exception:  # 기억 조회 실패가 이번 답변을 막지 않아요
        payload["preferences"], payload["child_notes"] = [], []
    payload["untrusted_data_fields"] = ["question", "chunks", "memories", "prior_answer", "preferences", "child_notes"]
    reply = answer_graph._ask_writer(answer_graph.OpenAIModel("DOCUMENT"), prompt, payload, [])
    if reply is None:
        return {"draft": {"text": "", "evidence": [], "no_evidence": True, "conflict": False}}
    draft = answer_graph._verify(reply, chunks, [], req["body"])
    if isinstance(chunks, Gathered):  # 카드에서 법령을 낱말로 다시 붙이지 않고 AI가 인용한 조문만 근거로 둬요
        draft.update(gathered=True, **({"law_unchecked": True} if chunks.law_unchecked else {}))
    return {"draft": draft}


def _check_request(state):
    from agents.graphs import answer as answer_graph
    from app.modules.documents.answer import asked_on, graph_enabled, request_who

    req = _request_context(state["request_id"])
    if req["type"] == "inquiry" and not graph_enabled():
        return {"passed": True, "issues": []}
    issues = answer_graph._review(answer_graph.OpenAIModel("CHECKER"), mask_sensitive(req["body"]), state["draft"],
                                  state["parallel"]["chunks"], state.get("attempt", 0) + 1, [], asked_on(req),
                                  request_who(req))
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
                      "tags": ["request-agent"], "run_name": "요청 처리"}
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
