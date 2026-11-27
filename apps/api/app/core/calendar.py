"""[제안] DB 의존성 없이 날짜 추출·반 범위를 두 백엔드에 같이 적용해요."""

from datetime import date

from agents.guardrails.injection import suspicious_chunk
from app.core.schedule import KST
from app.modules.documents.conflicts import extract_facts
from app.modules.documents.parsing import Chunk, DocumentMeta, ParsedDocument


def items(user, documents, start, end):
    from app import backend

    classes = (backend.users.classroom_ids_of(user.id) if user.role == "teacher" else
               [c.classroom_id for c in backend.users.children_of(user.id)] if user.role == "parent" else [])
    result = []
    for doc in documents:
        if doc["org_id"] != user.org_id or doc["status"] != "active" or doc["ingest_status"] != "succeeded" \
                or doc["doc_type"] not in ("schedule", "notice"):
            continue
        if (user.role == "parent" and doc["visibility"] == "staff") or (
                user.role != "director" and doc["classroom_ids"] and not set(classes).intersection(doc["classroom_ids"])):
            continue
        meta = {k: doc[k] for k in ("title", "doc_type", "visibility", "source", "is_virtual")}
        meta["effective_from"] = doc["effective_from"] or doc["created_at"].astimezone(KST).date()
        parsed = ParsedDocument(DocumentMeta(id=str(doc["id"]), kindergarten_id=str(doc["org_id"]),
                                classroom_keys=(), **meta), "", doc["content_sha256"], tuple(
            Chunk(c["chunk_index"], c["location"] or "", c["content"]) for c in doc["chunks"]
            if not suspicious_chunk(c["content"])))  # 검색처럼 의심 조각은 일정에도 안 보임(T55 G-6)
        for fact in extract_facts(parsed):
            if fact.kind != "date":
                continue
            first, span, last = fact.value.partition("~")
            day, until = date.fromisoformat(first), date.fromisoformat(last) if span else None
            if day <= end and (until or day) >= start:
                result.append({"date": day, "end_date": until, "title": fact.label, "document_id": doc["id"],
                               "document_title": fact.document_title, "location": fact.location})
    return {"items": sorted(result, key=lambda r: (r["date"], r["title"], r["document_title"], r["location"]))}
