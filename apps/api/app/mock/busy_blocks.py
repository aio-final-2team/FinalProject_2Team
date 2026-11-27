"""바쁜 시간의 메모리 구현도 저장소 잠금과 같은 권한을 써요."""

from app.core.errors import ApiError
from app.mock import store
from app.mock.feed import record


def checked(user, row, allowed, resource, resource_id):
    if row is None or not allowed:
        record(user, "permission_denied", resource=resource, resource_id=str(resource_id))
        raise ApiError(404, "NOT_FOUND")


def view(row):
    return {"id": row["id"], "user_id": row["user_id"], "kind": row["kind"],
            "start_at": row["period"]["start"], "end_at": row["period"]["end"]}


def list_blocks(user, start, end, user_id):
    with store._lock:
        target = store.get_user(user_id)
        checked(user, target, target is not None and target.org_id == user.org_id
                and target.role in ("teacher", "director") and (user_id == user.id or user.role == "director"),
                "staff", user_id)
        return {"items": [view(b) for b in sorted(store.state().staff_busy_blocks,
                                                key=lambda b: (b["period"]["start"], b["id"]))
                          if b["org_id"] == user.org_id and b["user_id"] == user_id
                          and start < b["period"]["end"] and b["period"]["start"] < end]}


def create(user, body):
    with store._lock:
        if any(b.org_id == user.org_id and b.teacher_id == user.id and b.status == "confirmed"
               and body.start_at < (b.expected_end_at or b.period["end"]) and b.period["start"] < body.end_at
               for b in store.state().bookings.values()):
            raise ApiError(409, "SLOT_TAKEN")
        row = {"id": store.state().next_int(), "org_id": user.org_id, "user_id": user.id,
               "period": {"start": body.start_at, "end": body.end_at}, "kind": body.kind}
        store.state().staff_busy_blocks.append(row)
        return view(row)


def delete(user, block_id):
    with store._lock:
        row = next((b for b in store.state().staff_busy_blocks if b.get("id") == block_id
                    and b["org_id"] == user.org_id), None)
        checked(user, row, row is not None and row["user_id"] == user.id, "busy_block", block_id)
        store.state().staff_busy_blocks.remove(row)
