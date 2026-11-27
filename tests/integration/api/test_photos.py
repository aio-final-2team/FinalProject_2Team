"""[TEST] 모의 API도 아이 프로필 사진·급식 참고 사진(API 75~77)을 같은 계약으로 준다."""

from app.mock import seed

BASE = "/api/v1"


def test_mock_children_carry_profile_photos_and_files_follow_scope(client, teacher, parent, teacher_other):
    kids = client.get(f"{BASE}/classrooms/{seed.CLASS_STAR}/children", headers=teacher).json()["items"]
    assert kids and all(k["profile_photo"]["file_url"] == f"{BASE}/children/{k['id']}/profile-photo" for k in kids)
    me = client.get(f"{BASE}/me", headers=parent).json()["children"]
    assert me[0]["profile_photo"] == {"file_url": f"{BASE}/children/{seed.CHILD}/profile-photo"}
    image = client.get(me[0]["profile_photo"]["file_url"], headers=parent)
    assert image.status_code == 200 and image.content == seed.profile_photo(seed.CHILD).read_bytes()
    assert client.get(f"{BASE}/children/{seed.CHILD_OTHER}/profile-photo", headers=parent).status_code == 404
    assert client.get(f"{BASE}/children/{seed.CHILD}/profile-photo", headers=teacher_other).status_code == 404


def test_mock_meal_photos(client, parent):
    items = client.get(f"{BASE}/meal-photos?from=2026-11-27&to=2026-11-27", headers=parent).json()["items"]
    assert items == [{"meal_date": "2026-11-27", "main_dish": "수육", "file_url": f"{BASE}/meal-photos/2026-11-27/file"}]
    assert client.get(items[0]["file_url"], headers=parent).headers["content-type"] == "image/webp"
    assert client.get(f"{BASE}/meal-photos/2026-11-28/file", headers=parent).status_code == 404
    assert client.get(f"{BASE}/meal-photos?from=2026-11-28&to=2026-11-27", headers=parent).status_code == 422
