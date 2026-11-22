"""[제안] T54 메모리 구현. 요청 하나는 기존 저장소 잠금 안에서 처리해요."""

import logging
from uuid import uuid4

from app.core import feed as rules, media
from app.core.errors import ApiError
from app.core.request_id import active_trace_id
from app.mock import store

log = logging.getLogger(__name__)


def record(user, action, **detail):
    state = store.state()
    state.events.append(store.Event(state.next_int(), user.org_id, action, actor_type="user", actor_id=user.id,
                                    detail={**detail, "trace_id": active_trace_id.get()}))


def deny(user, resource_id, status=403):
    record(user, "permission_denied", resource="feed", resource_id=str(resource_id))
    raise ApiError(status, "FORBIDDEN" if status == 403 else "NOT_FOUND")


def context(user, lane, target_id):
    state = store.state()
    children = {c.id: c.__dict__ for c in state.children.values() if c.org_id in org_ids(user, lane)}
    classrooms = {c.id for c in state.classrooms.values() if c.org_id == user.org_id}
    rules.lane_access(user, lane, target_id, classrooms, children,
                      lambda status: deny(user, target_id, status), state.organizations)
    return children


def org_ids(user, lane):
    organizations = store.state().organizations
    region = rules.neighborhood_region(organizations.get(user.org_id, {}))
    return {oid for oid, org in organizations.items() if region is not None and org["region"] == region} if (
        lane == "neighborhood") else {user.org_id}


def checked(user, post_id, *, include_hidden=False, deleting=False):
    post = store.state().feed_posts.get(post_id)
    if post is None:
        deny(user, post_id, 404)
    if post["lane"] == "neighborhood":
        rules.neighborhood_enabled()
    elif post["org_id"] != user.org_id:
        deny(user, post_id, 404)
    children = {c.id: c.__dict__ for c in store.state().children.values() if c.org_id == user.org_id} if (
        deleting and post["author_id"] == user.id) else context(
        user, post["lane"], post["classroom_id"] or post["org_id"])
    if post["deleted_at"] or (post["status"] == "hidden" and not include_hidden):
        raise ApiError(404, "NOT_FOUND")
    return {**post, "org_name": store.state().organizations.get(post["org_id"], {}).get("name")}, children


def photos(post_id):
    return [p for p in store.state().feed_photos.values() if p["post_id"] == post_id]


def check_access(user, lane, target_id):
    with store._lock:
        context(user, lane, target_id)


def listing(user, lane, target_id, page, size, sort):
    with store._lock:
        children = context(user, lane, target_id)
        items = [rules.post_view(user, {**p, "org_name": store.state().organizations[p["org_id"]]["name"]},
                                 photos(p["id"]), children) for p in store.state().feed_posts.values()
                 if p["org_id"] in org_ids(user, lane) and p["lane"] == lane and not p["deleted_at"]
                 and p["status"] == "published" and (lane != "class" or p["classroom_id"] == target_id)]
        return rules.page(items, page, size, sort)


def create(user, lane, target_id, body, uploads):
    with store._lock:
        children = context(user, lane, target_id)
        for _, _, tags in uploads:
            rules.tags_in_scope(lane, target_id, tags, children, user)
        post = {"id": uuid4(), "org_id": user.org_id, "lane": lane,
                "classroom_id": target_id if lane == "class" else None, "author_id": user.id, "body": body,
                "status": "published", "created_at": store.now(), "deleted_at": None}
        added = []
        try:
            for data, metadata, tags in uploads:
                added.append({"id": uuid4(), "post_id": post["id"], "org_id": user.org_id,
                              **metadata, "storage_path": media.save(data, metadata, mock=True), "child_ids": tags,
                              "created_at": store.now()})
        except Exception:
            for photo in added:
                media.remove(photo["storage_path"])
            raise
        store.state().feed_posts[post["id"]] = post
        store.state().feed_photos.update((p["id"], p) for p in added)
        record(user, "feed_post_created", post_id=str(post["id"]))
        return rules.post_view(user, {**post, "org_name": store.state().organizations[user.org_id]["name"]}, added, children)


def detail(user, post_id):
    with store._lock:
        post, children = checked(user, post_id)
        return rules.post_view(user, post, photos(post_id), children)


def album(user, lane, target_id, child_id, page, size, sort):
    with store._lock:
        children = context(user, lane, target_id)
        if child_id is not None and (user.role != "parent" or child_id not in children
                                    or user.id not in children[child_id]["guardian_ids"]):
            deny(user, child_id)
        items = []
        for p in store.state().feed_posts.values():
            if (p["org_id"] not in org_ids(user, lane) or p["lane"] != lane or p["deleted_at"] or p["status"] != "published"
                    or (lane == "class" and p["classroom_id"] != target_id)):
                continue
            items.extend(rules.photo_view(photo) for photo in photos(p["id"])
                         if (child_id is None or child_id in photo["child_ids"]) and rules.visible(user, p, photo, children))
        return rules.page(items, page, size, sort)


def file(user, photo_id):
    with store._lock:
        photo = store.state().feed_photos.get(photo_id)
        if photo is None:
            deny(user, photo_id, 404)
        post, children = checked(user, photo["post_id"])
        if not rules.visible(user, post, photo, children):
            raise ApiError(404, "NOT_FOUND")
        return dict(photo)


def delete(user, post_id):
    with store._lock:
        post, _ = checked(user, post_id, include_hidden=True, deleting=True)
        if post["author_id"] != user.id:
            deny(user, post_id)
        post_photos = photos(post_id)
        record(user, "feed_post_deleted", post_id=str(post_id))
        store.state().feed_posts[post_id]["deleted_at"] = store.now()
    for photo in post_photos:
        try:
            media.remove(photo["storage_path"])
        except OSError:
            log.warning("feed_photo_delete_failed photo_id=%s", photo["id"])


def hide(user, post_id):
    with store._lock:
        post, children = checked(user, post_id, include_hidden=True)
        if post["lane"] != "org" or user.role != "director" or post["org_id"] != user.org_id:
            deny(user, post_id)
        if post["status"] != "hidden":
            post["status"] = "hidden"
            store.state().feed_posts[post_id]["status"] = "hidden"
            record(user, "feed_post_hidden", post_id=str(post_id))
        return rules.post_view(user, post, photos(post_id), children)


def photo_scope(user, child_id, value=None):
    if value == "neighborhood" and not rules.settings.feature_neighborhood_feed:
        raise ApiError(422, "VALIDATION_FAILED", field="photo_scope")
    with store._lock:
        child = store.state().children.get(child_id)
        if child is None or child.org_id != user.org_id:
            deny(user, child_id, 404)
        if user.role != "parent" or user.id not in child.guardian_ids:
            deny(user, child_id)
        if value is not None and value != child.photo_scope:
            before, child.photo_scope = child.photo_scope, value
            record(user, "photo_scope_changed", child_id=str(child_id), before=before, after=value)
        return {"child_id": child_id, "photo_scope": child.photo_scope}
