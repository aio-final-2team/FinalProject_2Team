"""자료 올리기(DB): 접수 → 뒤에서 조각 나누기·충돌 검사 → 저장 (T20, FR-04·FR-13·NFR-07).

API 3.x `POST /documents`(202)·`GET /documents/{id}`, DB `documents`·`document_chunks`·`document_classrooms`.
- 조각 나누기·충돌 검사는 모델을 부르지 않는 가벼운 일이라 접수 요청 안에서 바로 끝낸다(모의 API와 같음).
  파일 원문 열이 DB에 없어서 뒤 작업(API·Celery 워커)으로 넘기지 않는다. 202 응답의 `ingest_status`는
  `succeeded`·`failed`이고 화면은 지금처럼 `GET /documents/{id}`로 본다. 무거운 임베딩(T33)은 저장된 조각을 읽어 뒤에서 한다.
- 조각은 `## ` 제목 단위(`parsing.split_chunks`), 제목이 근거 위치(`location`).
- 다른 사용 중 문서와 같은 항목의 날짜·숫자가 다르면 `status = conflict_pending`, 충돌 목록은 이력
  `events(action='checked', detail.conflicts)`에 남긴다(새 표 없이). 사람이 확인하기 전에는 옛 판을 바꾸지 않는다.
- 임베딩(`embedding`)은 비워 둔다. 검색은 낱말 검색(`search.py`)이고, bge-m3는 T33에서 붙인다(11/23 결정).
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from sqlalchemy import text

from app.core import scope
from app.core.db import transaction
from app.core.document_text import extract_text
from app.core.errors import ApiError
from app.core.schedule import KST
from agents.guardrails.injection import suspicious_chunk

from .conflicts import find_conflicts
from .parsing import Chunk, DocumentFormatError, DocumentMeta, ParsedDocument, parse_document, split_chunks

log = logging.getLogger(__name__)
FIELDS = ("id", "title", "doc_type", "visibility", "classroom_ids", "effective_from", "effective_to",
          "status", "ingest_status", "supersedes_id", "chunk_count")

_ROW = """
    SELECT d.*,
        ARRAY(SELECT dc.classroom_id FROM document_classrooms dc
              WHERE (dc.document_id,dc.org_id)=(d.id,d.org_id) ORDER BY dc.classroom_id) AS classroom_ids,
        (SELECT count(*) FROM document_chunks ch WHERE (ch.document_id,ch.org_id)=(d.id,d.org_id)) AS chunk_count,
        (SELECT e.detail FROM events e WHERE e.org_id=d.org_id AND e.action='tool_failed'
           AND e.detail->>'document_id'=CAST(d.id AS text) ORDER BY e.id DESC LIMIT 1) AS job_error,
        (SELECT e.detail FROM events e WHERE e.org_id=d.org_id AND e.action='checked'
           AND e.detail->>'document_id'=CAST(d.id AS text) ORDER BY e.id DESC LIMIT 1) AS job_check
    FROM documents d WHERE d.id=:id AND d.org_id=:org
"""


def _today():
    return datetime.now(KST).date()


def _row(connection, org_id, document_id):
    return connection.execute(text(_ROW), {"id": document_id, "org": org_id}).mappings().one_or_none()


def in_scope(user, document_id):
    """교직원 자료 상세 범위: 원장은 같은 기관 전체, 담임은 원 전체 자료와 지금 담당 반 자료(API 3.x ⑤)."""
    with transaction() as connection:
        row = _row(connection, user.org_id, document_id)
        allowed = row is not None and (
            user.role == "director" or not row["classroom_ids"]
            or any(scope._classroom(connection, user, c) for c in row["classroom_ids"]))
    return scope._checked(user, row, allowed, "document", document_id)


def view(row, *, include_chunks=False) -> dict:
    item = {key: row[key] for key in FIELDS}
    item["effective_from"] = row["effective_from"] or row["created_at"].astimezone(KST).date()
    item["classroom_ids"] = list(row["classroom_ids"] or [])
    item["conflicts"] = (row["job_check"] or {}).get("conflicts", [])
    error = row["job_error"]
    item["error"] = ({key: error[key] for key in ("code", "message")}
                     if error and row["ingest_status"] == "failed" else None)
    if include_chunks:
        with transaction() as connection:
            chunks = connection.execute(text("""
                SELECT chunk_index AS index,location,content FROM document_chunks
                WHERE document_id=:id AND org_id=:org ORDER BY chunk_index
            """), {"id": row["id"], "org": row["org_id"]}).mappings().all()
        item["chunks"] = [{**chunk, "suspicious": suspicious_chunk(chunk["content"])} for chunk in chunks]
    return item


def upload(user, filename, data, doc_type, visibility, classroom_ids, effective_from, replaces_document_id):
    """접수만 한다. 같은 기관에 같은 내용이 이미 있으면 그 문서를 돌려준다(created=False, 200)."""
    digest = hashlib.sha256(data).hexdigest()
    classroom_ids = list(dict.fromkeys(classroom_ids))
    old = in_scope(user, replaces_document_id) if replaces_document_id is not None else None
    with transaction() as connection:
        for classroom_id in classroom_ids:
            scope.classroom_in_scope(user, classroom_id, connection=connection)
        existing = connection.scalar(text("SELECT id FROM documents WHERE org_id=:org AND content_sha256=:sha"),
                                     {"org": user.org_id, "sha": digest})
        if existing is None:
            if old is not None and old["status"] != "active":
                raise ApiError(409, "INVALID_TRANSITION")
            existing = connection.scalar(text("""
                INSERT INTO documents (org_id, title, doc_type, visibility, source, effective_from, status,
                                       ingest_status, supersedes_id, uploaded_by, content_sha256, is_virtual)
                VALUES (:org, :title, :doc_type, :visibility, 'uploaded', :effective_from, 'active',
                        'running', NULL, :user, :sha, true)
                ON CONFLICT (org_id, content_sha256) DO NOTHING RETURNING id
            """), {"org": user.org_id, "title": filename, "doc_type": doc_type, "visibility": visibility,
                   "effective_from": effective_from, "user": user.id, "sha": digest})
            created = existing is not None
            if created:
                for classroom_id in classroom_ids:
                    connection.execute(text("""
                        INSERT INTO document_classrooms (document_id, classroom_id, org_id) VALUES (:d, :c, :org)
                        ON CONFLICT DO NOTHING
                    """), {"d": existing, "c": classroom_id, "org": user.org_id})
            else:
                existing = connection.scalar(text("SELECT id FROM documents WHERE org_id=:org AND content_sha256=:sha"),
                                             {"org": user.org_id, "sha": digest})
        else:
            created = False
    if not created:
        prior = in_scope(user, existing)
        if prior["ingest_status"] == "failed":
            if old is not None and old["status"] != "active":
                raise ApiError(409, "INVALID_TRANSITION")
            # 두 요청이 같이 failed를 읽어도 먼저 running으로 바꾼 쪽만 다시 적재한다.
            with transaction() as connection:
                created = connection.scalar(text("""
                    UPDATE documents SET title=:title, ingest_status='running'
                    WHERE id=:id AND org_id=:org AND ingest_status='failed' RETURNING id
                """), {"title": filename, "id": existing, "org": user.org_id}) is not None
    if created:
        run_ingest(existing, data, replaces_document_id)
    with transaction() as connection:
        row = _row(connection, user.org_id, existing)
    return row, created


def _parsed_from_upload(row, data: bytes) -> ParsedDocument:
    content = extract_text(row["title"], data)
    if content.lstrip().startswith("---"):
        parsed = parse_document(content)
        body, chunks = parsed.body, parsed.chunks
    else:
        body, chunks = content, tuple(split_chunks(content))
    if not chunks:
        raise DocumentFormatError("읽을 내용이 없어요")
    return ParsedDocument(meta=_meta(row), body=body, content_sha256=row["content_sha256"], chunks=tuple(chunks))


def _meta(row) -> DocumentMeta:
    # 충돌 검사의 대상 반 비교는 DB 반 ID 문자열로 한다(빈 목록 = 원 전체)
    return DocumentMeta(id=str(row["id"]), title=row["title"], doc_type=row["doc_type"],
                        kindergarten_id=str(row["org_id"]),
                        classroom_keys=tuple(str(c) for c in (row["classroom_ids"] or [])),
                        effective_from=row["effective_from"] or _today(), visibility=row["visibility"],
                        source=row["source"], is_virtual=row["is_virtual"])


def _others(connection, row, replaces_document_id) -> list[ParsedDocument]:
    """비교 대상: 같은 기관에서 사용 중(active)이고 적재가 끝난 다른 문서. 새 판이 대신할 옛 판은 뺀다."""
    docs = connection.execute(text("""
        SELECT d.*, ARRAY(SELECT dc.classroom_id FROM document_classrooms dc
                          WHERE (dc.document_id,dc.org_id)=(d.id,d.org_id)) AS classroom_ids
        FROM documents d
        WHERE d.org_id=:org AND d.id<>:id AND d.status='active' AND d.ingest_status='succeeded'
          AND (CAST(:old AS uuid) IS NULL OR d.id<>CAST(:old AS uuid))
    """), {"org": row["org_id"], "id": row["id"], "old": replaces_document_id}).mappings().all()
    out = []
    for doc in docs:
        chunks = connection.execute(text("""
            SELECT chunk_index, location, content FROM document_chunks
            WHERE document_id=:id AND org_id=:org ORDER BY chunk_index
        """), {"id": doc["id"], "org": doc["org_id"]}).mappings().all()
        body = "\n".join(c["content"] for c in chunks)
        out.append(ParsedDocument(meta=_meta(doc), body=body, content_sha256=doc["content_sha256"],
                                  chunks=tuple(Chunk(c["chunk_index"], c["location"] or "", c["content"])
                                               for c in chunks)))
    return out


def run_ingest(document_id, data: bytes, replaces):
    """조각·충돌을 한 트랜잭션에 저장한다. 실패하면 failed + 이력(tool_failed)."""
    try:
        with transaction() as connection:
            row = connection.execute(text(_ROW.replace("WHERE d.id=:id AND d.org_id=:org", "WHERE d.id=:id")),
                                     {"id": document_id}).mappings().one()
            parsed = _parsed_from_upload(row, data)
            conflicts = [c.to_dict() for c in find_conflicts(parsed, _others(connection, row, replaces))]
            suspicious_indexes = [chunk.index for chunk in parsed.chunks if suspicious_chunk(chunk.content)]
            for chunk in parsed.chunks:
                connection.execute(text("""
                    INSERT INTO document_chunks (document_id, org_id, chunk_index, location, content)
                    VALUES (:d, :org, :i, :loc, :content)
                """), {"d": document_id, "org": row["org_id"], "i": chunk.index, "loc": chunk.location,
                       "content": chunk.content})
            status = "conflict_pending" if conflicts else "active"
            supersedes = replaces if (replaces is not None and not conflicts) else None
            connection.execute(text("""
                UPDATE documents SET ingest_status='succeeded', status=:status, supersedes_id=:sup WHERE id=:id
            """), {"status": status, "sup": supersedes, "id": document_id})
            if supersedes is not None:
                connection.execute(text("UPDATE documents SET status='superseded' WHERE id=:id AND org_id=:org"),
                                   {"id": supersedes, "org": row["org_id"]})
            connection.execute(text("""
                INSERT INTO events (org_id, actor_type, action, detail)
                VALUES (:org, 'system', 'checked', CAST(:detail AS jsonb))
            """), {"org": row["org_id"], "detail": json.dumps(
                {"document_id": str(document_id), "chunk_count": len(parsed.chunks), "conflicts": conflicts,
                 "suspicious_chunk_indexes": suspicious_indexes},
                ensure_ascii=False)})
    except Exception as error:  # noqa: BLE001 - 어떤 실패든 화면에 failed로 보이게 한다
        message = str(error) if isinstance(error, DocumentFormatError) else "자료를 읽지 못했어요."
        log.warning("자료 적재 실패 %s: %s", document_id, type(error).__name__)
        with transaction() as connection:
            connection.execute(text("UPDATE documents SET ingest_status='failed' WHERE id=:id AND ingest_status='running'"),
                               {"id": document_id})
            connection.execute(text("""
                INSERT INTO events (org_id, actor_type, action, detail)
                SELECT org_id, 'system', 'tool_failed', CAST(:detail AS jsonb) FROM documents WHERE id=:id
            """), {"id": document_id, "detail": json.dumps(
                {"document_id": str(document_id), "code": "UPSTREAM_UNAVAILABLE", "message": message},
                ensure_ascii=False)})
