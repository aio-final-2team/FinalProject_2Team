"""[제안] T54: 칸 권한을 먼저 검사하고, 사진마다 현재 공개 범위를 계산해요."""

from app.core.errors import ApiError
from app.core.config import settings


def neighborhood_enabled():
    if not settings.feature_neighborhood_feed:
        raise ApiError(404, "NOT_FOUND")


def neighborhood_region(organization):
    region = organization.get("region")
    # PostgreSQL nullif(btrim(region),'')와 같게, 값이 있는 문자열은 그대로 비교해요.
    return region if region is not None and region.strip(" ") else None


def lane_access(user, lane, target_id, classrooms, children, deny, organizations=None):
    if lane == "neighborhood":
        neighborhood_enabled()
        own = organizations.get(user.org_id, {})
        target = organizations.get(target_id, {})
        region = neighborhood_region(own)
        if target_id != user.org_id and (
            user.role != "parent" or region is None or neighborhood_region(target) != region
        ):
            deny(404)
        if (user.role != "parent" or region is None or not any(
            c["org_id"] == user.org_id and user.id in c["guardian_ids"] for c in children.values()
        )):
            deny(403)
    elif lane == "org":
        if target_id != user.org_id:
            deny(404)
    else:
        if target_id not in classrooms:
            deny(404)
        if user.role != "parent" or not any(
            c["classroom_id"] == target_id and user.id in c["guardian_ids"] for c in children.values()
        ):
            deny(403)


def tags_in_scope(lane, target_id, tags, children, user=None):
    for child_id in tags:
        child = children.get(child_id)
        if (child is None or (lane == "class" and child["classroom_id"] != target_id)
                or (lane == "neighborhood" and user.id not in child["guardian_ids"])):
            raise ApiError(422, "VALIDATION_FAILED", child_id=str(child_id))


def visible(user, post, photo, children):
    if post["author_id"] == user.id:
        return True
    return all(child_id in children and (
        user.id in children[child_id]["guardian_ids"]
        or children[child_id]["photo_scope"] == "neighborhood"
        or (children[child_id]["photo_scope"] == "org" and post["lane"] in ("class", "org"))
        or (children[child_id]["photo_scope"] == "class" and post["lane"] == "class")
    ) for child_id in photo["child_ids"])


def photo_view(photo):
    # 내부 저장 경로·숨은 사진의 태그/건수는 응답에 넣지 않아요.
    return {key: photo[key] for key in ("id", "post_id", "media_type", "size_bytes", "created_at")} | {
        "file_url": f"/api/v1/photos/{photo['id']}/file"}


def post_view(user, post, photos, children):
    result = {key: post[key] for key in ("id", "lane", "classroom_id", "author_id", "body", "status", "created_at")} | {
        "photos": [photo_view(p) for p in photos if visible(user, post, p, children)]}
    if post["lane"] == "neighborhood":
        result.update(author_id=None, author_label=f"{post['org_name']} 보호자")
    return result


def page(items, page, size, sort):
    items.sort(key=lambda row: (row["created_at"], row["id"]), reverse=sort.startswith("-"))
    return {"items": items[(page-1)*size:page*size], "total": len(items), "page": page, "size": size}
