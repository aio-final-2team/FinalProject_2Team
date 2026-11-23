"""백업 뒤에 지운 글·좁힌 사진 범위가 덤프 복원으로 되살아나는지, 이력을 다시 적용하면 닫히는지 본다."""

import os
import subprocess
from dataclasses import replace

import pytest
from sqlalchemy import text

from app import backend
from app.core import media, users
from app.core.auth import issue_token
from app.mock import seed
from app.modules.feed import feed as db_feed

BASE = "/api/v1"


def psql(container, *args, **kwargs):
    return subprocess.run(["docker", "exec", "-i", container, *args], text=True, capture_output=True,
                          check=True, **kwargs).stdout


def test_dump_restore_revives_deleted_post_until_later_events_are_reapplied(db_client, seeded_db, monkeypatch, tmp_path):
    container = os.getenv("TEST_DB_CONTAINER")
    if not container:
        pytest.skip("tools/test_db.sh의 임시 컨테이너에서만 덤프·복원을 시험해요.")
    monkeypatch.setattr(media, "settings", replace(media.settings, media_dir=str(tmp_path)))
    monkeypatch.setattr(backend, "feed", db_feed)
    parent = {"Authorization": "Bearer " + issue_token(users.get_user(seed.PARENT))}
    scope_path = f"{BASE}/children/{seed.CHILD}/photo-scope"
    response = db_client.post(f"{BASE}/classrooms/{seed.CLASS_STAR}/posts", headers=parent,
                              files=[("files", ("virtual.png", seed.feed_png(), "image/png"))],
                              data={"body": "[TEST] 지울 글", "child_ids": "[[]]"})
    post = response.json()["post"]
    assert db_client.patch(scope_path, headers=parent, json={"photo_scope": "org"}).status_code == 200
    with seeded_db.connect() as connection:
        last_event = connection.scalar(text("SELECT max(id) FROM events"))
    dump = psql(container, "pg_dump", "-U", "yuchion", "-d", "yuchion_test")
    # 백업 뒤에 글을 지우고 공개 범위를 좁힌다. 사진 파일은 DB 덤프 밖이라 바로 사라진다.
    assert db_client.delete(f"{BASE}/posts/{post['id']}", headers=parent).status_code == 204
    assert db_client.patch(scope_path, headers=parent, json={"photo_scope": "family"}).status_code == 200
    with seeded_db.connect() as connection:
        later = connection.execute(text("""
            SELECT action, detail FROM events WHERE id>:id AND action IN ('feed_post_deleted','photo_scope_changed')
            ORDER BY id
        """), {"id": last_event}).mappings().all()
    seeded_db.dispose()
    psql(container, "psql", "-v", "ON_ERROR_STOP=1", "-U", "yuchion", "-d", "yuchion_test",
         "-c", "DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    psql(container, "psql", "-v", "ON_ERROR_STOP=1", "-U", "yuchion", "-d", "yuchion_test", input=dump)
    seeded_db.dispose()
    # 복원하면 지운 글 본문이 다시 보이고, 넓은 범위로 돌아간다. 파일은 없어 열면 404다.
    assert db_client.get(f"{BASE}/posts/{post['id']}", headers=parent).json()["post"]["body"] == "[TEST] 지울 글"
    assert db_client.get(post["photos"][0]["file_url"], headers=parent).status_code == 404
    assert db_client.get(scope_path, headers=parent).json()["photo_scope"] == "org"
    # 복원 전 DB에서 옮겨 둔 백업 뒤 이력을 다시 적용하면 복원 전 상태로 닫힌다.
    with seeded_db.begin() as connection:
        for event in later:
            if event["action"] == "feed_post_deleted":
                connection.execute(text("UPDATE feed_posts SET deleted_at=now() WHERE id=:id"),
                                   {"id": event["detail"]["post_id"]})
            else:
                connection.execute(text("UPDATE children SET photo_scope=:after WHERE id=:id"),
                                   {"after": event["detail"]["after"], "id": event["detail"]["child_id"]})
    assert [e["action"] for e in later] == ["feed_post_deleted", "photo_scope_changed"]
    assert db_client.get(f"{BASE}/posts/{post['id']}", headers=parent).status_code == 404
    assert db_client.get(scope_path, headers=parent).json()["photo_scope"] == "family"
