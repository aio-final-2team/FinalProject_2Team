"""DB와 같은 권한·상태 전이를 쓰는 가상 음성 메모리 저장소예요."""

from datetime import timedelta
from uuid import uuid4

from app.core import media, voice_analysis as rules
from app.core.errors import ApiError
from app.mock import store, video_consult


def access(user, booking_id, *, write=False):
    with store._lock:
        booking = store.state().bookings.get(booking_id)
        return rules.authorize(user, booking.__dict__ if booking else None,
                               lambda: video_consult.record(user, booking_id, "permission_denied"), write=write)


def _event(row, action, **detail):
    store.add_event(store.state().requests[row["request_id"]], action, analysis_id=str(row["id"]), **detail)


def create(user, booking_id, data, metadata):
    with store._lock:
        booking = access(user, booking_id, write=True)
        name = media.save(data, metadata, mock=True)
        row = {"id": uuid4(), "org_id": user.org_id, "booking_id": booking_id, "request_id": booking["request_id"],
               "storage_path": name, "sha256": metadata["sha256"], "duration_seconds": metadata["duration_seconds"],
               "status": "queued", "transcript": "", "result": {"summary": "", "parent_requests": [], "follow_ups": []},
               "created_at": store.now(), "started_at": None, "completed_at": None}
        store.state().voice_analyses[row["id"]] = row
        _event(row, "voice_analysis_requested", actor_type="user", actor_id=user.id)
        return rules.view(row)


def get(user, analysis_id):
    with store._lock:
        row = store.state().voice_analyses.get(analysis_id)
        if row is None or row["org_id"] != user.org_id:
            raise ApiError(404, "NOT_FOUND")
        access(user, row["booking_id"])
        return rules.view(row)


def listing(user, booking_id):
    with store._lock:
        access(user, booking_id)
        rows = [r for r in store.state().voice_analyses.values() if r["booking_id"] == booking_id]
        return {"items": [rules.view(r) for r in sorted(rows, key=lambda r: (r["created_at"], r["id"]), reverse=True)]}


def claim(analysis_id):
    with store._lock:
        row = store.state().voice_analyses.get(analysis_id)
        if row is None or row["status"] != "queued":
            return None
        row.update(status="running", started_at=store.now())
        return dict(row)


def finish(analysis_id, result):
    with store._lock:
        row = store.state().voice_analyses[analysis_id]
        if row["status"] == "running":
            row.update(status="succeeded" if result else "failed", storage_path=None, completed_at=store.now())
            if result:
                row.update(result)
            _event(row, "voice_analysis_completed", status=row["status"])


def sweep():
    with store._lock:
        rows = [dict(r) for r in store.state().voice_analyses.values() if r["status"] == "running"
                and r["started_at"] < store.now() - timedelta(seconds=rules.VOICE_TIMEOUT)]
        for row in rows:
            finish(row["id"], None)
    for row in rows:
        rules.remove(row["storage_path"])
    return len(rows)
