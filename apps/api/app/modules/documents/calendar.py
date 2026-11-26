"""[제안] 같은 기관에서 볼 수 있는 일정 자료만 읽어요."""

from sqlalchemy import text

from app.core.calendar import items
from app.core.db import transaction


def listing(user, start, end):
    with transaction() as connection:
        rows = connection.execute(text("""
            SELECT d.*, ARRAY(SELECT dc.classroom_id FROM document_classrooms dc
                             WHERE (dc.document_id,dc.org_id)=(d.id,d.org_id)) AS classroom_ids,
                   coalesce((SELECT jsonb_agg(jsonb_build_object('chunk_index',ch.chunk_index,
                       'location',ch.location,'content',ch.content) ORDER BY ch.chunk_index)
                       FROM document_chunks ch WHERE (ch.document_id,ch.org_id)=(d.id,d.org_id)), '[]') AS chunks
            FROM documents d WHERE d.org_id=:org AND d.status='active' AND d.ingest_status='succeeded'
              AND d.doc_type IN ('schedule','notice') ORDER BY d.id
        """), {"org": user.org_id}).mappings().all()
        return items(user, rows, start, end)
