"""75~77번 API의 DB 판. 사진 파일은 MEDIA_DIR 하위 폴더(profiles/, meals/<org_id>/)에 있어요."""

from sqlalchemy import text

from app.core import media, scope
from app.core.db import transaction
from app.core.errors import ApiError
from app.core.photos import check_range, meal_view, media_type


def profile_file(user, child_id):
    # 학부모는 내 아이, 교사는 지금 맡은 반 아이, 원장은 원 전체. 범위 밖은 404예요.
    child = scope.child_in_scope(user, child_id)
    if not child["profile_photo_path"]:
        raise ApiError(404, "NOT_FOUND")
    return {"path": media.path(child["profile_photo_path"]), "media_type": media_type(child["profile_photo_path"])}


def meals(user, date_from, date_to):
    check_range(date_from, date_to)
    with transaction() as connection:
        rows = connection.execute(text("""
            SELECT meal_date, main_dish FROM meal_photos
            WHERE org_id=:org AND meal_date BETWEEN :a AND :b ORDER BY meal_date
        """), {"org": user.org_id, "a": date_from, "b": date_to}).mappings().all()
    return {"items": [meal_view(row["meal_date"], row["main_dish"]) for row in rows]}


def meal_file(user, meal_date):
    with transaction() as connection:
        row = connection.execute(text("SELECT storage_path, media_type FROM meal_photos WHERE org_id=:org AND meal_date=:d"),
                                 {"org": user.org_id, "d": meal_date}).mappings().one_or_none()
    if row is None:
        raise ApiError(404, "NOT_FOUND")
    return {"path": media.path(row["storage_path"]), "media_type": row["media_type"]}
