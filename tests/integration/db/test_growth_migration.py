"""[TEST] 0014 왕복·사진 CASCADE·제약과 기존 피드 보존을 확인해요."""

from alembic import command
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.mock import seed
from tests.integration.db.test_migrations import HEAD_CATALOG, catalog, schema_dump


def test_growth_revision_roundtrip_and_photo_cascade(seeded_db, alembic_config):
    command.downgrade(alembic_config, '0013')
    previous = schema_dump()
    command.upgrade(alembic_config, 'head')
    with seeded_db.begin() as c:
        assert dict(catalog(c)) == HEAD_CATALOG
        vid = c.scalar(text("INSERT INTO growth_videos(org_id,child_id,requested_by,storage_path,photo_count) "
                            "VALUES (:org,:child,:user,'videos/test.mp4',3) RETURNING id"),
                       dict(org=seed.ORG, child=seed.CHILD, user=seed.PARENT))
        with pytest.raises(IntegrityError), c.begin_nested():
            c.execute(text("INSERT INTO growth_videos(org_id,child_id,requested_by,storage_path,photo_count) "
                           "VALUES (:org,:child,:user,'videos/duplicate.mp4',3)"),
                      dict(org=seed.ORG, child=seed.CHILD, user=seed.PARENT))
        c.execute(text("UPDATE growth_videos SET status='succeeded' WHERE id=:id"), {'id': vid})
        photo_id = seed.FEED_PHOTOS[0][0]
        c.execute(text('INSERT INTO growth_video_photos VALUES (:id,:org,:photo,0)'),
                  dict(id=vid, org=seed.ORG, photo=photo_id))
        for change in ("status='retry'", 'photo_count=2', 'duration_seconds=61', 'size_bytes=-1', "sha256='bad'"):
            with pytest.raises(IntegrityError), c.begin_nested():
                c.execute(text('UPDATE growth_videos SET '+change))
        c.execute(text('DELETE FROM feed_photo_children WHERE photo_id=:id'), {'id': photo_id})
        c.execute(text('DELETE FROM feed_photos WHERE id=:id'), {'id': photo_id})
        assert c.scalar(text('SELECT count(*) FROM growth_video_photos')) == 0
        for action in ('growth_video_requested', 'growth_video_completed', 'growth_video_deleted'):
            c.execute(text("INSERT INTO events(org_id,actor_type,action) VALUES (:org,'system',:action)"),
                      dict(org=seed.ORG, action=action))
        count = c.scalar(text('SELECT count(*) FROM feed_posts'))
    command.downgrade(alembic_config, '0013')
    assert schema_dump() == previous
    with seeded_db.connect() as c:
        assert c.scalar(text('SELECT count(*) FROM feed_posts')) == count
        assert c.scalar(text("SELECT count(*) FROM events WHERE action LIKE 'growth_video_%'")) == 0
    command.upgrade(alembic_config, 'head')

    snapshot = schema_dump()
    command.downgrade(alembic_config, '0014')
    with seeded_db.connect() as c:
        assert c.scalar(text("SELECT to_regclass('growth_videos_pending_child_idx')")) is None
        assert dict(catalog(c)) == HEAD_CATALOG
    command.upgrade(alembic_config, 'head')
    assert schema_dump() == snapshot
