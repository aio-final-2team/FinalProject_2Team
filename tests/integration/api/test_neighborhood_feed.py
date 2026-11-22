"""[TEST] 선택 동네 칸의 기관 간 공개·익명 표시·현재 사진 권한을 두 모드로 검사해요."""

from dataclasses import replace
from uuid import UUID

import pytest
from sqlalchemy import text

from app import backend
from app.core import config, feed as rules, media
from app.core.auth import issue_token
from app.core.db import transaction
from app.mock import feed, seed, store
from tests.integration.api.conftest import _login
from tests.integration.api.helpers import BASE, err
from tests.integration.api.test_feed import CLASS, ORG, audit, create, post, scope, unlink

NEIGHBORHOOD = BASE + "/neighborhood"
NEIGHBOR, FOREIGN = seed.NEIGHBORHOOD_ORGS


@pytest.fixture(autouse=True, params=["mock", "db"])
def neighborhood_backend(request, monkeypatch, tmp_path, _reset_store):
    settings = replace(config.settings, feature_neighborhood_feed=True)
    monkeypatch.setattr(config, "settings", settings)
    monkeypatch.setattr(rules, "settings", settings)
    monkeypatch.setattr(media, "settings", replace(media.settings, media_dir=str(tmp_path)))
    if request.param == "db":
        request.getfixturevalue("seeded_db")
        from app.core import users
        from app.modules.feed import feed as db_feed
        modules = users, db_feed
    else:
        store.reset()
        modules = store, feed
    for name, module in zip(("users", "feed"), modules, strict=True):
        monkeypatch.setattr(backend, name, module)
    return request.param


@pytest.fixture
def neighbor(client):
    return _login(client, NEIGHBOR["login_id"])


@pytest.fixture
def foreign(client):
    return _login(client, FOREIGN["login_id"])


def set_region(mode, org_id, value):
    if mode == "mock":
        store.state().organizations[org_id]["region"] = value
    else:
        with transaction() as connection:
            connection.execute(text("UPDATE organizations SET region=:value WHERE id=:id"), {"value": value, "id": org_id})


def paths(own):
    return [NEIGHBORHOOD + "/posts", NEIGHBORHOOD + "/albums", f"{BASE}/posts/{own['id']}", own["photos"][0]["file_url"]]


def test_same_neighborhood_cross_org_read_write_and_anonymous_author(client, parent, neighbor):
    own = post(client, parent, root=NEIGHBORHOOD)
    other = post(client, neighbor, root=NEIGHBORHOOD)
    for actor in (parent, neighbor):
        rows = client.get(NEIGHBORHOOD + "/posts", headers=actor).json()["items"]
        assert {p["id"] for p in rows} == {own["id"], other["id"]}
        for item in (own, other):
            viewed = client.get(f"{BASE}/posts/{item['id']}", headers=actor).json()["post"]
            assert viewed == item and viewed["author_id"] is None
            assert viewed["author_label"] == ("가상 햇살유치원 보호자" if item == own else "가상 달빛어린이집 보호자")
            assert set(viewed) == {"id", "lane", "classroom_id", "author_id", "author_label", "body", "status", "created_at", "photos"}
            assert viewed["classroom_id"] is None
            response = client.get(item["photos"][0]["file_url"], headers=actor)
            assert response.content == seed.feed_png()
            assert response.headers["cache-control"] == "private, no-store"
            assert response.headers["x-content-type-options"] == "nosniff"


def test_foreign_neighborhood_hidden_from_list_album_detail_file_and_mutations(client, parent, foreign):
    own = post(client, parent, root=NEIGHBORHOOD)
    post(client, foreign, root=NEIGHBORHOOD)
    for path in (f"{BASE}/posts/{own['id']}", own["photos"][0]["file_url"]):
        err(client.get(path, headers=foreign), 404, "NOT_FOUND")
    for suffix in ("/posts", "/albums"):
        rows = client.get(NEIGHBORHOOD + suffix, headers=foreign).json()
        assert rows["total"] == 1
        assert own["id"] not in {r.get("post_id", r["id"]) for r in rows["items"]}
    err(client.delete(f"{BASE}/posts/{own['id']}", headers=foreign), 404, "NOT_FOUND")
    err(client.patch(f"{BASE}/posts/{own['id']}", headers=foreign, json={"status": "hidden"}), 404, "NOT_FOUND")


@pytest.mark.parametrize("actor", ["teacher", "teacher_other", "director"])
def test_staff_denied_all_read_surfaces_and_upload_with_events(client, parent, actor, request, neighborhood_backend):
    own = post(client, parent, root=NEIGHBORHOOD)
    before = len(audit(neighborhood_backend))
    headers = {**request.getfixturevalue(actor), "X-Request-ID": "t60-denied"}
    for path in paths(own):
        err(client.get(path, headers=headers), 403, "FORBIDDEN")
    err(create(client, headers, root=NEIGHBORHOOD), 403, "FORBIDDEN")
    denied = audit(neighborhood_backend)[before:]
    assert len(denied) == 5 and all(e["action"] == "permission_denied" for e in denied)
    assert all(e["detail"]["trace_id"] == "t60-denied" for e in denied)


def test_null_region_denied_and_empty_region_is_an_exact_string(client, parent, neighborhood_backend):
    set_region(neighborhood_backend, seed.ORG, None)
    before = len(audit(neighborhood_backend))
    for suffix in ("/posts", "/albums"):
        err(client.get(NEIGHBORHOOD + suffix, headers=parent), 403, "FORBIDDEN")
    err(create(client, parent, root=NEIGHBORHOOD), 403, "FORBIDDEN")
    assert len(audit(neighborhood_backend)) == before + 3
    set_region(neighborhood_backend, seed.ORG, "")
    assert client.get(NEIGHBORHOOD + "/posts", headers=parent).status_code == 200


def test_parent_without_current_child_denied(client, parent, neighborhood_backend):
    unlink(neighborhood_backend, seed.CHILD, seed.PARENT)
    err(client.get(NEIGHBORHOOD + "/posts", headers=parent), 403, "FORBIDDEN")


@pytest.mark.parametrize("value,visible", [("family", False), ("class", False), ("org", False), ("neighborhood", True)])
def test_photo_scope_filters_list_detail_album_and_file(client, parent, parent_other, neighbor, value, visible):
    assert scope(client, parent, seed.CHILD, value).status_code == 200
    own = post(client, parent, root=NEIGHBORHOOD, tags=[[seed.CHILD]])
    for actor in (parent_other, neighbor):
        for path in (NEIGHBORHOOD + "/posts", f"{BASE}/posts/{own['id']}"):
            payload = client.get(path, headers=actor).json()
            viewed = payload["items"][0] if "items" in payload else payload["post"]
            assert bool(viewed["photos"]) is visible
        album = client.get(NEIGHBORHOOD + "/albums", headers=actor).json()
        assert album["total"] == int(visible)
        response = client.get(own["photos"][0]["file_url"], headers=actor)
        assert response.status_code == (200 if visible else 404)
    assert client.get(own["photos"][0]["file_url"], headers=parent).status_code == 200


def test_scope_and_region_changes_apply_immediately_to_old_photos(client, parent, neighbor, neighborhood_backend):
    own = post(client, parent, root=NEIGHBORHOOD, tags=[[seed.CHILD]])
    for value, code in (("neighborhood", 200), ("org", 404), ("neighborhood", 200)):
        assert scope(client, parent, seed.CHILD, value).status_code == 200
        assert client.get(own["photos"][0]["file_url"], headers=neighbor).status_code == code
    set_region(neighborhood_backend, NEIGHBOR["id"], "가상동 ")
    assert client.get(NEIGHBORHOOD + "/posts", headers=neighbor).json()["total"] == 0
    err(client.get(own["photos"][0]["file_url"], headers=neighbor), 404, "NOT_FOUND")


def test_only_own_children_can_be_tagged_and_album_filter_is_own_child(client, parent, neighbor):
    for child_id in (seed.CHILD_OTHER, NEIGHBOR["child_id"]):
        err(create(client, parent, root=NEIGHBORHOOD, tags=[[child_id]]), 422, "VALIDATION_FAILED")
    own = post(client, neighbor, root=NEIGHBORHOOD, tags=[[NEIGHBOR["child_id"]]])
    assert client.get(NEIGHBORHOOD + "/albums", headers=neighbor,
                      params={"child_id": str(NEIGHBOR["child_id"])}).json()["total"] == 1
    err(client.get(NEIGHBORHOOD + "/albums", headers=parent,
                   params={"child_id": str(NEIGHBOR["child_id"])}), 403, "FORBIDDEN")
    err(client.get(own["photos"][0]["file_url"], headers=parent), 404, "NOT_FOUND")


@pytest.mark.parametrize("root", [CLASS, ORG])
def test_neighborhood_scope_covers_existing_lanes_without_changing_payload(client, parent, parent_other, root):
    assert scope(client, parent, seed.CHILD, "neighborhood").status_code == 200
    own = post(client, parent, root=root, tags=[[seed.CHILD]])
    assert "author_label" not in own and own["author_id"] == str(seed.PARENT)
    assert client.get(own["photos"][0]["file_url"], headers=parent_other).status_code == 200


def test_delete_only_author_and_hiding_only_author_org_director(client, parent, neighbor, director, neighborhood_backend):
    own = post(client, parent, root=NEIGHBORHOOD)
    photo = backend.feed.file(backend.users.get_user(seed.PARENT), UUID(own["photos"][0]["id"]))
    path = media.path(photo["storage_path"])
    err(client.delete(f"{BASE}/posts/{own['id']}", headers=neighbor), 403, "FORBIDDEN")
    err(client.patch(f"{BASE}/posts/{own['id']}", headers=parent, json={"status": "hidden"}), 403, "FORBIDDEN")
    # 같은 동네 다른 기관 원장에게는 숨김 권한이 없어요.
    director_id = seed.demo_id("399")
    if neighborhood_backend == "mock":
        store.state().users[director_id] = store.User(director_id, NEIGHBOR["id"], "director", "director-n01",
                                                      "unused", "[TEST] 다른 원장")
    else:
        with transaction() as connection:
            connection.execute(text("""
                INSERT INTO users(id,org_id,role,login_id,display_name,password_hash)
                VALUES (:id,:org,'director','director-n01','[TEST] 다른 원장','unused')
            """), {"id": director_id, "org": NEIGHBOR["id"]})
    headers = {"Authorization": "Bearer " + issue_token(backend.users.get_user(director_id))}
    err(client.patch(f"{BASE}/posts/{own['id']}", headers=headers, json={"status": "hidden"}), 403, "FORBIDDEN")
    response = client.patch(f"{BASE}/posts/{own['id']}", headers=director, json={"status": "hidden"})
    assert response.status_code == 200 and response.json()["post"]["status"] == "hidden"
    err(client.get(own["photos"][0]["file_url"], headers=neighbor), 404, "NOT_FOUND")
    assert client.delete(f"{BASE}/posts/{own['id']}", headers=parent).status_code == 204
    assert not path.exists()
    assert {e["action"] for e in audit(neighborhood_backend)} >= {"feed_post_hidden", "feed_post_deleted"}


def test_existing_pagination_and_sort_and_anonymous_auth(client, parent):
    created = [post(client, parent, root=NEIGHBORHOOD) for _ in range(3)]
    for suffix in ("/posts", "/albums"):
        result = client.get(NEIGHBORHOOD + suffix, headers=parent, params={"size": 1, "page": 2, "sort": "created_at"}).json()
        assert result["total"] == 3 and len(result["items"]) == 1 and result["page"] == 2
        assert client.get(NEIGHBORHOOD + suffix, headers=parent, params={"page": 10**30}).json()["items"] == []
        err(client.get(NEIGHBORHOOD + suffix, headers=parent, params={"size": 101}), 422, "VALIDATION_FAILED")
        err(client.get(NEIGHBORHOOD + suffix), 401, "UNAUTHENTICATED")
    assert client.get(NEIGHBORHOOD + "/posts", headers=parent).json()["items"][0]["id"] == created[-1]["id"]


def test_flag_off_hides_new_and_shared_routes_but_keeps_existing_feed(client, parent, monkeypatch):
    own = post(client, parent, root=NEIGHBORHOOD)
    monkeypatch.setattr(rules, "settings", replace(rules.settings, feature_neighborhood_feed=False))
    for actor in ({}, parent):
        for path in (NEIGHBORHOOD + "/posts", NEIGHBORHOOD + "/albums"):
            err(client.get(path, headers=actor), 404, "NOT_FOUND")
        err(create(client, actor, root=NEIGHBORHOOD), 404, "NOT_FOUND")
    for path in (f"{BASE}/posts/{own['id']}", own["photos"][0]["file_url"]):
        err(client.get(path, headers=parent), 404, "NOT_FOUND")
    err(client.delete(f"{BASE}/posts/{own['id']}", headers=parent), 404, "NOT_FOUND")
    err(client.patch(f"{BASE}/posts/{own['id']}", headers=parent, json={"status": "hidden"}), 404, "NOT_FOUND")
    assert client.get(CLASS + "/posts", headers=parent).status_code == 200
