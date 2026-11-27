"""실제 DB와 같은 권한·정렬·삭제·명시 메모 우선 규칙이에요."""

from uuid import uuid4

from app.mock import store


def list_records(user, classroom_id, note_date):
    with store._lock:
        store.classroom_in_scope(user, classroom_id)
        return {"items": [dict(r) for r in _rows(user.org_id, classroom_id, note_date)]}


def _rows(org_id, classroom_id, note_date):
    return sorted((r for r in store.state().daily_records.values()
                   if (r["org_id"], r["classroom_id"], r["note_date"]) == (org_id, classroom_id, note_date)
                   and r["deleted_at"] is None), key=lambda r: (r["child_id"], r["created_at"], r["id"]))


def create(user, classroom_id, body):
    with store._lock:
        children = store.classroom_children(user, classroom_id)
        if body.child_id not in {c.id for c in children}:
            store.deny(user)
        row = {**body.model_dump(), "id": uuid4(), "org_id": user.org_id, "classroom_id": classroom_id,
               "author_id": user.id, "created_at": store.now(), "deleted_at": None}
        store.state().daily_records[row["id"]] = row
        return dict(row)


def delete(user, record_id):
    with store._lock:
        row = store.state().daily_records.get(record_id)
        if row is None or row["org_id"] != user.org_id or row["deleted_at"] is not None:
            store.deny(user)
        if row["author_id"] != user.id:
            store.classroom_in_scope(user, row["classroom_id"])
        row["deleted_at"] = store.now()


def with_record_memos(entry, memos):
    grouped = {}
    for row in _rows(entry.org_id, entry.classroom_id, entry.note_date):
        grouped.setdefault(row["child_id"], []).append(row["body"])
    return {**{child: "\n".join(lines) for child, lines in grouped.items()}, **memos}
