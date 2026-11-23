"""같은 API 프로세스의 백그라운드 입구. T29에서 워커 태스크로도 불러요."""

from importlib import import_module
from datetime import timedelta
import logging

from sqlalchemy import text

from app.core.config import settings
from app.core.db import transaction
from app.modules.requests.agent_stub import new_card
from app.modules.requests.events import record, set_status

log = logging.getLogger(__name__)


def _handoff(connection, req, reason):
    card = new_card(connection, req, "reply_draft", None)
    set_status(connection, req, "awaiting_review", action="checked", card=card, handoff_reason=reason)


def run_request(request_id):
    try:
        module, name = settings.request_agent.split(":", 1)
        getattr(import_module(module), name)(request_id)
    except Exception:
        # 예외 본문은 개인정보·키를 담을 수 있어 저장·응답에 옮기지 않아요.
        with transaction() as connection:
            row = connection.execute(text("SELECT * FROM requests WHERE id=:id FOR UPDATE"),
                                     {"id": request_id}).mappings().one_or_none()
            if row is None:
                return
            req = dict(row)
            record(connection, req, "tool_failed", code="UPSTREAM_UNAVAILABLE", handoff_reason="ai_failed")
            if req["status"] in ("received", "classified", "assigned", "needs_info") and not connection.scalar(text("""
                SELECT EXISTS (SELECT 1 FROM cards WHERE request_id=:id)
            """), {"id": request_id}):
                _handoff(connection, req, "ai_failed")


def sweep_missing_cards(now):
    """5분 넘게 카드가 없으면 한 번 재전달하고, 5분 더 없을 때만 인계해요."""
    requeued, handed_off = [], 0
    with transaction() as connection:
        rows = connection.execute(text("""
            SELECT * FROM requests r
            WHERE type IN ('inquiry','consultation','complaint')
              AND status IN ('received','classified','assigned') AND created_at<:now-interval '5 minutes'
              AND NOT EXISTS (SELECT 1 FROM cards c WHERE c.request_id=r.id)
            ORDER BY r.id FOR UPDATE OF r SKIP LOCKED
        """), {"now": now}).mappings().all()
        for row in rows:
            # 잠금을 기다리는 사이 다른 실행이 카드를 커밋했는지도 다시 봐요.
            if connection.scalar(text("SELECT EXISTS (SELECT 1 FROM cards WHERE request_id=:id)"), {"id": row["id"]}):
                continue
            # 요청 잠금 뒤 새 문장으로 읽어 동시 점검의 재전달 이력도 확인해요.
            retried_at = connection.scalar(text("""
                SELECT max(created_at) FROM events WHERE request_id=:id AND action='agent_requeued'
            """), {"id": row["id"]})
            if retried_at is None:
                connection.execute(text("""
                    INSERT INTO events(org_id,request_id,actor_type,action,created_at)
                    VALUES (:org,:id,'system','agent_requeued',:now)
                """), {"org": row["org_id"], "id": row["id"], "now": now})
                requeued.append(row["id"])
            elif retried_at <= now - timedelta(minutes=5):
                _handoff(connection, dict(row), "card_missing")
                handed_off += 1
    # 먼저 커밋해요. eager·API 안 실행도 요청 잠금을 다시 잡을 수 있어야 해요.
    for request_id in requeued:
        if settings.run_in == "worker":
            from app.core.jobs import publish
            publish("request", request_id)
        else:
            run_request(request_id)
    try:
        from app.modules.requests.graph_agent import sweep_approval_resumes
        sweep_approval_resumes()
    except Exception as error:  # noqa: BLE001 - 누락 카드 점검은 그래프 재전달 실패와 독립적으로 끝낸다
        log.warning("승인 그래프 재전달 점검 실패 error_type=%s", type(error).__name__)
    return len(requeued) + handed_off
