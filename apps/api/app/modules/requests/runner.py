"""같은 API 프로세스의 백그라운드 입구. T29에서 워커 태스크로도 불러요."""

from importlib import import_module

from sqlalchemy import text

from app.core.config import settings
from app.core.db import transaction
from app.modules.requests.agent_stub import new_card
from app.modules.requests.events import record, set_status


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
    """5분을 넘긴 진행 중 요청만 미배정 카드로 넘겨요. 주기 실행은 T29에서 붙여요."""
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
            if not connection.scalar(text("SELECT EXISTS (SELECT 1 FROM cards WHERE request_id=:id)"), {"id": row["id"]}):
                _handoff(connection, dict(row), "card_missing")
        return len(rows)
