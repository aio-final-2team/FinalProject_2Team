"""가상 영상의 메모리 상태 전이는 DB와 같아요."""

from datetime import timedelta
from uuid import uuid4

from app.core import growth_video as rules
from app.core.errors import ApiError
from app.mock import feed, store


def access(user, child_id):
    feed.photo_scope(user, child_id)


def create(user, child_id, limit):
    with store._lock:
        access(user, child_id)
        rules.check_capacity([r for r in store.state().growth_videos.values()
                              if r["child_id"] == child_id and not r["deleted_at"]])
        video_id = uuid4()
        row = dict(id=video_id, org_id=user.org_id, child_id=child_id, requested_by=user.id, status="queued",
                   storage_path=f"mock/videos/{video_id}.mp4", photo_count=limit, photo_ids=[], failure_reason=None,
                   duration_seconds=None, size_bytes=None, sha256=None, created_at=store.now(),
                   started_at=None, completed_at=None, deleted_at=None)
        store.state().growth_videos[video_id] = row
        try:
            ids = rules.select(candidates(user, child_id), limit)
        except Exception:
            del store.state().growth_videos[video_id]
            raise
        row.update(photo_count=len(ids), photo_ids=ids)
        feed.record(user, "growth_video_requested", video_id=str(video_id))
        return rules.view(row)


def candidates(user, child_id):
    with store._lock:
        return sources(user, [p["id"] for p in store.state().feed_photos.values() if child_id in p["child_ids"]])


def sources(user, ids):
    with store._lock:
        state = store.state()
        return rules.visible_sources(user, [state.feed_photos[i] for i in ids if i in state.feed_photos],
                                     state.feed_posts, {i: c.__dict__ for i, c in state.children.items()},
                                     {i for i, c in state.classrooms.items() if c.org_id == user.org_id},
                                     state.organizations)


def checked(user, video_id):
    row = store.state().growth_videos.get(video_id)
    if row is None or row["org_id"] != user.org_id or row["deleted_at"]:
        raise ApiError(404, "NOT_FOUND")
    access(user, row["child_id"])
    return row


def listing(user, child_id):
    with store._lock:
        access(user, child_id)
        rows = [r for r in store.state().growth_videos.values() if r["child_id"] == child_id and not r["deleted_at"]]
        return {"items": [rules.view(r) for r in sorted(rows, key=lambda r: (r["created_at"], r["id"]), reverse=True)]}


def file(user, video_id):
    with store._lock:
        row = checked(user, video_id)
        if row["status"] != "succeeded":
            raise ApiError(404, "NOT_FOUND")
        rules.source_photos(user, row["photo_ids"])
        return dict(row)


def delete(user, video_id):
    with store._lock:
        row = checked(user, video_id)
        row["deleted_at"] = store.now()
        if row["status"] in {"queued", "running"}:
            row.update(status="failed", completed_at=store.now())
        feed.record(user, "growth_video_deleted", video_id=str(video_id))
    rules.remove(row["storage_path"])


def claim(video_id):
    with store._lock:
        row = store.state().growth_videos.get(video_id)
        if row is None or row["status"] != "queued" or row["deleted_at"]:
            return None
        row.update(status="running", started_at=store.now())
        return dict(row)


def finish(video_id, result, *, failure_reason=None):
    with store._lock:
        row = store.state().growth_videos[video_id]
        if row["status"] != "running" or row["deleted_at"]:
            return False
        row.update(status="succeeded" if result else "failed", completed_at=store.now(),
                   failure_reason=failure_reason, **(result or {}))
        feed.record(store.state().users[row["requested_by"]], "growth_video_completed",
                    video_id=str(video_id), status=row["status"])
        return True


def sweep(*, all_pending=False):
    with store._lock:
        rows = [dict(r) for r in store.state().growth_videos.values() if r["status"] in {"queued", "running"}
                and not r["deleted_at"] and (all_pending or (r["started_at"] or r["created_at"])
                < store.now() - timedelta(seconds=rules.QUEUED_TIMEOUT if r["status"] == "queued"
                                          else rules.JOB_TIMEOUT))]
        for row in rows:
            store.state().growth_videos[row["id"]]["status"] = "running"
            finish(row["id"], None)
    for row in rows:
        rules.remove(row["storage_path"])
    rules.clean_temp()
    return len(rows)
