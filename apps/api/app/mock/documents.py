"""문서 업로드·조각·근거의 메모리 구현."""

from hashlib import sha256
from uuid import uuid4

from app.core.errors import ApiError
from app.core.document_text import extract_text
from app.modules.documents.parsing import DocumentFormatError
from app.mock import store
from app.mock.records import Document, Chunk, Evidence


def in_scope(user, document_id):
    doc = store.state().documents.get(document_id)
    targets = store.state().document_classrooms.get(document_id, [])
    if doc is None or doc.org_id != user.org_id or (user.role == "teacher" and targets
            and not set(targets).intersection(store.classroom_ids_of(user.id))):
        store.deny(user)
    return doc


def visible(user):
    allowed = set(store.classroom_ids_of(user.id))
    return [d for d in store.state().documents.values() if d.org_id == user.org_id and (user.role == "director"
            or not store.state().document_classrooms.get(d.id)
            or allowed.intersection(store.state().document_classrooms[d.id]))]


def list_documents(user, page, size, sort):
    with store._lock:
        items = sorted(visible(user), key=lambda doc: doc.created_at, reverse=sort.startswith("-"))
        return {"items": [view(doc) for doc in items[(page-1)*size:page*size]],
                "total": len(items), "page": page, "size": size}


def chunks(doc):
    return [c for c in store.state().chunks.values() if c.document_id == doc.id]


def add_chunks(doc, text):
    # shortcut: 텍스트 길이로만 조각을 나눔, 실제 적재 작업에서 문서 파서로 교체
    for index, offset in enumerate(range(0, max(len(text), 1), 500)):
        chunk = Chunk(store.state().next_int(), doc.org_id, doc.id, index, f"{index + 1}쪽", text[offset:offset+500])
        store.state().chunks[chunk.id] = chunk


def upload(user, filename, data, doc_type, visibility, classroom_ids, effective_from, replaces_document_id):
    with store._lock:
        for classroom_id in classroom_ids:
            store.classroom_in_scope(user, classroom_id)
        old = in_scope(user, replaces_document_id) if replaces_document_id else None
        digest = sha256(data).hexdigest()
        existing = next((d for d in store.state().documents.values()
                         if d.org_id == user.org_id and d.content_sha256 == digest), None)
        if existing:
            return in_scope(user, existing.id), False
        if old and old.status != "active":
            raise ApiError(409, "INVALID_TRANSITION")
        message = None
        try:
            if "[실패]" in filename:
                raise DocumentFormatError("자료를 읽지 못했어요.")
            content = extract_text(filename, data)
        except DocumentFormatError as error:
            message = str(error)
        failed = message is not None
        doc = Document(uuid4(), user.org_id, filename, doc_type, visibility, digest, effective_from, store.now(),
                       source="uploaded", supersedes_id=old.id if old and not failed else None, uploaded_by=user.id,
                       ingest_status="failed" if failed else "succeeded")
        store.state().documents[doc.id] = doc
        store.state().document_classrooms[doc.id] = classroom_ids
        if old and not failed:          # 새 판 적재가 실패하면 옛 판을 그대로 쓴다
            old.status = "superseded"
        if failed:
            store.add_event(None, "tool_failed", org_id=user.org_id, document_id=doc.id,
                            code="UPSTREAM_UNAVAILABLE", message=message)
        else:
            add_chunks(doc, content)
        return doc, True


def view(doc, *, include_chunks=False):
    error = next((e.detail for e in reversed(store.state().events)
                  if e.action == "tool_failed" and e.detail.get("document_id") == doc.id), None)
    item = {"id": doc.id, "title": doc.title, "doc_type": doc.doc_type, "visibility": doc.visibility,
            "classroom_ids": store.state().document_classrooms.get(doc.id, []), "status": doc.status,
            "effective_from": doc.effective_from, "effective_to": doc.effective_to,
            "ingest_status": doc.ingest_status, "supersedes_id": doc.supersedes_id, "conflicts": [],
            "chunk_count": len(chunks(doc)),
            "error": {k: error[k] for k in ("code", "message")} if error and doc.ingest_status == "failed" else None}
    if include_chunks:
        from agents.guardrails.injection import suspicious_chunk

        item["chunks"] = [{"index": c.chunk_index, "location": c.location, "content": c.content,
                           "suspicious": suspicious_chunk(c.content)}
                          for c in sorted(chunks(doc), key=lambda c: c.chunk_index)]
    return item


def attach_evidence(card):
    req = store.state().requests[card.request_id]
    docs = [d for d in store.state().documents.values() if d.org_id == req.org_id and d.status == "active"
            and d.effective_from <= store.now().date() and (not d.effective_to or d.effective_to >= store.now().date())
            and (not store.state().document_classrooms.get(d.id)
                 or req.classroom_id in store.state().document_classrooms[d.id])]
    if docs:
        chunk = next(iter(chunks(docs[0])), None)
        if chunk:
            store.state().evidence.append(Evidence(card.id, card.org_id, chunk.id, 1, chunk.content[:120]))
    card.draft["no_evidence"] = not any(e.card_id == card.id for e in store.state().evidence)


def evidence(card, parent=False):
    result = []
    for link in sorted(store.state().evidence, key=lambda e: e.rank):
        if link.card_id != card.id:
            continue
        chunk = store.state().chunks[link.chunk_id]
        doc = store.state().documents[chunk.document_id]
        if parent and doc.visibility not in ("parents", "all"):
            continue
        result.append({"document_title": doc.title, "location": chunk.location,
                       "effective_from": doc.effective_from, "quote": link.quote,
                       # 시행 전 문서도 지금 판이에요. 옛 판·충돌 대기·기간 만료만 거짓(API 설계 문서 3.3 evidence)
                       "is_current": doc.status == "active"
                                     and (doc.effective_to is None or doc.effective_to >= store.now().date())})
    return result
