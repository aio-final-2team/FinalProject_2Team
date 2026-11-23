"""다른 기관 사용자·다른 반 보호자·연결이 끝난 보호자를 실제 HTTP의 조회·수정·파일 열람에서 막는지 본다."""

import json
from dataclasses import replace

import pytest
from sqlalchemy import text

from app import backend
from app.core import media, users
from app.core.auth import issue_token
from app.mock import seed
from app.modules.feed import feed as db_feed
from tests.integration.db.test_scope import records as records

BASE = "/api/v1"
CLASS = f"{BASE}/classrooms/{seed.CLASS_STAR}"
ORG = f"{BASE}/organizations/{seed.ORG}"


@pytest.fixture
def feed_files(db_client, monkeypatch, tmp_path):
    monkeypatch.setattr(media, "settings", replace(media.settings, media_dir=str(tmp_path)))
    monkeypatch.setattr(backend, "feed", db_feed)
    return db_client


def auth(user_id, trace="scope-case"):
    return {"Authorization": "Bearer " + issue_token(users.get_user(user_id)), "X-Request-ID": trace}


def photo_post(client, user_id, root, tags):
    files = [("files", ("virtual.png", seed.feed_png(), "image/png")) for _ in tags]
    response = client.post(root + "/posts", headers=auth(user_id), files=files,
                           data={"body": "[TEST] 가상 피드", "child_ids": json.dumps([[str(c) for c in t] for t in tags])})
    assert response.status_code == 201, response.text
    return response.json()["post"]


def denials(engine, trace):
    with engine.connect() as connection:
        return connection.execute(text("""
            SELECT org_id, actor_id FROM events WHERE action='permission_denied' AND detail->>'trace_id'=:trace
        """), {"trace": trace}).all()


def unlink(engine, child_id, user_id):
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM child_guardians WHERE child_id=:child AND user_id=:user"),
                           {"child": child_id, "user": user_id})


def ask(client, user_id, child_id, trace):
    return client.post(BASE + "/requests", headers=auth(user_id, trace), json={
        "client_request_id": f"[TEST] {trace}", "type": "inquiry", "body": "[TEST] 문의", "child_id": str(child_id)})


def test_other_org_user_gets_404_for_document_and_feed_files_with_denial(feed_files, records, seeded_db):
    client = feed_files
    own = photo_post(client, seed.PARENT, CLASS, [[]])
    shared = photo_post(client, seed.TEACHER, ORG, [[]])
    calls = [(records["teacher"], f"{BASE}/documents/{seed.MENU}"), (records["teacher"], shared["photos"][0]["file_url"]),
             (records["parent"], own["photos"][0]["file_url"]), (records["parent"], f"{BASE}/posts/{own['id']}")]
    # 정상: 같은 기관의 담임·작성자는 같은 경로를 연다.
    for owner, (_, path) in zip((seed.TEACHER, seed.TEACHER, seed.PARENT, seed.PARENT), calls, strict=True):
        assert client.get(path, headers=auth(owner)).status_code == 200, path
    for user_id, path in calls:
        response = client.get(path, headers=auth(user_id, "other-org"))
        assert response.status_code == 404 and response.json()["error"]["code"] == "NOT_FOUND", path
    # 거부 이력은 부른 사람의 기관에 남고, 이 원의 이력에는 섞이지 않는다.
    assert sorted(denials(seeded_db, "other-org")) == sorted((records["org"], u) for u, _ in calls)


def test_other_class_guardian_is_blocked_on_read_update_and_file(feed_files, records, seeded_db):
    client = feed_files
    unlink(seeded_db, seed.demo_id("503"), seed.PARENT_OTHER)  # 이제 햇님반 바다의 보호자이기만 하다
    class_photo = photo_post(client, seed.PARENT, CLASS, [[]])["photos"][0]
    org_photo = photo_post(client, seed.PARENT, ORG, [[seed.CHILD]])["photos"][0]
    me = seed.PARENT_OTHER
    # 정상: 그 아이 보호자는 같은 요청·인계자 목록·반 칸 사진을 연다.
    for path in (f"{BASE}/requests/{records['local_request']}", f"{BASE}/children/{seed.CHILD}/pickup-guardians",
                 class_photo["file_url"]):
        assert client.get(path, headers=auth(seed.PARENT)).status_code == 200, path
    for path in (f"{BASE}/requests/{records['local_request']}", f"{BASE}/children/{seed.CHILD}/pickup-guardians"):
        assert client.get(path, headers=auth(me, "other-class")).status_code == 404
    assert ask(client, me, seed.CHILD, "other-class").status_code == 404
    response = client.patch(f"{BASE}/children/{seed.CHILD}/photo-scope", headers=auth(me, "other-class"),
                            json={"photo_scope": "org"})
    assert response.status_code == 403
    assert client.get(class_photo["file_url"], headers=auth(me, "other-class")).status_code == 403
    assert len(denials(seeded_db, "other-class")) == 5
    # 아이 범위(family)로 가려진 원 칸 사진과 남의 아이 알림장은 거부가 아니라 걸러서 보이지 않는다.
    assert client.get(org_photo["file_url"], headers=auth(me, "hidden")).status_code == 404
    with seeded_db.connect() as connection:
        note_date = connection.scalar(text("SELECT note_date FROM daily_notes WHERE id=:id"), {"id": records["local_note"]})
    response = client.get(BASE + "/daily-notes", headers=auth(me, "hidden"),
                          params={"date": note_date.isoformat(), "classroom_id": str(seed.CLASS_STAR)})
    assert response.status_code == 200 and response.json()["total"] == 0
    assert denials(seeded_db, "hidden") == []


def test_unlinked_guardian_loses_child_notes_requests_and_all_feed_photos(feed_files, records, seeded_db):
    client = feed_files
    class_photo = photo_post(client, seed.PARENT_OTHER, CLASS, [[]])["photos"][0]
    tagged = photo_post(client, seed.PARENT_OTHER, ORG, [[seed.CHILD]])["photos"][0]
    untagged = photo_post(client, seed.PARENT_OTHER, ORG, [[]])["photos"][0]
    with seeded_db.connect() as connection:
        note_date = connection.scalar(text("SELECT note_date FROM daily_notes WHERE id=:id"), {"id": records["local_note"]})

    def sent_notes():
        response = client.get(BASE + "/daily-notes", headers=auth(seed.PARENT), params={"date": note_date.isoformat()})
        assert response.status_code == 200
        return response.json()["total"]

    assert sent_notes() == 1
    assert all(client.get(p["file_url"], headers=auth(seed.PARENT)).status_code == 200
               for p in (class_photo, tagged, untagged))
    unlink(seeded_db, seed.CHILD, seed.PARENT)  # parent01에게 남은 아이가 없다
    assert sent_notes() == 0
    assert ask(client, seed.PARENT, seed.CHILD, "unlinked").status_code == 404
    # 원 칸도 지금 연결된 아이가 있는 보호자만 연다. 아이와 무관한 원 칸 사진도 막힌다.
    for path in (class_photo["file_url"], tagged["file_url"], untagged["file_url"], ORG + "/posts"):
        assert client.get(path, headers=auth(seed.PARENT, "unlinked")).status_code == 403, path
    assert len(denials(seeded_db, "unlinked")) == 5
    # 추가 조치로 계정까지 끄면 인증 단계에서 401이 된다.
    headers = auth(seed.PARENT)
    with seeded_db.begin() as connection:
        connection.execute(text("UPDATE users SET is_active=false WHERE id=:id"), {"id": seed.PARENT})
    assert client.get(ORG + "/posts", headers=headers).status_code == 401
