"""[제안] 담당 범위 자료만 검색하고 요청·카드 없이 호출 이력을 남겨요."""

import json

from sqlalchemy import text

from app.core.db import transaction
from app.core.request_id import active_trace_id
from app.core.staff_ask import respond
from app.modules.documents.documents import list_documents
from app.modules.documents.search import search_documents


def ask(user, question, writer=None, checker=None):
    docs = {d["id"]: d for d in list_documents(user, 1, 2147483647, "-created_at")["items"]}
    with transaction() as connection:
        rows = connection.execute(text("""
            SELECT ch.id,ch.document_id,ch.location,d.effective_from FROM document_chunks ch
            JOIN documents d ON (d.id,d.org_id)=(ch.document_id,ch.org_id)
            WHERE ch.org_id=:org AND ch.document_id=ANY(CAST(:ids AS uuid[]))
        """), {"org": user.org_id, "ids": list(docs)}).mappings().all()
    sources = {r["id"]: {"document_id": r["document_id"], "title": docs[r["document_id"]]["title"],
                          "location": r["location"] or "본문",
                          "effective_date": r["effective_from"]} for r in rows}

    def search(kind, query):
        return search_documents(user, str(user.org_id), kind, query, top_k=8, allowed_chunk_ids=sources)["chunks"]

    result = None
    try:
        result = respond(question, search, sources, writer, checker)
        return result
    finally:
        with transaction() as connection:
            connection.execute(text("""
                INSERT INTO events(org_id,actor_type,actor_id,agent_name,action,detail)
                VALUES (:org,'user',:actor,'document',:action,CAST(:detail AS jsonb))
            """), {"org": user.org_id, "actor": user.id,
                   "action": "tool_called" if result is not None else "tool_failed",
                   "detail": json.dumps({"tool": "staff_ask", "evidence_count": len(result["evidence"]) if result else 0,
                                         "trace_id": active_trace_id.get(),
                                         **({"code": "UPSTREAM_UNAVAILABLE"} if result is None else {})})})
