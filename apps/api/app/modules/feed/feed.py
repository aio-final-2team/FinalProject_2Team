"""[제안] T54 SQLAlchemy Core 구현. 파일 바이트는 PG에 넣지 않아요."""

import json
from uuid import uuid4

from sqlalchemy import text

from app.core import feed as rules, media
from app.core.db import transaction
from app.core.errors import ApiError
from app.core.request_id import active_trace_id


def record(connection, user, action, **detail):
    connection.execute(text("""
        INSERT INTO events(org_id,actor_type,actor_id,action,detail)
        VALUES (:org,'user',:actor,:action,CAST(:detail AS jsonb))
    """), {"org": user.org_id, "actor": user.id, "action": action,
           "detail": json.dumps({**detail, "trace_id": active_trace_id.get()})})


def deny(user, resource_id, status=403):
    # 오류로 업무 트랜잭션이 롤백되어도 권한 거부는 남겨요.
    with transaction() as connection:
        record(connection, user, "permission_denied", resource="feed", resource_id=str(resource_id))
    raise ApiError(status, "FORBIDDEN" if status == 403 else "NOT_FOUND")


def context(connection, user, lane, target_id):
    children = {r["id"]: dict(r) for r in connection.execute(text("""
        SELECT c.*, coalesce(array_agg(g.user_id) FILTER (WHERE g.user_id IS NOT NULL), '{}') AS guardian_ids
        FROM children c LEFT JOIN child_guardians g ON (g.child_id,g.org_id)=(c.id,c.org_id)
        WHERE c.org_id=:org GROUP BY c.id
    """), {"org": user.org_id}).mappings()}
    classrooms = set(connection.scalars(text("SELECT id FROM classrooms WHERE org_id=:org"), {"org": user.org_id}))
    rules.lane_access(user, lane, target_id, classrooms, children, lambda status: deny(user, target_id, status))
    return children


def checked(connection, user, post_id, *, lock=False, include_hidden=False, deleting=False):
    row = connection.execute(text("SELECT * FROM feed_posts WHERE id=:id AND org_id=:org" +
                                  (" FOR UPDATE" if lock else "")), {"id": post_id, "org": user.org_id}).mappings().one_or_none()
    if row is None:
        deny(user, post_id, 404)
    post = dict(row)
    children = {} if deleting and post["author_id"] == user.id else context(
        connection, user, post["lane"], post["classroom_id"] or post["org_id"])
    if post["deleted_at"] or (post["status"] == "hidden" and not include_hidden):
        raise ApiError(404, "NOT_FOUND")
    return post, children


def photos(connection, org_id, post_ids):
    return [dict(p) for p in connection.execute(text("""
        SELECT p.*, ARRAY(SELECT t.child_id FROM feed_photo_children t
                         WHERE t.photo_id=p.id AND t.org_id=p.org_id ORDER BY t.child_id) AS child_ids
        FROM feed_photos p WHERE p.org_id=:org AND p.post_id = ANY(:ids) ORDER BY p.created_at,p.id
    """), {"org": org_id, "ids": post_ids}).mappings()]


def posts(connection, user, lane, target_id, *, page=None, size=None, sort="-created_at"):
    order = "DESC" if sort.startswith("-") else "ASC"
    # PostgreSQL OFFSET은 bigint예요. 그보다 큰 페이지도 기존처럼 빈 목록으로 답해요.
    offset = min((page - 1) * size, 2**63 - 1) if page is not None else 0
    return [dict(p) for p in connection.execute(text("""
        SELECT * FROM feed_posts WHERE org_id=:org AND lane=:lane AND status='published' AND deleted_at IS NULL
          AND (:lane='org' OR classroom_id=:target)
    """ + f" ORDER BY created_at {order}, id {order}" + (" LIMIT :size OFFSET :offset" if page is not None else "")),
        {"org": user.org_id, "lane": lane, "target": target_id, "size": size, "offset": offset}).mappings()]


def check_access(user, lane, target_id):
    with transaction() as connection:
        context(connection, user, lane, target_id)


def listing(user, lane, target_id, page, size, sort):
    with transaction() as connection:
        children = context(connection, user, lane, target_id)
        total = connection.scalar(text("""
            SELECT count(*) FROM feed_posts WHERE org_id=:org AND lane=:lane AND status='published'
              AND deleted_at IS NULL AND (:lane='org' OR classroom_id=:target)
        """), {"org": user.org_id, "lane": lane, "target": target_id})
        rows = posts(connection, user, lane, target_id, page=page, size=size, sort=sort)
        grouped = {p["id"]: [] for p in rows}
        for photo in photos(connection, user.org_id, list(grouped)):
            grouped[photo["post_id"]].append(photo)
        return {"items": [rules.post_view(user, p, grouped[p["id"]], children) for p in rows],
                "total": total, "page": page, "size": size}


def create(user, lane, target_id, body, uploads):
    saved = []
    try:
        with transaction() as connection:
            children = context(connection, user, lane, target_id)
            for _, _, tags in uploads:
                rules.tags_in_scope(lane, target_id, tags, children)
            post = dict(connection.execute(text("""
                INSERT INTO feed_posts(org_id,lane,classroom_id,author_id,body)
                VALUES (:org,:lane,:class,:author,:body) RETURNING *
            """), {"org": user.org_id, "lane": lane, "class": target_id if lane == "class" else None,
                   "author": user.id, "body": body}).mappings().one())
            for data, metadata, tags in uploads:
                name = media.save(data, metadata)
                saved.append(name)
                photo_id = uuid4()
                connection.execute(text("""
                    INSERT INTO feed_photos(id,org_id,post_id,storage_path,media_type,size_bytes,sha256,created_at)
                    VALUES (:id,:org,:post,:path,:media_type,:size_bytes,:sha256,clock_timestamp())
                """), {**metadata, "id": photo_id, "org": user.org_id, "post": post["id"], "path": name})
                for child_id in tags:
                    connection.execute(text("""
                        INSERT INTO feed_photo_children(photo_id,org_id,child_id) VALUES (:photo,:org,:child)
                    """), {"photo": photo_id, "org": user.org_id, "child": child_id})
            record(connection, user, "feed_post_created", post_id=str(post["id"]))
            result = rules.post_view(user, post, photos(connection, user.org_id, [post["id"]]), children)
        return result
    except Exception:
        for name in saved:
            media.remove(name)
        raise


def detail(user, post_id):
    with transaction() as connection:
        post, children = checked(connection, user, post_id)
        return rules.post_view(user, post, photos(connection, user.org_id, [post_id]), children)


def album(user, lane, target_id, child_id, page, size, sort):
    with transaction() as connection:
        children = context(connection, user, lane, target_id)
        if child_id is not None and (user.role != "parent" or child_id not in children
                                    or user.id not in children[child_id]["guardian_ids"]):
            deny(user, child_id)
        items = []
        for post in posts(connection, user, lane, target_id):
            items.extend(rules.photo_view(p) for p in photos(connection, user.org_id, [post["id"]])
                         if (child_id is None or child_id in p["child_ids"]) and rules.visible(user, post, p, children))
        return rules.page(items, page, size, sort)


def file(user, photo_id):
    with transaction() as connection:
        row = connection.execute(text("SELECT post_id FROM feed_photos WHERE id=:id AND org_id=:org"),
                                 {"id": photo_id, "org": user.org_id}).mappings().one_or_none()
        if row is None:
            deny(user, photo_id, 404)
        post, children = checked(connection, user, row["post_id"])
        photo = next(p for p in photos(connection, user.org_id, [post["id"]]) if p["id"] == photo_id)
        if not rules.visible(user, post, photo, children):
            raise ApiError(404, "NOT_FOUND")
        return photo


def delete(user, post_id):
    with transaction() as connection:
        post, _ = checked(connection, user, post_id, lock=True, include_hidden=True, deleting=True)
        if post["author_id"] != user.id:
            deny(user, post_id)
        paths = [p["storage_path"] for p in photos(connection, user.org_id, [post_id])]
        connection.execute(text("UPDATE feed_posts SET deleted_at=now() WHERE id=:id AND org_id=:org"),
                           {"id": post_id, "org": user.org_id})
        record(connection, user, "feed_post_deleted", post_id=str(post_id))
    # DB 커밋 실패 때는 파일을 보존해요. 디스크 정리 실패는 고아 파일만 남겨요.
    for name in paths:
        media.remove(name)


def hide(user, post_id):
    with transaction() as connection:
        post, children = checked(connection, user, post_id, lock=True, include_hidden=True)
        if post["lane"] != "org" or user.role != "director":
            deny(user, post_id)
        if post["status"] != "hidden":
            connection.execute(text("UPDATE feed_posts SET status='hidden' WHERE id=:id AND org_id=:org"),
                               {"id": post_id, "org": user.org_id})
            post["status"] = "hidden"
            record(connection, user, "feed_post_hidden", post_id=str(post_id))
        return rules.post_view(user, post, photos(connection, user.org_id, [post_id]), children)


def photo_scope(user, child_id, value=None):
    with transaction() as connection:
        child = connection.execute(text("SELECT * FROM children WHERE id=:id AND org_id=:org" +
                                        (" FOR NO KEY UPDATE" if value is not None else "")),
                                   {"id": child_id, "org": user.org_id}).mappings().one_or_none()
        if child is None:
            deny(user, child_id, 404)
        guardian = connection.scalar(text("""
            SELECT EXISTS(SELECT 1 FROM child_guardians WHERE child_id=:child AND org_id=:org AND user_id=:user)
        """), {"child": child_id, "org": user.org_id, "user": user.id})
        if user.role != "parent" or not guardian:
            deny(user, child_id)
        scope = child["photo_scope"]
        if value is not None and value != scope:
            connection.execute(text("UPDATE children SET photo_scope=:scope WHERE id=:id AND org_id=:org"),
                               {"scope": value, "id": child_id, "org": user.org_id})
            record(connection, user, "photo_scope_changed", child_id=str(child_id), before=scope, after=value)
            scope = value
        return {"child_id": child_id, "photo_scope": scope}
