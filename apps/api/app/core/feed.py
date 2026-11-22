"""[제안] T54: 칸 권한을 먼저 검사하고, 사진마다 현재 공개 범위를 계산해요."""

from app.core.errors import ApiError


def lane_access(user, lane, target_id, classrooms, children, deny):
    if lane == "org":
        if target_id != user.org_id:
            deny(404)
    else:
        if target_id not in classrooms:
            deny(404)
        if user.role != "parent" or not any(
            c["classroom_id"] == target_id and user.id in c["guardian_ids"] for c in children.values()
        ):
            deny(403)


def tags_in_scope(lane, target_id, tags, children):
    for child_id in tags:
        child = children.get(child_id)
        if child is None or (lane == "class" and child["classroom_id"] != target_id):
            raise ApiError(422, "VALIDATION_FAILED", child_id=str(child_id))


def visible(user, post, photo, children):
    if post["author_id"] == user.id:
        return True
    return all(child_id in children and (
        user.id in children[child_id]["guardian_ids"]
        or children[child_id]["photo_scope"] == "org"
        or (children[child_id]["photo_scope"] == "class" and post["lane"] == "class")
    ) for child_id in photo["child_ids"])


def photo_view(photo):
    # 내부 저장 경로·숨은 사진의 태그/건수는 응답에 넣지 않아요.
    return {key: photo[key] for key in ("id", "post_id", "media_type", "size_bytes", "created_at")} | {
        "file_url": f"/api/v1/photos/{photo['id']}/file"}


def post_view(user, post, photos, children):
    return {key: post[key] for key in ("id", "lane", "classroom_id", "author_id", "body", "status", "created_at")} | {
        "photos": [photo_view(p) for p in photos if visible(user, post, p, children)]}


def page(items, page, size, sort):
    items.sort(key=lambda row: (row["created_at"], row["id"]), reverse=sort.startswith("-"))
    return {"items": items[(page-1)*size:page*size], "total": len(items), "page": page, "size": size}
