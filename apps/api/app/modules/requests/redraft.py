"""학부모가 답을 받은 뒤 글을 더 남기면, 새 글까지 넣은 대화로 답변 AI가 초안을 다시 써요.

requests.message가 카드를 빈 초안(앞 답은 previous_text)으로 되돌려 커밋한 뒤 처음 초안과 같은 일꾼(jobs.dispatch)으로 넘겨요.
처음 초안(agent_stub.run_request)처럼 공공 API·모델은 트랜잭션 밖에서 부르고 저장만 짧은 트랜잭션에서 해요.
다시 쓴 글이 없거나 실패했거나, 그새 카드가 바뀌었으면(담임이 손댐·새 글로 다시 열림) 빈 초안 그대로 둬요.
승인 막기·사람 확인은 그대로예요. 카드는 pending으로 담임 확인을 기다려요.
"""

import json
import logging

from sqlalchemy import text

from app.core.db import transaction
from app.core.schedule import KST
from app.modules.requests.events import record

log = logging.getLogger(__name__)
SPEAKERS = {"parent": "보호자", "teacher": "선생님", "director": "선생님"}
# 앞 초안의 근거 표시는 새 초안 근거로 바꿔요(법령 미확인 표시도 새로 정해요).
STALE_KEYS = ("note_evidence", "record_evidence", "care_evidence", "law_unchecked")


def _latest_card(connection, request_id):
    return connection.execute(text("""
        SELECT * FROM cards WHERE request_id=:id AND kind='reply_draft' ORDER BY created_at DESC,id DESC LIMIT 1
    """), {"id": request_id}).mappings().one_or_none()


def _reopened(card):
    """새 글로 다시 열린 뒤 아직 아무도 손대지 않은 빈 초안 카드인지."""
    return (card is not None and card["status"] in ("pending", "unassigned")
            and "previous_text" in card["draft"] and not card["draft"].get("text"))


def conversation(connection, req):
    """요청 글부터 새 글까지의 대화와 마지막 글 시각(답변 AI가 '오늘'로 읽는 날)."""
    rows = connection.execute(text("""
        SELECT m.sender_type,m.body,m.created_at,u.role FROM request_messages m
        LEFT JOIN users u ON (u.id,u.org_id)=(m.sender_id,m.org_id)
        WHERE m.org_id=:org AND m.request_id=:id ORDER BY m.created_at,m.id
    """), {"org": req["org_id"], "id": req["id"]}).mappings().all()
    lines = [f"{SPEAKERS.get(row['role'], '안내') if row['sender_type'] == 'user' else '안내'}: {row['body']}"
             for row in rows]
    return "\n".join(lines), rows[-1]["created_at"] if rows else req["created_at"]


def redraft_request(request_id):
    try:
        _redraft(request_id)
    except Exception as error:  # noqa: BLE001 - 다시 쓰기 실패는 빈 초안 그대로 둬요
        log.warning("새 글 초안 다시 쓰기 실패 error_type=%s", type(error).__name__)


def _redraft(request_id):
    from agents.graphs.answer import gather_on
    from app.modules.documents.answer import answer_for_request, graph_enabled, save_evidence
    from app.modules.documents.public_sources import attach_law_evidence, prefetch_public, question_forecast

    if not graph_enabled():  # 답변 AI가 꺼진 설정(모의 작성기)은 지금처럼 빈 초안이에요
        return
    with transaction() as connection:
        req = connection.execute(text("SELECT * FROM requests WHERE id=:id"), {"id": request_id}).mappings().one_or_none()
        card = _latest_card(connection, request_id)
        # 긴급은 처음 초안처럼 AI 초안을 건너뛰는 선이에요.
        if (req is None or req["type"] not in ("inquiry", "complaint") or req["status"] != "awaiting_review"
                or req["risk_level"] == "urgent" or not _reopened(card)):
            return
        req = dict(req)
        dialogue, last_at = conversation(connection, req)
    today = last_at.astimezone(KST).date()
    prefetched = prefetch_public(req["type"], dialogue, req["topic_key"], today, with_forecast=False,
                                 risk_category=req["risk_category"])
    forecast = question_forecast(req["org_id"], dialogue, today) if req["type"] == "inquiry" and not gather_on() else None
    answer = answer_for_request({**req, "body": dialogue, "created_at": last_at}, forecast=forecast)
    if (answer["no_evidence"] and not answer.get("partial")) or answer["conflict"] or not answer["text"].strip():
        return  # 근거 없음·충돌·실패는 처음 초안처럼 글 없는 카드예요. 빈 초안 그대로 둬요
    with transaction() as connection:
        row = connection.execute(text("SELECT * FROM cards WHERE id=:id FOR UPDATE"), {"id": card["id"]}).mappings().one()
        if row["version"] != card["version"] or not _reopened(row):
            return  # 그새 담임이 손댔거나 새 글로 다시 열렸어요. 나중 실행이 맡아요
        draft = {**{k: v for k, v in row["draft"].items() if k not in STALE_KEYS},
                 "text": answer["text"], "no_evidence": answer["no_evidence"], "conflict": answer["conflict"]}
        saved = dict(connection.execute(text("""
            UPDATE cards SET draft=CAST(:draft AS jsonb),check_result=CAST(:check AS jsonb),version=version+1,
                updated_at=clock_timestamp() WHERE id=:id RETURNING *
        """), {"id": row["id"], "draft": json.dumps(draft), "check": json.dumps(answer.get("check_result"))}).mappings().one())
        connection.execute(text("DELETE FROM card_evidence WHERE card_id=:id"), {"id": row["id"]})
        save_evidence(connection, saved, answer)
        if req["type"] == "complaint":
            attach_law_evidence(connection, saved, req, prefetched, answer)
        record(connection, req, "drafted", card=saved, actor_type="agent", agent_name="document", redraft=True)
