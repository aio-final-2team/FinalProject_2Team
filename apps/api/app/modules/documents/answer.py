"""학부모 문의의 자료 범위를 묶고 근거를 카드에 저장한다."""

import os
import json
from datetime import datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import text
from app.core.db import transaction
from app.core.memory_rules import mask_child_names
from app.core.schedule import KST

from agents.graphs.answer import draft_answer, fallback
from app.modules.documents.search import search_documents


def asked_on(req):
    """질문을 받은 날(한국 시각). 답변 AI는 이 날을 기준으로 오늘·내일을 읽는다."""
    created = req.get("created_at")
    return created.astimezone(KST).date() if isinstance(created, datetime) else None


def daily_note_chunks(req):
    from agents.graphs.answer import child_day_question, note_chunk
    if req["type"] != "inquiry" or not req.get("child_id") or not child_day_question(req["body"]):
        return []
    today = datetime.now(KST).date()
    with transaction() as connection:
        rows = connection.execute(text("""
            SELECT n.id,n.note_date,n.content FROM daily_notes n
            WHERE n.org_id=:org AND n.child_id=:child AND n.status='sent' AND n.note_date BETWEEN :since AND :today
              AND EXISTS (SELECT 1 FROM child_guardians g WHERE (g.org_id,g.child_id,g.user_id)=(:org,:child,:parent))
            ORDER BY n.note_date DESC,n.id LIMIT 3
        """), {"org": req["org_id"], "child": req["child_id"], "parent": req["requester_id"],
               "since": today-timedelta(days=2), "today": today}).mappings().all()
    return [chunk for row in rows if (chunk := note_chunk(row["id"], row["note_date"], row["content"]))]


RELATIVE_DAYS = (("그저께", 2), ("그제", 2), ("어저께", 1), ("어제", 1), ("오늘", 0))


def asked_days(body, today):
    """질문에 나온 오늘·어제·그제를 날짜로 바꿔요. 날짜 말이 없으면 질문 받은 날 하나예요."""
    return sorted({today - timedelta(days=n) for word, n in RELATIVE_DAYS if word in body} or {today})


def daily_record_chunks(req):
    """아이에 관한 문의면 질문이 가리키는 날(오늘·어제·그제, 없으면 질문 받은 날)의 담임 관찰 기록을 근거 후보로 더해요.
    날마다 최근 3개까지예요. 관찰 기록은 보호자에게 바로 안 보이는 메모라, 담임이 검토하고 보내는 초안에만 쓰여요."""
    from agents.graphs.answer import child_about_question, record_chunk
    if req["type"] != "inquiry" or not req.get("child_id") or not child_about_question(req["body"]):
        return []
    today = asked_on(req) or datetime.now(KST).date()
    with transaction() as connection:
        rows = connection.execute(text("""
            SELECT id,note_date,body FROM (
                SELECT r.id,r.note_date,r.body,r.created_at,
                       row_number() OVER (PARTITION BY r.note_date ORDER BY r.created_at DESC,r.id) AS n
                FROM daily_records r
                WHERE r.org_id=:org AND r.child_id=:child AND r.deleted_at IS NULL
                  AND r.note_date=ANY(CAST(:days AS date[]))
                  AND EXISTS (SELECT 1 FROM child_guardians g WHERE (g.org_id,g.child_id,g.user_id)=(:org,:child,:parent))
            ) picked WHERE n<=3 ORDER BY note_date DESC,created_at DESC,id
        """), {"org": req["org_id"], "child": req["child_id"], "parent": req["requester_id"],
               "days": asked_days(req["body"], today)}).mappings().all()
        # 기록에 함께 적힌 다른 아이 이름은 이 학부모 초안·외부 모델로 넘기지 않아요(기억 저장과 같은 가림).
        roster = connection.execute(text("SELECT display_name,id=:child AS own FROM children WHERE org_id=:org"),
                                    {"org": req["org_id"], "child": req["child_id"]}).all() if rows else []
    own = {name for name, is_own in roster if is_own}
    others = [name for name, is_own in roster if not is_own and name not in own]
    return [chunk for row in rows
            if (chunk := record_chunk(row["id"], row["note_date"], mask_child_names(row["body"], others)))]


def answer_for_request(req, writer=None, checker=None, forecast=None):
    """forecast는 run_request가 트랜잭션 밖에서 가져와 저장해 둔 예보 근거(없으면 None)."""
    user = SimpleNamespace(id=req["requester_id"], org_id=req["org_id"], role="parent")

    def search(doc_type, query):
        chunks = search_documents(user, str(req["org_id"]), doc_type, query,
                                  classroom_id=req["classroom_id"], top_k=8)["chunks"]
        if forecast and doc_type == "schedule":
            chunks = [{k: v for k, v in forecast.items() if k != "quote"}, *chunks]
        if doc_type == "notice":
            chunks = [*daily_note_chunks(req), *daily_record_chunks(req), *chunks]
        return chunks

    try:
        from app.modules.requests.graph_agent import _load_request_memory
        from app.modules.memories.saved_answers import find_saved_answer
        try:  # 기억을 못 읽어도 자료만으로 답을 쓴다
            memories = _load_request_memory(req["id"])
        except Exception:
            memories = []
        from app.modules.memories.memories import load_preferences, load_child_notes
        from app.core.db import transaction
        try:
            with transaction() as connection:
                preferences = load_preferences(connection, req["org_id"], req["requester_id"])
                child_notes = load_child_notes(connection, req["org_id"], req["child_id"], req["requester_id"])
        except Exception:  # 기억 조회 실패가 이번 답변을 막지 않아요
            preferences, child_notes = [], []
        return draft_answer(req["body"], search, writer=writer, checker=checker, memories=memories,
                            prior_answer=find_saved_answer(req), preferences=preferences, child_notes=child_notes,
                            today=asked_on(req))
    except Exception:  # 모델·자료 오류가 카드 생성을 막지 않도록 한다
        return fallback(["search", "write"])


def save_evidence(connection, card, answer):
    seen = set()
    # 알림장·관찰 기록은 card_evidence.chunk_id(NOT NULL)에 못 넣어 카드 초안에 따로 남겨요.
    for field, source in (("note_evidence", "daily_note"), ("record_evidence", "daily_record")):
        items = [item for item in answer["evidence"] if item.get("source") == source and item.get("chunk_id") is None]
        if items:
            card["draft"][field] = items
            connection.execute(text("UPDATE cards SET draft=draft || CAST(:items AS jsonb) WHERE id=:id"),
                               {"items": json.dumps({field: items}), "id": card["id"]})
    for item in answer["evidence"]:
        if item.get("chunk_id") is None:
            continue
        chunk_id = int(item["chunk_id"])
        if chunk_id in seen:
            continue
        seen.add(chunk_id)
        connection.execute(text("""
            INSERT INTO card_evidence(card_id, org_id, chunk_id, rank, score, quote)
            VALUES (:card, :org, :chunk, :rank, :score, :quote)
        """), {"card": card["id"], "org": card["org_id"], "chunk": chunk_id,
               "rank": len(seen), "score": item["score"], "quote": item["quote"]})


def graph_enabled():
    return os.getenv("ANSWER_WRITER", "stub") == "graph"
