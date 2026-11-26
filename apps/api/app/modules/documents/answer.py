"""학부모 문의의 자료 범위를 묶고 근거를 카드에 저장한다."""

import os
from types import SimpleNamespace

from sqlalchemy import text

from agents.graphs.answer import draft_answer, fallback
from app.modules.documents.search import search_documents


def answer_for_request(req, writer=None, checker=None, forecast=None):
    """forecast는 run_request가 트랜잭션 밖에서 가져와 저장해 둔 예보 근거(없으면 None)."""
    user = SimpleNamespace(id=req["requester_id"], org_id=req["org_id"], role="parent")

    def search(doc_type, query):
        chunks = search_documents(user, str(req["org_id"]), doc_type, query,
                                  classroom_id=req["classroom_id"], top_k=8)["chunks"]
        if forecast and doc_type == "schedule":
            chunks = [{k: v for k, v in forecast.items() if k != "quote"}, *chunks]
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
                            prior_answer=find_saved_answer(req), preferences=preferences, child_notes=child_notes)
    except Exception:  # 모델·자료 오류가 카드 생성을 막지 않도록 한다
        return fallback(["search", "write"])


def save_evidence(connection, card, answer):
    seen = set()
    for item in answer["evidence"]:
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
