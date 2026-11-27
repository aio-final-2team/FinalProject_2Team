"""75~77번 API의 모의 판. 저장소 가상 사진 파일을 그대로 줘요."""

from datetime import date

from app.core.errors import ApiError
from app.core.photos import check_range, meal_view, media_type
from app.mock import seed, store


def profile_file(user, child_id):
    with store._lock:
        child = store.state().children.get(child_id)
        allowed = child is not None and child.org_id == user.org_id and (
            user.id in child.guardian_ids if user.role == "parent"
            else user.role == "director" or child.classroom_id in store.classroom_ids_of(user.id))
    path = seed.profile_photo(child_id) if allowed else None
    if path is None:
        raise ApiError(404, "NOT_FOUND")
    return {"path": path, "media_type": media_type(path)}


def _meals(user):
    return [m for m in seed.meal_photos() if user.org_id == seed.ORG]


def meals(user, date_from, date_to):
    check_range(date_from, date_to)
    return {"items": [meal_view(date.fromisoformat(m["date"]), m["main_dish"]) for m in _meals(user)
                      if date_from <= date.fromisoformat(m["date"]) <= date_to]}


def meal_file(user, meal_date):
    found = next((m for m in _meals(user) if m["date"] == meal_date.isoformat()), None)
    if found is None:
        raise ApiError(404, "NOT_FOUND")
    return {"path": found["path"], "media_type": media_type(found["path"])}
