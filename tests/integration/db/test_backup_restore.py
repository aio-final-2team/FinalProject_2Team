"""백업 뒤에 지운 글·좁힌 사진 범위·지운 기억·퇴소가 덤프 복원으로 되살아나고, after_restore로 다시 닫히는지 본다."""

import json
import os
import subprocess
from dataclasses import replace

import pytest
from sqlalchemy import text

from app import backend
from app.core import media, users
from app.core.auth import issue_token
from app.maintenance import after_restore, withdraw_child
from app.mock import seed
from app.modules.feed import feed as db_feed

BASE = "/api/v1"
NOEUL, NOEUL_PHOTO = seed.demo_id("503"), seed.demo_id("f01")   # 백업 뒤에 퇴소하는 아이와 그 아이만 찍힌 사진


def psql(container, *args, **kwargs):
    return subprocess.run(["docker", "exec", "-i", container, *args], text=True, capture_output=True,
                          check=True, **kwargs).stdout


def state(engine, post_id, memory_id):
    with engine.connect() as connection:
        return {
            "post_deleted": connection.scalar(text("SELECT deleted_at IS NOT NULL FROM feed_posts WHERE id=:id"),
                                              {"id": post_id}),
            "scope": connection.scalar(text("SELECT photo_scope FROM children WHERE id=:id"), {"id": seed.CHILD}),
            "memory": connection.scalar(text("SELECT content FROM memories WHERE id=:id"), {"id": memory_id}),
            "noeul_guardians": connection.scalar(text("SELECT count(*) FROM child_guardians WHERE child_id=:id"),
                                                 {"id": NOEUL}),
            "noeul_photo": connection.scalar(text("SELECT count(*) FROM feed_photos WHERE id=:id"), {"id": NOEUL_PHOTO}),
            "events": connection.scalar(text("SELECT count(*) FROM events")),
        }


def test_dump_restore_revives_later_deletions_until_after_restore_applies_them(db_client, seeded_db, monkeypatch,
                                                                                 tmp_path):
    container = os.getenv("TEST_DB_CONTAINER")
    if not container:
        pytest.skip("tools/test_db.sh의 임시 컨테이너에서만 덤프·복원을 시험해요.")
    monkeypatch.setattr(media, "settings", replace(media.settings, media_dir=str(tmp_path)))
    monkeypatch.setattr(backend, "feed", db_feed)
    parent = {"Authorization": "Bearer " + issue_token(users.get_user(seed.PARENT))}
    teacher = {"Authorization": "Bearer " + issue_token(users.get_user(seed.TEACHER))}
    scope_path = f"{BASE}/children/{seed.CHILD}/photo-scope"
    response = db_client.post(f"{BASE}/classrooms/{seed.CLASS_STAR}/posts", headers=parent,
                              files=[("files", ("virtual.png", seed.feed_png(), "image/png"))],
                              data={"body": "[TEST] 지울 글", "child_ids": "[[]]"})
    post = response.json()["post"]
    assert db_client.patch(scope_path, headers=parent, json={"photo_scope": "org"}).status_code == 200
    with seeded_db.begin() as connection:
        memory = connection.scalar(text("""
            INSERT INTO memories(org_id,owner_id,kind,content) VALUES (:org,:owner,'tone','[TEST] 지울 기억') RETURNING id
        """), {"org": seed.ORG, "owner": seed.TEACHER})
        since = connection.scalar(text("SELECT now()"))
    dump = psql(container, "pg_dump", "-U", "yuchion", "-d", "yuchion_test")
    backed_up = state(seeded_db, post["id"], memory)

    # 백업 뒤에 글을 지우고, 공개 범위를 좁히고, 기억을 지우고, 노을이를 퇴소 처리한다.
    assert db_client.delete(f"{BASE}/posts/{post['id']}", headers=parent).status_code == 204
    assert db_client.patch(scope_path, headers=parent, json={"photo_scope": "family"}).status_code == 200
    assert db_client.delete(f"{BASE}/memories/{memory}", headers=teacher).status_code == 204
    withdraw_child.withdraw(NOEUL, apply=True)
    closed = state(seeded_db, post["id"], memory)
    with seeded_db.connect() as connection:
        # 실제 절차처럼 JSON 파일을 거친 값으로 적용한다.
        exported = json.loads(json.dumps(after_restore.export(connection, since), default=str))
    assert [p["id"] for p in exported["posts_deleted"]] == [post["id"]]
    assert [m["id"] for m in exported["memories_deleted"]] == [memory]
    assert [c["child_id"] for c in exported["withdrawn_children"]] == [str(NOEUL)]

    seeded_db.dispose()
    psql(container, "psql", "-v", "ON_ERROR_STOP=1", "-U", "yuchion", "-d", "yuchion_test",
         "-c", "DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    psql(container, "psql", "-v", "ON_ERROR_STOP=1", "-U", "yuchion", "-d", "yuchion_test", input=dump)
    seeded_db.dispose()
    # 복원하면 지운 글 본문, 넓은 범위, 지운 기억, 끝낸 보호자 연결이 다시 살아난다. 사진 파일은 없어 열면 404다.
    assert state(seeded_db, post["id"], memory) == backed_up
    assert db_client.get(f"{BASE}/posts/{post['id']}", headers=parent).json()["post"]["body"] == "[TEST] 지울 글"
    assert db_client.get(post["photos"][0]["file_url"], headers=parent).status_code == 404

    with seeded_db.begin() as connection:
        first = after_restore.apply(connection, exported)
    assert first == {"posts_deleted": 1, "posts_hidden": 0, "photo_scopes": 2, "withdrawn_children": 1,
                     "memories_deleted": 1, "events": 3}
    # 범위는 하늘이(org→family)와 노을이(class→family) 두 명이다. 이력은 백업 전에 있던 범위 변경을 빼고
    # 글 삭제·범위 좁힘·퇴소 세 줄을 되돌려 넣어 복원 전과 같아진다.
    assert state(seeded_db, post["id"], memory) == closed
    assert db_client.get(f"{BASE}/posts/{post['id']}", headers=parent).status_code == 404
    assert db_client.get(scope_path, headers=parent).json()["photo_scope"] == "family"
    with seeded_db.begin() as connection:
        again = after_restore.apply(connection, exported)
    assert set(again.values()) == {0} and state(seeded_db, post["id"], memory) == closed
