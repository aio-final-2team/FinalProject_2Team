"""고아 사진 정리와 퇴소 관리 작업이 고를 것만 고르고, 시키기 전에는 아무것도 바꾸지 않는지 본다."""

import os
from dataclasses import replace

import pytest
from sqlalchemy import text

from app import backend
from app.core import media, users
from app.core.auth import issue_token
from app.maintenance import media_sweep, withdraw_child
from app.mock import seed
from app.modules.feed import feed as db_feed

BASE = "/api/v1"
SOLO, SHARED = seed.demo_id("f02"), seed.demo_id("f04")   # 하늘이만 / 하늘이와 노을이가 함께 찍힌 시드 사진


@pytest.fixture
def media_root(monkeypatch, tmp_path):
    root = tmp_path / "media"
    monkeypatch.setattr(media, "settings", replace(media.settings, media_dir=str(root)))
    monkeypatch.setattr(backend, "feed", db_feed)
    return root


def auth(user_id):
    return {"Authorization": "Bearer " + issue_token(users.get_user(user_id))}


def old(path, data=b"x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    os.utime(path, (1, 1))
    return path


def snapshot(engine):
    with engine.connect() as connection:
        return [connection.execute(text(sql)).all() for sql in (
            "SELECT child_id,user_id FROM child_guardians ORDER BY 1,2",
            "SELECT id,photo_scope FROM children ORDER BY id",
            "SELECT photo_id,child_id FROM feed_photo_children ORDER BY 1,2",
            "SELECT id,content,deleted_at FROM memories ORDER BY id",
            "SELECT count(*) FROM events",
        )]


def test_sweep_lists_only_orphans_and_deletes_them_only_with_apply(media_root, seeded_db, tmp_path):
    with seeded_db.begin() as connection:
        connection.execute(text("UPDATE feed_posts SET deleted_at=now() WHERE id=:id"), {"id": seed.demo_id("e04")})
    for path in media_root.glob("*.png"):
        os.utime(path, (1, 1))
    stray = old(media_root / "stray.png")
    outside = old(tmp_path / "outside.png")
    (media_root / "link.png").symlink_to(outside)
    old(media_root / "mock" / "seed.png")
    (media_root / "fresh.png").write_bytes(b"uploading")
    expected = [f"{seed.demo_id('f05')}.png", "stray.png"]   # 지운 글의 사진과 행이 없는 파일

    assert media_sweep.sweep() == expected
    assert stray.exists() and (media_root / expected[0]).exists()
    assert media_sweep.sweep(apply=True) == expected
    assert not stray.exists() and not (media_root / expected[0]).exists()
    remaining = sorted(p.name for p in media_root.iterdir())
    assert remaining == sorted([f"{seed.demo_id(f'f0{n}')}.png" for n in range(1, 5)] + ["fresh.png", "link.png", "mock"])
    assert outside.exists() and media_sweep.sweep(apply=True) == []


@pytest.mark.parametrize("name", ["../outside.png", "/etc/hostname", "mock/../../outside.png", "."])
def test_paths_outside_media_dir_are_refused(media_root, tmp_path, name):
    outside = old(tmp_path / "outside.png")
    with pytest.raises(ValueError):
        media_sweep.safe_path(name)
    withdraw_child.remove_files([name])
    assert outside.exists()


def test_withdraw_dry_run_changes_nothing_then_apply_follows_four_steps(media_root, db_client, seeded_db):
    with seeded_db.begin() as connection:
        card = connection.scalar(text("""
            INSERT INTO cards(org_id,request_id,kind,status) VALUES (:org,:req,'reply_draft','done') RETURNING id
        """), {"org": seed.ORG, "req": seed.REQUEST_COUGH})
        memory = connection.scalar(text("""
            INSERT INTO memories(org_id,owner_id,kind,content,structured,source_card_id)
            VALUES (:org,:owner,'preference','[TEST] 하늘이 하원 메모','{"weekday": 3}',:card) RETURNING id
        """), {"org": seed.ORG, "owner": seed.TEACHER, "card": card})
        other = connection.scalar(text("""
            INSERT INTO memories(org_id,owner_id,kind,content) VALUES (:org,:owner,'tone','[TEST] 남는 기억') RETURNING id
        """), {"org": seed.ORG, "owner": seed.TEACHER})
    parent, class_feed = auth(seed.PARENT), f"{BASE}/classrooms/{seed.CLASS_STAR}/posts"
    assert db_client.patch(f"{BASE}/children/{seed.CHILD}/photo-scope", headers=parent,
                           json={"photo_scope": "org"}).status_code == 200
    solo_file = media.path(f"{SOLO}.png")
    before = snapshot(seeded_db)

    todo = withdraw_child.withdraw(seed.CHILD)
    assert (todo["guardian_ids"], todo["photo_scope"], todo["memory_ids"]) == ([seed.PARENT], "org", [memory])
    assert ([p["id"] for p in todo["solo_photos"]], todo["shared_photo_ids"]) == ([SOLO], [SHARED])
    assert snapshot(seeded_db) == before and solo_file.exists()
    assert db_client.get(class_feed, headers=parent).status_code == 200

    withdraw_child.withdraw(seed.CHILD, apply=True)
    with seeded_db.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM child_guardians WHERE child_id=:c"), {"c": seed.CHILD}) == 0
        assert connection.scalar(text("SELECT photo_scope FROM children WHERE id=:c"), {"c": seed.CHILD}) == "family"
        assert connection.scalar(text("SELECT count(*) FROM feed_photos WHERE id=:p"), {"p": SOLO}) == 0
        assert set(connection.scalars(text("SELECT child_id FROM feed_photo_children WHERE photo_id=:p"),
                                      {"p": SHARED})) == {seed.CHILD, seed.demo_id("503")}
        memories = dict(connection.execute(text("SELECT id,content FROM memories WHERE id IN (:a,:b)"),
                                           {"a": memory, "b": other}).all())
        assert memories == {memory: "", other: "[TEST] 남는 기억"}
        event = connection.execute(text("SELECT actor_type,detail FROM events WHERE action='photo_scope_changed' "
                                        "ORDER BY id DESC LIMIT 1")).one()
    assert event.actor_type == "system" and event.detail["withdrawn"] is True
    assert (event.detail["before"], event.detail["photo_ids"]) == ("org", [str(SOLO)])
    assert not solo_file.exists() and media.path(f"{SHARED}.png").exists()
    # 남은 아이가 없는 보호자는 반 칸·원 칸 모두 403이다. 함께 찍힌 사진은 노을이 보호자에게도 가려진다.
    assert db_client.get(class_feed, headers=parent).status_code == 403
    assert db_client.get(f"{BASE}/organizations/{seed.ORG}/posts", headers=parent).status_code == 403
    shared_post = db_client.get(f"{BASE}/posts/{seed.demo_id('e03')}", headers=auth(seed.PARENT_OTHER)).json()["post"]
    assert [p["id"] for p in shared_post["photos"]] == [str(seed.demo_id("f03"))]

    after = snapshot(seeded_db)
    assert not withdraw_child.pending(withdraw_child.withdraw(seed.CHILD, apply=True))
    assert snapshot(seeded_db) == after
