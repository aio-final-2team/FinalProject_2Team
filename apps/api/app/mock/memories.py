from copy import deepcopy

from app.mock import store


def list_memories(user, kind, page, size, sort):
    with store._lock:
        items = [m for m in store.state().memories.values() if m.org_id == user.org_id and m.owner_id == user.id
                 and m.deleted_at is None and (kind is None or m.kind == kind)]
        items.sort(key=lambda m: (m.created_at, m.id), reverse=sort.startswith("-"))
        return {"items": [{key: deepcopy(getattr(m, key)) for key in
                           ("id", "kind", "reason_code", "content", "structured", "created_at")}
                          for m in items[(page-1)*size:page*size]], "total": len(items), "page": page, "size": size}


def delete(user, memory_id):
    with store._lock:
        memory = store.state().memories.get(memory_id)
        if memory is None or memory.org_id != user.org_id or memory.owner_id != user.id or memory.deleted_at is not None:
            store.deny(user)
        memory.deleted_at = store.now()
