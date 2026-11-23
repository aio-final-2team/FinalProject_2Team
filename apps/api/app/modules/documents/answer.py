"""학부모 문의의 자료 범위를 묶고 근거를 카드에 저장한다."""

import os
from types import SimpleNamespace

from sqlalchemy import text

from agents.graphs.answer import draft_answer, fallback
from app.modules.documents.search import search_documents


def answer_for_request(req, writer=None, checker=None):
    user = SimpleNamespace(id=req["requester_id"], org_id=req["org_id"], role="parent")

    def search(doc_type, query):
        return search_documents(user, str(req["org_id"]), doc_type, query,
                                classroom_id=req["classroom_id"], top_k=8)["chunks"]

    try:
        return draft_answer(req["body"], search, writer=writer, checker=checker)
    except Exception:  # 모델·자료 오류가 카드 생성을 막지 않도록 한다
        return fallback(["search", "write"])


def save_evidence(connection, card, answer):
    for rank, item in enumerate(answer["evidence"], 1):
        connection.execute(text("""
            INSERT INTO card_evidence(card_id, org_id, chunk_id, rank, score, quote)
            VALUES (:card, :org, :chunk, :rank, :score, :quote)
        """), {"card": card["id"], "org": card["org_id"], "chunk": item["chunk_id"],
               "rank": rank, "score": item["score"], "quote": item["quote"]})


def graph_enabled():
    return os.getenv("ANSWER_WRITER", "stub") == "graph"
