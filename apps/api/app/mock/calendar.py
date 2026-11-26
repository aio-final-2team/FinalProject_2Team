"""[제안] DB와 같은 날짜 추출·범위 규칙을 쓰는 일정 대역이에요."""

from dataclasses import asdict

from app.mock import store
from app.mock.documents import chunks
from app.mock.feed import record
from app.core.calendar import items


def listing(user, start, end):
    with store._lock:
        state = store.state()
        documents = [asdict(d) | {"classroom_ids": state.document_classrooms.get(d.id, []),
                     "is_virtual": d.source == "virtual", "chunks": [asdict(c) for c in chunks(d)]}
                     for d in sorted(state.documents.values(), key=lambda d: d.id) if d.org_id == user.org_id]
        return items(user, documents, start, end, lambda document_id: record(
            user, "permission_denied", resource="document", resource_id=str(document_id)))
