"""[TEST] 아이 프로필 사진·급식 참고 사진(API 75~77)이 범위대로 보이고, 퇴소하면 사라지는지 본다."""

import os
from dataclasses import replace

import pytest
from sqlalchemy import text

from app import backend
from app.core import media, users
from app.core.auth import issue_token
from app.maintenance import media_sweep, withdraw_child
from app.mock import seed
from app.modules.photos import photos as db_photos

BASE = "/api/v1"


@pytest.fixture
def media_root(monkeypatch, tmp_path):
    root = tmp_path / "media"
    monkeypatch.setattr(media, "settings", replace(media.settings, media_dir=str(root)))
    monkeypatch.setattr(backend, "photos", db_photos)
    return root


def auth(user_id):
    return {"Authorization": "Bearer " + issue_token(users.get_user(user_id))}


def photo(client, child_id, user_id):
    return client.get(f"{BASE}/children/{child_id}/profile-photo", headers=auth(user_id))


def test_children_lists_and_me_carry_server_profile_photos(media_root, db_client, seeded_db):
    kids = db_client.get(f"{BASE}/classrooms/{seed.CLASS_STAR}/children", headers=auth(seed.TEACHER)).json()["items"]
    assert len(kids) == 20 and all(k["profile_photo"] == {"file_url": f"{BASE}/children/{k['id']}/profile-photo"}
                                   for k in kids)
    me = db_client.get(f"{BASE}/me", headers=auth(seed.PARENT_OTHER)).json()["children"]
    assert {c["display_name"]: c["profile_photo"] is not None for c in me} == {"바다": True, "노을": True}
    assert (media_root / f"profiles/{seed.CHILD}.jpg").read_bytes() == seed.profile_photo(seed.CHILD).read_bytes()


def test_profile_photo_follows_child_scope(media_root, db_client, seeded_db):
    ok = photo(db_client, seed.CHILD, seed.PARENT)
    assert ok.status_code == 200 and ok.headers["content-type"] == "image/jpeg"
    assert ok.content == seed.profile_photo(seed.CHILD).read_bytes()
    assert photo(db_client, seed.CHILD, seed.TEACHER).status_code == 200
    assert photo(db_client, seed.CHILD_OTHER, seed.DIRECTOR).status_code == 200
    # 다른 집 아이·다른 반 아이는 404(거부 이력)예요.
    assert photo(db_client, seed.CHILD_OTHER, seed.PARENT).status_code == 404
    assert photo(db_client, seed.CHILD, seed.TEACHER_OTHER).status_code == 404
    assert db_client.get(f"{BASE}/children/{seed.CHILD}/profile-photo").status_code == 401
    with seeded_db.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM events WHERE action='permission_denied' "
                                      "AND detail->>'resource'='child'")) == 2


def test_withdraw_removes_profile_photo_and_seed_keeps_it_removed(media_root, db_client, seeded_db):
    from db.seeds.demo import seed_demo

    stored = media_root / f"profiles/{seed.CHILD}.jpg"
    todo = withdraw_child.withdraw(seed.CHILD)
    assert todo["profile_photo"] == f"profiles/{seed.CHILD}.jpg" and stored.exists()
    withdraw_child.withdraw(seed.CHILD, apply=True)
    assert not stored.exists()
    assert photo(db_client, seed.CHILD, seed.DIRECTOR).status_code == 404
    with seeded_db.begin() as connection:
        seed_demo(connection)
    with seeded_db.connect() as connection:
        assert connection.scalar(text("SELECT profile_photo_path FROM children WHERE id=:c"), {"c": seed.CHILD}) is None
    assert not stored.exists() and not withdraw_child.pending(withdraw_child.withdraw(seed.CHILD))


def test_meal_photos_list_and_file_are_org_scoped(media_root, db_client, seeded_db):
    listing = db_client.get(f"{BASE}/meal-photos", params={"from": "2026-11-23", "to": "2026-11-27"},
                            headers=auth(seed.PARENT))
    assert listing.status_code == 200
    items = listing.json()["items"]
    assert [i["meal_date"] for i in items] == [f"2026-11-{d}" for d in range(23, 28)]
    assert items[-1] == {"meal_date": "2026-11-27", "main_dish": "수육",
                         "file_url": f"{BASE}/meal-photos/2026-11-27/file"}
    image = db_client.get(items[-1]["file_url"], headers=auth(seed.TEACHER))
    assert image.status_code == 200 and image.headers["content-type"] == "image/webp"
    assert image.content == next(m for m in seed.meal_photos() if m["date"] == "2026-11-27")["path"].read_bytes()
    assert db_client.get(f"{BASE}/meal-photos/2026-11-28/file", headers=auth(seed.TEACHER)).status_code == 404
    for query in ({"from": "2026-11-27", "to": "2026-11-26"}, {"from": "2026-11-01", "to": "2027-01-15"},
                  {"from": "2026-11-27"}, {"from": "11/27", "to": "2026-11-27"}):
        assert db_client.get(f"{BASE}/meal-photos", params=query, headers=auth(seed.PARENT)).status_code == 422
    with seeded_db.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM meal_photos WHERE org_id=:org"), {"org": seed.ORG}) == 38


def test_sweep_finds_profile_files_left_without_a_child_path(media_root, seeded_db):
    stray = media_root / "profiles" / "left-after-failed-delete.jpg"
    stray.write_bytes(b"x")
    for path in (stray, media_root / f"profiles/{seed.CHILD}.jpg"):
        os.utime(path, (1, 1))
    assert media_sweep.sweep() == ["profiles/left-after-failed-delete.jpg"]
    assert media_sweep.sweep(apply=True) == ["profiles/left-after-failed-delete.jpg"]
    assert not stray.exists() and (media_root / f"profiles/{seed.CHILD}.jpg").exists()
