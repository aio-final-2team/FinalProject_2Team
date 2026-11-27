"""아이 프로필 사진·급식 참고 사진의 응답 모양과 기간 검사. mock·DB 백엔드가 같이 써요."""

from app.core.errors import ApiError

MAX_MEAL_DAYS = 62
MEDIA_TYPES = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}


def profile_view(child_id, path):
    return {"file_url": f"/api/v1/children/{child_id}/profile-photo"} if path else None


def meal_view(meal_date, main_dish):
    return {"meal_date": meal_date, "main_dish": main_dish, "file_url": f"/api/v1/meal-photos/{meal_date}/file"}


def check_range(date_from, date_to):
    if date_to < date_from or (date_to - date_from).days >= MAX_MEAL_DAYS:
        raise ApiError(422, "VALIDATION_FAILED", field="to", problem=f"기간은 {MAX_MEAL_DAYS}일 안이어야 해요.")


def media_type(name):
    return MEDIA_TYPES.get(str(name).rsplit(".", 1)[-1].lower(), "image/jpeg")
