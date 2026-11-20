"""교직원 자료 목록. 기관·현재 담당 반을 먼저 거른 뒤 쪽을 나눠요."""

from datetime import datetime

from sqlalchemy import text

from app.core.db import transaction
from app.core.schedule import KST


def list_documents(user, page, size, sort):
    conditions = """ FROM documents d WHERE d.org_id=:org AND (
        :director OR NOT EXISTS (
            SELECT 1 FROM document_classrooms dc WHERE (dc.document_id,dc.org_id)=(d.id,d.org_id))
        OR EXISTS (
            SELECT 1 FROM document_classrooms dc JOIN classroom_staff cs
              ON (cs.classroom_id,cs.org_id)=(dc.classroom_id,dc.org_id)
            WHERE (dc.document_id,dc.org_id)=(d.id,d.org_id) AND cs.user_id=:user
              AND (cs.valid_from IS NULL OR cs.valid_from<=:today)
              AND (cs.valid_to IS NULL OR cs.valid_to>=:today)))"""
    values = {"org": user.org_id, "user": user.id, "director": user.role == "director",
              "today": datetime.now(KST).date(), "limit": size, "offset": (page-1)*size}
    direction = "DESC" if sort.startswith("-") else "ASC"
    with transaction() as connection:
        total = connection.scalar(text("SELECT count(*)" + conditions), values)
        rows = connection.execute(text("""
            SELECT d.*,
                ARRAY(SELECT dc.classroom_id FROM document_classrooms dc
                      WHERE (dc.document_id,dc.org_id)=(d.id,d.org_id) ORDER BY dc.classroom_id) AS classroom_ids,
                (SELECT count(*) FROM document_chunks ch
                 WHERE (ch.document_id,ch.org_id)=(d.id,d.org_id)) AS chunk_count,
                (SELECT e.detail FROM events e WHERE e.org_id=d.org_id AND e.action='tool_failed'
                 AND e.detail->>'document_id'=CAST(d.id AS text) ORDER BY e.id DESC LIMIT 1) AS job_error
        """ + conditions + f" ORDER BY d.created_at {direction}, d.id {direction} LIMIT :limit OFFSET :offset"),
                                  values).mappings().all()
    items = []
    for row in rows:
        item = {key: row[key] for key in ("id", "title", "doc_type", "visibility", "classroom_ids",
                "effective_from", "effective_to", "status", "ingest_status", "supersedes_id", "chunk_count")}
        # DDL에서 비울 수 있는 적용일은 읽기 계약의 date에 맞춰 생성일을 기본값으로 써요.
        item["effective_from"] = row["effective_from"] or row["created_at"].astimezone(KST).date()
        item["conflicts"] = []
        error = row["job_error"]
        item["error"] = {key: error[key] for key in ("code", "message")} if error else None
        items.append(item)
    return {"items": items, "total": total, "page": page, "size": size}
