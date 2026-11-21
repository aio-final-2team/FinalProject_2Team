"""알림장 출처 확인용 요청 읽기. 쓰기·대화·스트림은 T27에서 연결해요."""

from sqlalchemy import text

from app.api.labels import parent_label, staff_label
from app.core import scope
from app.core.db import transaction
from app.core.errors import ApiError


def detail(user, request_id):
    req = scope.request_in_scope(user, request_id)
    # 현재 읽기 계약은 inquiry·consultation·complaint·pickup이에요. 투약 계약은 T46 몫이에요.
    if req["type"] == "medication":
        raise ApiError(501, "NOT_IMPLEMENTED")
    values = {"id": request_id, "org": user.org_id, "parent": user.role == "parent",
              "requester": req["requester_id"]}
    with transaction() as connection:
        messages = connection.execute(text("""
            SELECT id, sender_type, body, created_at FROM request_messages
            WHERE request_id=:id AND org_id=:org AND sender_type='user' AND sender_id=:requester
            ORDER BY created_at, id LIMIT 1
        """), values).mappings().all()
        sources = connection.execute(text("""
            SELECT d.title AS document_title, ch.location, d.effective_from
            FROM cards c JOIN card_evidence e ON (e.card_id,e.org_id)=(c.id,c.org_id)
            JOIN document_chunks ch ON (ch.id,ch.org_id)=(e.chunk_id,e.org_id)
            JOIN documents d ON (d.id,d.org_id)=(ch.document_id,ch.org_id)
            WHERE c.request_id=:id AND c.org_id=:org
              AND (NOT :parent OR d.visibility IN ('parents','all'))
              AND EXISTS (SELECT 1 FROM approvals a WHERE (a.card_id,a.org_id)=(c.id,c.org_id)
                          AND a.decision IN ('approve','edit_approve'))
            ORDER BY c.created_at, c.id, e.rank, ch.id
        """), values).mappings().all() if req["status"] in ("sent_or_booked", "completed") else []
    label = parent_label if user.role == "parent" else staff_label
    return {"request": {**{key: req[key] for key in (
                "id", "type", "title", "status", "missing_fields", "parent_confirmed_at", "created_at", "updated_at")},
                "status_label": label(req["status"], req["type"]), "hold_until": None},
            "messages": [dict(row) for row in messages], "sources": [dict(row) for row in sources],
            "timeline": [], "consultation": None, "rejection": None}
