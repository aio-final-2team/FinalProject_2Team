"""영상 파일의 메타데이터·원본 사진 연결만 PG에 저장해요."""

from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core import growth_video as rules
from app.core.db import transaction
from app.core.errors import ApiError
from app.modules.feed import feed


def access(user, child_id):
    try:
        with transaction() as c:
            check_access(c, user, child_id)
    except ApiError as error:
        feed.deny(user, child_id, error.status)


def check_access(c, user, child_id):
    child = c.scalar(text("SELECT id FROM children WHERE id=:id AND org_id=:org FOR UPDATE"),
                     {"id": child_id, "org": user.org_id})
    if child is None:
        raise ApiError(404, "NOT_FOUND")
    guardian = c.scalar(text("SELECT EXISTS(SELECT 1 FROM child_guardians "
                             "WHERE child_id=:child AND org_id=:org AND user_id=:user)"),
                        {"child": child_id, "org": user.org_id, "user": user.id})
    if user.role != "parent" or not guardian:
        raise ApiError(403, "FORBIDDEN")


def create(user, child_id, limit):
    try:
        with transaction() as c:
            check_access(c, user, child_id)
            rules.check_capacity(c.execute(text("SELECT status FROM growth_videos WHERE child_id=:child "
                                                "AND deleted_at IS NULL"), {"child": child_id}).mappings().all())
            video_id = uuid4()
            row = c.execute(text("""
                INSERT INTO growth_videos(id,org_id,child_id,requested_by,storage_path,photo_count)
                VALUES (:id,:org,:child,:user,:path,:count) RETURNING *
            """), {"id": video_id, "org": user.org_id, "child": child_id, "user": user.id,
                   "path": f"videos/{video_id}.mp4", "count": limit}).mappings().one()
            # 자리를 잡은 뒤 메타데이터만 읽어요. 422면 행도 함께 롤백해요.
            ids = rules.select(candidates(user, child_id, connection=c), limit)
            c.execute(text("UPDATE growth_videos SET photo_count=:count WHERE id=:id"),
                      {"count": len(ids), "id": video_id})
            c.execute(text("INSERT INTO growth_video_photos(video_id,org_id,photo_id,position) VALUES (:id,:org,:photo,:pos)"),
                      [{"id": video_id, "org": user.org_id, "photo": pid, "pos": pos} for pos, pid in enumerate(ids)])
            feed.record(c, user, "growth_video_requested", video_id=str(video_id))
            row = {**row, "photo_count": len(ids)}
    except ApiError as error:
        if error.status in {403, 404}:
            feed.deny(user, child_id, error.status)
        raise
    except IntegrityError as error:
        if getattr(error.orig.diag, "constraint_name", None) == "growth_videos_pending_child_idx":
            raise ApiError(409, "CONFLICT", "이 아이의 성장 영상을 만들고 있어요.") from None
        raise
    return rules.view(row)


def candidates(user, child_id, *, connection=None):
    if connection is None:
        with transaction() as c:
            return candidates(user, child_id, connection=c)
    ids = list(connection.scalars(text("SELECT photo_id FROM feed_photo_children "
                                       "WHERE child_id=:child AND org_id=:org"),
                                  {"child": child_id, "org": user.org_id}))
    return sources(user, ids, connection=connection)


def sources(user, ids, *, connection=None):
    if connection is None:
        with transaction() as c:
            return sources(user, ids, connection=c)
    c = connection
    rows = list(c.execute(text("SELECT DISTINCT post_id FROM feed_photos WHERE id=ANY(:ids)"),
                          {"ids": ids}).scalars())
    posts = {r["id"]: dict(r) for r in c.execute(text("SELECT * FROM feed_posts WHERE id=ANY(:ids)"),
                                                {"ids": rows}).mappings()}
    photos = {p["id"]: p for p in feed.photos(c, rows)}
    orgs = list({user.org_id, *(p["org_id"] for p in posts.values())})
    children = {r["id"]: dict(r) for r in c.execute(text("""
        SELECT c.*,ARRAY(SELECT user_id FROM child_guardians g WHERE g.child_id=c.id) AS guardian_ids
        FROM children c WHERE org_id=ANY(:orgs)
    """), {"orgs": orgs}).mappings()}
    classrooms = set(c.scalars(text("SELECT id FROM classrooms WHERE org_id=:org"), {"org": user.org_id}))
    organizations = {r["id"]: dict(r) for r in c.execute(text("SELECT id,region FROM organizations")).mappings()}
    return rules.visible_sources(user, [photos[i] for i in ids if i in photos], posts, children,
                                 classrooms, organizations)


def checked(c, user, video_id, *, lock=False):
    row = c.execute(text("SELECT * FROM growth_videos WHERE id=:id AND org_id=:org AND deleted_at IS NULL" +
                         (" FOR UPDATE" if lock else "")), {"id": video_id, "org": user.org_id}).mappings().one_or_none()
    if row is None:
        raise ApiError(404, "NOT_FOUND")
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
    access(user, row["child_id"])
    if row["status"] != "succeeded" or len(ids) != row["photo_count"]:
        raise ApiError(404, "NOT_FOUND")
    rules.source_photos(user, ids)
    return dict(row)


def delete(user, video_id):
    with transaction() as c:
        child_id = checked(c, user, video_id)["child_id"]
    access(user, child_id)
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


def finish(video_id, result, *, failure_reason=None):
    with transaction() as c:
        row = c.execute(text("""
            UPDATE growth_videos SET status=:status,duration_seconds=:duration,size_bytes=:size,sha256=:sha,
                failure_reason=:reason,photo_count=coalesce(:count,photo_count),
                completed_at=now() WHERE id=:id AND status='running' AND deleted_at IS NULL RETURNING *
        """), {"id": video_id, "status": "succeeded" if result else "failed",
               "duration": result["duration_seconds"] if result else None, "size": result["size_bytes"] if result else None,
               "sha": result["sha256"] if result else None, "reason": failure_reason,
               "count": result.get("photo_count") if result else None}).mappings().one_or_none()
        if row:
            if result and "photo_ids" in result:
                c.execute(text("DELETE FROM growth_video_photos WHERE video_id=:id"), {"id": video_id})
                c.execute(text("INSERT INTO growth_video_photos(video_id,org_id,photo_id,position) "
                               "VALUES (:id,:org,:photo,:pos)"),
                          [{"id": video_id, "org": row["org_id"], "photo": pid, "pos": pos}
                           for pos, pid in enumerate(result["photo_ids"])])
            complete(c, row)
        return row is not None


def sweep(*, all_pending=False):
    with transaction() as c:
        rows = c.execute(text("""
            UPDATE growth_videos SET status='failed',completed_at=now()
            WHERE status IN ('queued','running') AND deleted_at IS NULL
                AND (:all OR (status='queued' AND created_at<now()-make_interval(secs=>:queued))
                     OR (status='running' AND started_at<now()-make_interval(secs=>:running))) RETURNING *
        """), {"all": all_pending, "queued": rules.QUEUED_TIMEOUT, "running": rules.JOB_TIMEOUT}).mappings().all()
        for row in rows:
            complete(c, row)
    for row in rows:
        rules.remove(row["storage_path"])
    rules.clean_temp()
    return len(rows)
