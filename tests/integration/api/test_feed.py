"""[제안] T54·AC-06: 같은 HTTP 계약을 mock·임시 PostgreSQL에서 검사해요."""

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from app import backend
from app.core import media
from app.core.constants import MAX_PHOTO_BYTES, MAX_POST_BYTES
from app.core.auth import issue_token
from app.core.db import transaction
from app.mock import feed, seed, store
from tests.integration.api.helpers import BASE, err

CLASS = f"{BASE}/classrooms/{seed.CLASS_STAR}"
ORG = f"{BASE}/organizations/{seed.ORG}"


@pytest.fixture(autouse=True, params=["mock", "db"])
def feed_backend(request, monkeypatch, tmp_path, _reset_store):
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


def create(client, actor, root=CLASS, tags=None, data=None, body="[TEST] 가상 피드", **fields):
    tags = [[]] if tags is None else tags
    files = [("files", ("virtual.exe", data or seed.feed_png(), "application/octet-stream")) for _ in tags]
    return client.post(root + "/posts", headers=actor, files=files,
                       data={"body": body, "child_ids": json.dumps([[str(c) for c in t] for t in tags]), **fields})


def post(client, actor, **kwargs):
    response = create(client, actor, **kwargs)
    assert response.status_code == 201, response.text
    return response.json()["post"]


def audit(mode):
    if mode == "mock":
        return [e.__dict__ for e in store.state().events]
    with transaction() as connection:
        return [dict(e) for e in connection.execute(text("SELECT * FROM events ORDER BY id")).mappings()]


def unlink(mode, child_id, user_id):
    if mode == "mock":
        child = store.state().children[child_id]
        child.guardian_ids = [u for u in child.guardian_ids if u != user_id]
    else:
        with transaction() as connection:
            connection.execute(text("DELETE FROM child_guardians WHERE child_id=:child AND user_id=:user"),
                               {"child": child_id, "user": user_id})


def scope(client, actor, child_id, value):
    return client.patch(f"{BASE}/children/{child_id}/photo-scope", headers=actor, json={"photo_scope": value})


@pytest.mark.parametrize("actor", ["teacher", "director", "parent_other"])
def test_class_all_read_surfaces_and_write_deny_with_persistent_events(client, parent, actor, request, feed_backend):
    own = post(client, parent)
    if actor == "parent_other":
        unlink(feed_backend, seed.demo_id("503"), seed.PARENT_OTHER)
    headers = {**request.getfixturevalue(actor), "X-Request-ID": "t54-denied"}
    before = len(audit(feed_backend))
    for path in (CLASS + "/posts", CLASS + "/albums", f"{BASE}/posts/{own['id']}", own["photos"][0]["file_url"]):
        err(client.get(path, headers=headers), 403, "FORBIDDEN")
    err(create(client, headers), 403, "FORBIDDEN")
    denied = audit(feed_backend)[before:]
    assert len(denied) == 5 and all(e["action"] == "permission_denied" for e in denied)
    assert all(e["detail"]["trace_id"] == "t54-denied" for e in denied)


def test_org_every_member_can_read_and_write_and_file_has_private_headers(client, parent, parent_other, teacher, teacher_other, director):
    for actor in (parent, parent_other, teacher, teacher_other, director):
        own = post(client, actor, root=ORG)
        assert client.get(ORG + "/posts", headers=actor).status_code == 200
        assert client.get(ORG + "/albums", headers=actor).status_code == 200
        response = client.get(own["photos"][0]["file_url"], headers=parent)
        assert response.status_code == 200 and response.content == seed.feed_png()
        assert response.headers["cache-control"] == "private, no-store"
        assert response.headers["content-type"] == "image/png"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["content-disposition"] == "inline"
        assert "storage_path" not in json.dumps(own) and "sha256" not in json.dumps(own)


def test_foreign_organization_is_404_even_for_real_post_photo_child_and_class(client, parent, feed_backend):
    own = post(client, parent)
    foreign = uuid4()
    user_id = uuid4()
    if feed_backend == "mock":
        store.state().users[user_id] = store.User(user_id, foreign, "parent", "foreign", "unused", "[TEST] 외부")
    else:
        with transaction() as connection:
            connection.execute(text("INSERT INTO organizations(id,name) VALUES (:id,'[TEST] 외부')"), {"id": foreign})
            connection.execute(text("""
                INSERT INTO users(id,org_id,role,login_id,display_name,password_hash)
                VALUES (:id,:org,'parent',:login,'[TEST] 외부','unused')
            """), {"id": user_id, "org": foreign, "login": str(user_id)})
    headers = {"Authorization": "Bearer " + issue_token(backend.users.get_user(user_id))}
    for path in (CLASS + "/posts", CLASS + "/albums", ORG + "/posts", ORG + "/albums",
                 f"{BASE}/posts/{own['id']}", own["photos"][0]["file_url"], f"{BASE}/children/{seed.CHILD}/photo-scope"):
        err(client.get(path, headers=headers), 404, "NOT_FOUND")
    err(create(client, headers), 404, "NOT_FOUND")
    err(create(client, headers, root=ORG), 404, "NOT_FOUND")
    err(create(client, headers, data=b"invalid"), 404, "NOT_FOUND")
    err(scope(client, headers, seed.CHILD, "org"), 404, "NOT_FOUND")


@pytest.mark.parametrize("lane,value,expected", [(CLASS, "family", False), (CLASS, "class", True),
    (CLASS, "org", True), (ORG, "family", False), (ORG, "class", False), (ORG, "org", True)])
def test_photo_scope_filters_all_surfaces_and_uploader_always_sees(client, parent, parent_other, lane, value, expected):
    assert scope(client, parent, seed.CHILD, value).status_code == 200
    own = post(client, parent_other, root=lane, tags=[[seed.CHILD], []])
    guarded = own["photos"][0]
    # 올린 사람은 family에도 보이고, 그 아이 보호자도 보여요.
    for actor in (parent, parent_other):
        assert client.get(guarded["file_url"], headers=actor).status_code == 200
    # 같은 반의 다른 보호자로 검사해요(노을 보호자는 올린 사람이라 별도 계정 사용).
    login = next(u["login_id"] for u in seed.USERS if u["role"] == "parent" and u["id"] not in (seed.PARENT, seed.PARENT_OTHER))
    from tests.integration.api.conftest import _login
    viewer = _login(client, login)
    detail = client.get(f"{BASE}/posts/{own['id']}", headers=viewer).json()["post"]
    listing = client.get(lane + "/posts", headers=viewer).json()["items"]
    listed = next(p for p in listing if p["id"] == own["id"])
    album = client.get(lane + "/albums", headers=viewer).json()
    assert len(detail["photos"]) == len(listed["photos"]) == (2 if expected else 1)
    assert (guarded["id"] in {p["id"] for p in album["items"]}) is expected
    response = client.get(guarded["file_url"], headers=viewer)
    assert response.status_code == (200 if expected else 404)
    assert all("child_ids" not in p for p in detail["photos"])


def test_scope_changes_apply_to_old_photos_immediately_and_all_tagged_children_must_allow(client, parent, parent_other, teacher):
    own = post(client, parent, root=ORG, tags=[[seed.CHILD, seed.demo_id("503")]])
    url = own["photos"][0]["file_url"]
    err(client.get(url, headers=teacher), 404, "NOT_FOUND")
    assert scope(client, parent, seed.CHILD, "org").status_code == 200
    err(client.get(url, headers=teacher), 404, "NOT_FOUND")
    assert scope(client, parent_other, seed.demo_id("503"), "org").status_code == 200
    assert client.get(url, headers=teacher).status_code == 200
    assert scope(client, parent, seed.CHILD, "family").status_code == 200
    err(client.get(url, headers=teacher), 404, "NOT_FOUND")
    detail = client.get(f"{BASE}/posts/{own['id']}", headers=teacher).json()["post"]
    assert detail["photos"] == []


@pytest.mark.parametrize("actor", ["parent_other", "teacher", "director"])
def test_only_current_child_guardian_can_read_or_change_scope(client, parent, actor, request, feed_backend):
    path = f"{BASE}/children/{seed.CHILD}/photo-scope"
    assert client.get(path, headers=parent).json()["photo_scope"] == "family"
    headers = request.getfixturevalue(actor)
    err(client.get(path, headers=headers), 403, "FORBIDDEN")
    err(scope(client, headers, seed.CHILD, "org"), 403, "FORBIDDEN")
    assert scope(client, parent, seed.CHILD, "org").status_code == 200
    changes = [e for e in audit(feed_backend) if e["action"] == "photo_scope_changed"]
    assert len(changes) == 1 and changes[0]["detail"]["before"] == "family"
    assert changes[0]["detail"]["after"] == "org"
    unlink(feed_backend, seed.CHILD, seed.PARENT)
    err(scope(client, parent, seed.CHILD, "class"), 403, "FORBIDDEN")


def test_last_guardian_update_wins_and_filter_only_own_child(client, parent, parent_other, feed_backend):
    if feed_backend == "mock":
        child = store.state().children[seed.CHILD]
        child.guardian_ids = [*child.guardian_ids, seed.PARENT_OTHER]
    else:
        with transaction() as connection:
            connection.execute(text("INSERT INTO child_guardians(org_id,child_id,user_id,relation) VALUES (:org,:child,:user,'other')"),
                               {"org": seed.ORG, "child": seed.CHILD, "user": seed.PARENT_OTHER})
    assert scope(client, parent, seed.CHILD, "org").status_code == 200
    assert scope(client, parent_other, seed.CHILD, "family").status_code == 200
    assert client.get(f"{BASE}/children/{seed.CHILD}/photo-scope", headers=parent).json()["photo_scope"] == "family"
    own = post(client, parent, tags=[[seed.CHILD], []])
    result = client.get(CLASS + "/albums", headers=parent, params={"child_id": str(seed.CHILD)}).json()
    assert own["photos"][0]["id"] in {p["id"] for p in result["items"]}
    assert own["photos"][1]["id"] not in {p["id"] for p in result["items"]}
    err(client.get(CLASS + "/albums", headers=parent, params={"child_id": str(seed.CHILD_OTHER)}), 403, "FORBIDDEN")


def test_author_delete_erases_files_and_hidden_post_can_still_be_deleted(client, parent, parent_other, director, feed_backend):
    own = post(client, parent, root=ORG, tags=[[], []])
    paths = [media.path(backend.feed.file(backend.users.get_user(seed.PARENT), UUID(p["id"]))["storage_path"]) for p in own["photos"]]
    err(client.delete(f"{BASE}/posts/{own['id']}", headers=parent_other), 403, "FORBIDDEN")
    err(client.delete(f"{BASE}/posts/{own['id']}", headers=director), 403, "FORBIDDEN")
    assert all(p.is_file() for p in paths)
    assert client.patch(f"{BASE}/posts/{own['id']}", headers=director, json={"status": "hidden"}).status_code == 200
    assert client.delete(f"{BASE}/posts/{own['id']}", headers=parent).status_code == 204
    assert all(not p.exists() for p in paths)
    err(client.get(f"{BASE}/posts/{own['id']}", headers=parent), 404, "NOT_FOUND")
    for photo in own["photos"]:
        err(client.get(photo["file_url"], headers=parent), 404, "NOT_FOUND")
    assert any(e["action"] == "feed_post_deleted" for e in audit(feed_backend))


def test_director_hide_only_org_and_hidden_photos_disappear_everywhere(client, parent, teacher, director, feed_backend):
    own = post(client, parent, root=ORG)
    err(client.patch(f"{BASE}/posts/{own['id']}", headers=teacher, json={"status": "hidden"}), 403, "FORBIDDEN")
    for _ in range(2):
        assert client.patch(f"{BASE}/posts/{own['id']}", headers=director, json={"status": "hidden"}).status_code == 200
    for actor in (parent, director):
        err(client.get(f"{BASE}/posts/{own['id']}", headers=actor), 404, "NOT_FOUND")
        err(client.get(own["photos"][0]["file_url"], headers=actor), 404, "NOT_FOUND")
        assert own["id"] not in {p["id"] for p in client.get(ORG + "/posts", headers=actor).json()["items"]}
        assert own["photos"][0]["id"] not in {p["id"] for p in client.get(ORG + "/albums", headers=actor).json()["items"]}
    assert len([e for e in audit(feed_backend) if e["action"] == "feed_post_hidden"]) == 1
    other = post(client, parent)
    err(client.patch(f"{BASE}/posts/{other['id']}", headers=director, json={"status": "hidden"}), 403, "FORBIDDEN")


@pytest.mark.parametrize("case", ["body-empty", "body-long", "too-many", "too-big", "bad-magic", "tag-other-class", "tag-unknown", "tag-duplicate", "tag-count", "tag-json"])
def test_upload_rejects_invalid_input_without_files_or_partial_post(client, parent, case, tmp_path, feed_backend):
    before = set(tmp_path.iterdir())
    fields = {}
    if case == "body-empty":
        fields["body"] = " "
    if case == "body-long":
        fields["body"] = "x" * 2001
    if case == "too-many":
        fields["tags"] = [[]] * 11
    if case == "too-big":
        fields["data"] = seed.feed_png() + b"x" * MAX_PHOTO_BYTES
    if case == "bad-magic":
        fields["data"] = b"pretend.png"
    if case == "tag-other-class":
        fields["tags"] = [[seed.CHILD_OTHER]]
    if case == "tag-unknown":
        fields["tags"] = [[uuid4()]]
    if case == "tag-duplicate":
        fields["tags"] = [[seed.CHILD, seed.CHILD]]
    if case == "tag-count":
        fields["child_ids"] = "[[],[]]"
    if case == "tag-json":
        fields["child_ids"] = "oops"
    total = client.get(CLASS + "/posts", headers=parent).json()["total"]
    err(create(client, parent, **fields), 422, "VALIDATION_FAILED")
    assert set(tmp_path.iterdir()) == before
    assert client.get(CLASS + "/posts", headers=parent).json()["total"] == total


def test_text_only_and_ten_photos_and_existing_list_pagination(client, parent):
    text_post = post(client, parent, tags=[])
    assert text_post["photos"] == []
    own = post(client, parent, tags=[[]] * 10)
    assert len(own["photos"]) == 10
    for suffix in ("/posts", "/albums"):
        result = client.get(CLASS + suffix, headers=parent, params={"size": 1, "sort": "created_at"}).json()
        assert result["size"] == 1 and len(result["items"]) == 1 and result["page"] == 1
        assert client.get(CLASS + suffix, headers=parent, params={"page": 10**30}).json()["items"] == []
        err(client.get(CLASS + suffix, headers=parent, params={"size": 101}), 422, "VALIDATION_FAILED")
        err(client.get(CLASS + suffix, headers=parent, params={"sort": "bad"}), 422, "VALIDATION_FAILED")
    rows = client.get(CLASS + "/posts", headers=parent).json()["items"]
    assert [p["id"] for p in rows[:2]] == [own["id"], text_post["id"]]


def test_seed_four_posts_five_photos_and_anonymous_rejection(client, parent, feed_backend):
    for root in (CLASS, ORG):
        assert client.get(root + "/posts", headers=parent).json()["total"] == 2
        err(client.get(root + "/posts"), 401, "UNAUTHENTICATED")
    rows = [p for root in (CLASS, ORG) for p in client.get(root + "/posts", headers=parent).json()["items"]]
    assert {p["id"] for p in rows} == {str(p["id"]) for p in seed.FEED_POSTS}
    assert len(seed.FEED_PHOTOS) == 5
    err(client.get(f"{BASE}/photos/{seed.FEED_PHOTOS[0][0]}/file"), 401, "UNAUTHENTICATED")


@pytest.mark.parametrize("signature,kind", [(b"\xff\xd8\xff", "image/jpeg"), (b"RIFFxxxxWEBP", "image/webp")])
def test_format_uses_signature_even_with_misleading_filename_and_mime(client, parent, signature, kind):
    own = post(client, parent, data=signature + b"[TEST] synthetic signature")
    result = client.get(own["photos"][0]["file_url"], headers=parent)
    assert result.status_code == 200 and result.headers["content-type"] == kind


def test_exact_five_mb_is_accepted_and_tags_do_not_leak_hidden_count(client, parent, teacher):
    data = seed.feed_png()
    own = post(client, parent, root=ORG, data=data + b"x" * (MAX_PHOTO_BYTES-len(data)), tags=[[seed.CHILD]])
    assert own["photos"][0]["size_bytes"] == MAX_PHOTO_BYTES
    assert client.get(own["photos"][0]["file_url"], headers=parent).content == data + b"x" * (MAX_PHOTO_BYTES-len(data))
    before = client.get(ORG + "/albums", headers=teacher).json()
    assert own["photos"][0]["id"] not in {p["id"] for p in before["items"]}
    assert scope(client, parent, seed.CHILD, "org").status_code == 200
    after = client.get(ORG + "/albums", headers=teacher).json()
    assert after["total"] == before["total"] + 1


def test_partial_disk_write_failure_cleans_saved_files_and_rolls_back_post(client, parent, monkeypatch, tmp_path, feed_backend):
    total = client.get(CLASS + "/posts", headers=parent).json()["total"]
    before = set(tmp_path.iterdir())
    original = media.save
    calls = 0
    def fail_second(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("[TEST] disk full")
        return original(*args, **kwargs)
    monkeypatch.setattr(media, "save", fail_second)
    err(create(client, parent, tags=[[], []]), 500, "INTERNAL_ERROR")
    assert set(tmp_path.iterdir()) == before
    assert client.get(CLASS + "/posts", headers=parent).json()["total"] == total


def test_delete_and_file_reads_concurrently_twenty_rounds(client, parent):
    with ThreadPoolExecutor(max_workers=5) as pool:
        for _ in range(20):
            own = post(client, parent, root=ORG)
            barrier = Barrier(5)
            def read():
                barrier.wait(timeout=10)
                result = client.get(own["photos"][0]["file_url"], headers=parent)
                assert result.status_code in (200, 404), result.text
                if result.status_code == 200:
                    assert result.content == seed.feed_png()
            def delete():
                barrier.wait(timeout=10)
                assert client.delete(f"{BASE}/posts/{own['id']}", headers=parent).status_code == 204
            futures = [pool.submit(read) for _ in range(4)] + [pool.submit(delete)]
            for future in futures:
                future.result(timeout=30)


@pytest.mark.parametrize("when", ["before-open", "after-open"])
def test_file_removed_at_open_boundary_is_404_or_complete_response(client, parent, monkeypatch, when):
    own = post(client, parent)
    photo = backend.feed.file(backend.users.get_user(seed.PARENT), UUID(own["photos"][0]["id"]))
    path = media.path(photo["storage_path"])
    original = Path.open
    def remove_at_open(self, *args, **kwargs):
        if self == path and when == "before-open":
            self.unlink()
        handle = original(self, *args, **kwargs)
        if self == path and when == "after-open":
            self.unlink()
        return handle
    monkeypatch.setattr(Path, "open", remove_at_open)
    response = client.get(own["photos"][0]["file_url"], headers=parent)
    if when == "before-open":
        err(response, 404, "NOT_FOUND")
    else:
        assert response.status_code == 200 and response.content == seed.feed_png()


def test_failed_delete_audit_preserves_post_photo_and_file(client, parent, monkeypatch, feed_backend):
    own = post(client, parent)
    original = backend.feed.record
    def fail_delete(*args, **kwargs):
        if "feed_post_deleted" in args:
            raise RuntimeError("[TEST] 이력 기록 실패")
        return original(*args, **kwargs)
    monkeypatch.setattr(backend.feed, "record", fail_delete)
    err(client.delete(f"{BASE}/posts/{own['id']}", headers=parent), 500, "INTERNAL_ERROR")
    assert client.get(f"{BASE}/posts/{own['id']}", headers=parent).json()["post"] == own
    assert client.get(own["photos"][0]["file_url"], headers=parent).content == seed.feed_png()
    assert not any(e["action"] == "feed_post_deleted" for e in audit(feed_backend))


@pytest.mark.parametrize("photo_count", [1, 2])
def test_disk_delete_failure_leaves_only_orphan_file_after_commit(
        client, parent, monkeypatch, caplog, feed_backend, photo_count):
    own = post(client, parent, tags=[[]] * photo_count)
    photos = [backend.feed.file(backend.users.get_user(seed.PARENT), UUID(p["id"])) for p in own["photos"]]
    paths = [media.path(p["storage_path"]) for p in photos]
    original = media.remove
    def fail_remove(name):
        if name == photos[0]["storage_path"]:
            raise OSError(f"[TEST] 지우기 실패 {paths[0]} token=test-secret")
        return original(name)
    monkeypatch.setattr(media, "remove", fail_remove)
    with caplog.at_level("WARNING", logger=backend.feed.__name__):
        response = client.delete(f"{BASE}/posts/{own['id']}", headers=parent)
    assert response.status_code == 204 and response.content == b""
    warnings = [r for r in caplog.records if r.name == backend.feed.__name__]
    assert [r.getMessage() for r in warnings] == [f"feed_photo_delete_failed photo_id={photos[0]['id']}"]
    assert warnings[0].levelname == "WARNING" and warnings[0].exc_info is None
    assert paths[0].is_file() and all(not p.exists() for p in paths[1:])
    err(client.get(f"{BASE}/posts/{own['id']}", headers=parent), 404, "NOT_FOUND")
    for photo in own["photos"]:
        err(client.get(photo["file_url"], headers=parent), 404, "NOT_FOUND")
    assert own["id"] not in {p["id"] for p in client.get(CLASS + "/posts", headers=parent).json()["items"]}
    album_ids = {p["id"] for p in client.get(CLASS + "/albums", headers=parent).json()["items"]}
    assert not album_ids.intersection(p["id"] for p in own["photos"])
    deleted = [e for e in audit(feed_backend) if e["action"] == "feed_post_deleted"]
    assert len(deleted) == 1 and deleted[0]["detail"]["post_id"] == own["id"]


def test_author_can_delete_after_losing_class_access(client, parent, feed_backend):
    own = post(client, parent)
    photo = backend.feed.file(backend.users.get_user(seed.PARENT), UUID(own["photos"][0]["id"]))
    path = media.path(photo["storage_path"])
    unlink(feed_backend, seed.CHILD, seed.PARENT)
    err(client.get(CLASS + "/posts", headers=parent), 403, "FORBIDDEN")
    assert client.delete(f"{BASE}/posts/{own['id']}", headers=parent).status_code == 204
    assert not path.exists()


def test_org_lane_closes_for_guardian_without_linked_child(client, parent, teacher, feed_backend):
    own = post(client, teacher, root=ORG)
    assert client.get(ORG + "/posts", headers=parent).status_code == 200
    unlink(feed_backend, seed.CHILD, seed.PARENT)  # parent01은 하늘이 하나만 연결돼 있었어요.
    headers = {**parent, "X-Request-ID": "t54-unlinked"}
    before = len(audit(feed_backend))
    for path in (ORG + "/posts", ORG + "/albums", f"{BASE}/posts/{own['id']}", own["photos"][0]["file_url"]):
        err(client.get(path, headers=headers), 403, "FORBIDDEN")
    err(create(client, headers, root=ORG), 403, "FORBIDDEN")
    denied = audit(feed_backend)[before:]
    assert len(denied) == 5 and all(e["action"] == "permission_denied" for e in denied)
    assert all(e["detail"]["trace_id"] == "t54-unlinked" for e in denied)


@pytest.mark.parametrize("actor", ["teacher", "parent_other"])
def test_unauthorized_invalid_upload_does_not_read_body(client, actor, request, monkeypatch, feed_backend):
    from starlette.requests import Request
    headers = request.getfixturevalue(actor)
    if actor == "parent_other":
        unlink(feed_backend, seed.demo_id("503"), seed.PARENT_OTHER)
    async def unread(self):
        pytest.fail("[TEST] 권한 없는 업로드 몸통을 읽었어요")
        yield b""
    monkeypatch.setattr(Request, "stream", unread)
    before = len(audit(feed_backend))
    err(create(client, headers, data=b"invalid"), 403, "FORBIDDEN")
    assert [e["action"] for e in audit(feed_backend)[before:]] == ["permission_denied"]


@pytest.mark.parametrize("root", [CLASS, ORG])
def test_large_content_length_is_413_without_reading_body(client, parent, monkeypatch, root):
    from starlette.requests import Request
    async def unread(self):
        pytest.fail("[TEST] Content-Length가 큰 몸통을 읽었어요")
        yield b""
    monkeypatch.setattr(Request, "stream", unread)
    err(client.post(root + "/posts", headers={**parent, "Content-Length": str(MAX_POST_BYTES + 1)},
                    content=b"unused"), 413, "VALIDATION_FAILED")


@pytest.mark.parametrize("length", [None, "1"])
def test_streamed_body_limit_closes_temporary_files(client, parent, monkeypatch, length):
    import asyncio
    import httpx
    import starlette.formparsers as parser
    from app.main import app
    opened = []
    original = parser.SpooledTemporaryFile
    def track(*args, **kwargs):
        handle = original(*args, **kwargs)
        opened.append(handle)
        return handle
    monkeypatch.setattr(parser, "SpooledTemporaryFile", track)
    sent = 0
    async def content():
        nonlocal sent
        yield (b'--test\r\nContent-Disposition: form-data; name="files"; filename="virtual.png"\r\n'
               b'Content-Type: image/png\r\n\r\n' + seed.feed_png())
        for _ in range(100):
            sent += 1
            yield b"x" * (1024 * 1024)
        pytest.fail("[TEST] 상한 뒤 몸통도 전부 읽었어요")
    async def send():
        headers = {**parent, "Content-Type": "multipart/form-data; boundary=test"}
        if length is not None:
            headers["Content-Length"] = length
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as http:
            return await http.post(CLASS + "/posts", headers=headers, content=content())
    err(asyncio.run(send()), 413, "VALIDATION_FAILED")
    assert sent == 51 and opened and all(handle.closed for handle in opened)


def test_mock_reset_removes_only_mock_files(client, parent, feed_backend):
    own = post(client, parent)
    photo = backend.feed.file(backend.users.get_user(seed.PARENT), UUID(own["photos"][0]["id"]))
    path = media.path(photo["storage_path"])
    marker = media.save(seed.feed_png(), media.inspect(seed.feed_png()))
    mock_orphan = media.save(seed.feed_png(), media.inspect(seed.feed_png()), mock=True)
    store.reset()
    assert media.path(marker).is_file() and not media.path(mock_orphan).exists()
    assert path.exists() is (feed_backend == "db")
    assert {p.name for p in media.path("mock").iterdir()} == {f"{p[0]}.png" for p in seed.FEED_PHOTOS}
