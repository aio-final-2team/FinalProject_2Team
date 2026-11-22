"""영상 파일의 메타데이터·원본 사진 연결만 PG에 저장해요."""

from uuid import uuid4

from sqlalchemy import text

from app.core import growth_video as rules
from app.core.db import transaction
from app.core.errors import ApiError
from app.modules.feed import feed


def access(user, child_id):
    feed.photo_scope(user, child_id)


def create(user, child_id, limit):
    access(user, child_id)
    with transaction() as c:
        candidates = c.execute(text("""
            SELECT p.id,p.created_at FROM feed_photos p JOIN feed_photo_children t ON t.photo_id=p.id
            WHERE t.child_id=:child AND t.org_id=:org
        """), {"child": child_id, "org": user.org_id}).mappings()
        ids = rules.select(user, candidates, limit)
        video_id = uuid4()
        row = c.execute(text("""
            INSERT INTO growth_videos(id,org_id,child_id,requested_by,storage_path,photo_count)
            VALUES (:id,:org,:child,:user,:path,:count) RETURNING *
        """), {"id": video_id, "org": user.org_id, "child": child_id, "user": user.id,
               "path": f"videos/{video_id}.mp4", "count": len(ids)}).mappings().one()
        c.execute(text("INSERT INTO growth_video_photos(video_id,org_id,photo_id,position) VALUES (:id,:org,:photo,:pos)"),
                  [{"id": video_id, "org": user.org_id, "photo": pid, "pos": pos} for pos, pid in enumerate(ids)])
        feed.record(c, user, "growth_video_requested", video_id=str(video_id))
    return rules.view(row)


def checked(c, user, video_id, *, lock=False):
    row = c.execute(text("SELECT * FROM growth_videos WHERE id=:id AND org_id=:org AND deleted_at IS NULL" +
                         (" FOR UPDATE" if lock else "")), {"id": video_id, "org": user.org_id}).mappings().one_or_none()
    if row is None:
        raise ApiError(404, "NOT_FOUND")
    access(user, row["child_id"])
    return row


def photo_ids(c, video_id):
    return list(c.scalars(text("SELECT photo_id FROM growth_video_photos WHERE video_id=:id ORDER BY position"),
                          {"id": video_id}))


def listing(user, child_id):
    access(user, child_id)
    with transaction() as c:
        rows = c.execute(text("SELECT * FROM growth_videos WHERE child_id=:child AND org_id=:org "
                              "AND deleted_at IS NULL ORDER BY created_at DESC,id DESC"),
                         {"child": child_id, "org": user.org_id}).mappings()
        return {"items": [rules.view(r) for r in rows]}


def file(user, video_id):
    with transaction() as c:
        row = checked(c, user, video_id)
        ids = photo_ids(c, video_id)
    if row["status"] != "succeeded" or len(ids) != row["photo_count"]:
        raise ApiError(404, "NOT_FOUND")
    rules.source_photos(user, ids)
    return dict(row)


def delete(user, video_id):
    with transaction() as c:
        row = checked(c, user, video_id, lock=True)
        c.execute(text("""
            UPDATE growth_videos SET deleted_at=now(),
                status=CASE WHEN status IN ('queued','running') THEN 'failed' ELSE status END,
                completed_at=CASE WHEN status IN ('queued','running') THEN now() ELSE completed_at END WHERE id=:id
        """), {"id": video_id})
        feed.record(c, user, "growth_video_deleted", video_id=str(video_id))
    rules.remove(row["storage_path"])


def claim(video_id):
    with transaction() as c:
        row = c.execute(text("UPDATE growth_videos SET status='running',started_at=now() "
                              "WHERE id=:id AND status='queued' AND deleted_at IS NULL RETURNING *"),
                         {"id": video_id}).mappings().one_or_none()
        return {**row, "photo_ids": photo_ids(c, video_id)} if row else None


def complete(c, row):
    from app.core.auth import CurrentUser
    user = CurrentUser(id=row["requested_by"], org_id=row["org_id"], role="parent")
    feed.record(c, user, "growth_video_completed", video_id=str(row["id"]), status=row["status"])


def finish(video_id, result):
    with transaction() as c:
        row = c.execute(text("""
            UPDATE growth_videos SET status=:status,duration_seconds=:duration,size_bytes=:size,sha256=:sha,
                completed_at=now() WHERE id=:id AND status='running' AND deleted_at IS NULL RETURNING *
        """), {"id": video_id, "status": "succeeded" if result else "failed",
               "duration": result["duration_seconds"] if result else None, "size": result["size_bytes"] if result else None,
               "sha": result["sha256"] if result else None}).mappings().one_or_none()
        if row:
            complete(c, row)
        return row is not None


def sweep(*, all_pending=False):
    with transaction() as c:
        rows = c.execute(text("""
            UPDATE growth_videos SET status='failed',completed_at=now()
            WHERE status IN ('queued','running') AND deleted_at IS NULL
                AND (:all OR coalesce(started_at,created_at)<now()-make_interval(secs=>:timeout)) RETURNING *
        """), {"all": all_pending, "timeout": rules.JOB_TIMEOUT}).mappings().all()
        for row in rows:
            complete(c, row)
    for row in rows:
        rules.remove(row["storage_path"])
    return len(rows)
