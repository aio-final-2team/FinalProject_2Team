"""[제안] 자료 목록과 기존 낱말 점수를 쓰는 메모리 대역이에요."""

from app.core.staff_ask import respond
from app.mock import documents, store
from agents.guardrails.injection import suspicious_chunk


def ask(user, question, writer=None, checker=None):
    from app.modules.documents.search import score, terms

    with store._lock:
        docs = {d.id: d for d in documents.visible(user) if d.status == "active" and d.ingest_status == "succeeded"
                and (d.effective_to is None or d.effective_to >= store.now().date())}
        chunks = [c for c in store.state().chunks.values() if c.document_id in docs and c.org_id == user.org_id]
        sources = {c.id: {"document_id": c.document_id, "title": docs[c.document_id].title,
                           "location": c.location or "본문", "effective_date": docs[c.document_id].effective_from}
                   for c in chunks}

        def search(kind, query):
            found = []
            for c in chunks:
                doc = docs[c.document_id]
                value = score(terms(query), doc.title, c.location or "", c.content)
                if doc.doc_type == kind and value > 0 and not suspicious_chunk(c.content):
                    found.append({"chunk_id": c.id, "document_title": doc.title, "location": c.location or "본문",
                                  "effective_from": doc.effective_from, "content": c.content, "score": value})
            return sorted(found, key=lambda c: (-c["score"], c["chunk_id"]))[:8]

        result = None
        try:
            result = respond(question, search, sources, writer, checker)
            return result
        finally:
            store.add_event(None, "tool_called" if result is not None else "tool_failed",
                            org_id=user.org_id, actor_type="user", actor_id=user.id,
                            agent_name="document", tool="staff_ask", evidence_count=len(result["evidence"]) if result else 0,
                            **({"code": "UPSTREAM_UNAVAILABLE"} if result is None else {}))
