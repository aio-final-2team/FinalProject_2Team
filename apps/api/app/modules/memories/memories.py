from sqlalchemy import text

from app.core import scope
from app.core.db import transaction


def list_memories(user, kind, page, size, sort):
    condition = "org_id=:org AND owner_id=:owner AND deleted_at IS NULL"
    if kind is not None:
        condition += " AND kind=:kind"
    values = {"org": user.org_id, "owner": user.id, "kind": kind, "limit": size, "offset": (page-1)*size}
    direction = "DESC" if sort.startswith("-") else "ASC"
    with transaction() as connection:
        total = connection.scalar(text("SELECT count(*) FROM memories WHERE " + condition), values)
        items = connection.execute(text("""
            SELECT id, kind, reason_code, content, structured, created_at FROM memories WHERE
        """ + condition + f" ORDER BY created_at {direction}, id {direction} LIMIT :limit OFFSET :offset"),
                                   values).mappings().all()
    return {"items": [dict(row) for row in items], "total": total, "page": page, "size": size}


def delete(user, memory_id):
    with transaction() as connection:
        row = connection.execute(text("""
            UPDATE memories SET deleted_at=now()
            WHERE id=:id AND org_id=:org AND owner_id=:owner AND deleted_at IS NULL RETURNING id
        """), {"id": memory_id, "org": user.org_id, "owner": user.id}).mappings().one_or_none()
    scope._checked(user, row, row is not None, "memory", memory_id)
