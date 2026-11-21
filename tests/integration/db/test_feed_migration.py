"""0010의 기존 아이 기본값·기관 FK·CHECK·바로 앞 판 왕복을 검사해요."""

import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.mock import seed
from db.seeds.demo import seed_demo
from tests.integration.db.test_migrations import HEAD_CATALOG, catalog, schema_dump


def test_feed_revision_backfill_constraints_and_previous_revision_roundtrip(db_engine, alembic_config):
    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "0009")
    with db_engine.begin() as connection:
        seed_demo(connection)
        original = dict(connection.execute(text("SELECT * FROM children WHERE id=:id"),
                                           {"id": seed.CHILD}).mappings().one())
    previous = schema_dump()
    command.upgrade(alembic_config, "head")
    with db_engine.begin() as connection:
        assert dict(catalog(connection)) == HEAD_CATALOG
        assert dict(connection.execute(text("SELECT * FROM children WHERE id=:id"),
                                       {"id": seed.CHILD}).mappings().one()) == {**original, "photo_scope": "family"}
        for invalid in (None, "public", ""):
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(text("UPDATE children SET photo_scope=:scope WHERE id=:id"),
                                   {"id": seed.CHILD, "scope": invalid})
        seed_demo(connection)
        # 재시드는 가족이 바꾼 공개 범위·삭제 상태를 되돌리지 않아요.
        connection.execute(text("UPDATE children SET photo_scope='org' WHERE id=:id"), {"id": seed.CHILD})
        connection.execute(text("UPDATE feed_posts SET deleted_at=now() WHERE id=:id"), {"id": seed.demo_id("e01")})
        seed_demo(connection)
        assert connection.scalar(text("SELECT photo_scope FROM children WHERE id=:id"), {"id": seed.CHILD}) == "org"
        assert connection.scalar(text("SELECT deleted_at FROM feed_posts WHERE id=:id"), {"id": seed.demo_id("e01")})
        other = connection.scalar(text("INSERT INTO organizations(name) VALUES ('[TEST] 다른 원') RETURNING id"))
        for statement, values in (
            ("UPDATE feed_posts SET org_id=:org WHERE id=:id", {"org": other, "id": seed.demo_id("e02")}),
            ("UPDATE feed_photos SET org_id=:org WHERE id=:id", {"org": other, "id": seed.demo_id("f01")}),
            ("UPDATE feed_photo_children SET org_id=:org WHERE photo_id=:id", {"org": other, "id": seed.demo_id("f01")}),
            ("UPDATE feed_posts SET lane='org' WHERE id=:id", {"id": seed.demo_id("e02")}),
            ("UPDATE feed_posts SET body='' WHERE id=:id", {"id": seed.demo_id("e02")}),
            ("UPDATE feed_photos SET size_bytes=5242881 WHERE id=:id", {"id": seed.demo_id("f01")}),
            ("UPDATE feed_photos SET media_type='image/svg+xml' WHERE id=:id", {"id": seed.demo_id("f01")}),
        ):
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(text(statement), values)
        connection.execute(text("""
            INSERT INTO events(org_id,actor_type,action) VALUES (:org,'system','photo_scope_changed')
        """), {"org": seed.ORG})
    command.downgrade(alembic_config, "0009")
    assert schema_dump() == previous
    with db_engine.connect() as connection:
        assert dict(connection.execute(text("SELECT * FROM children WHERE id=:id"),
                                       {"id": seed.CHILD}).mappings().one()) == original
        assert connection.scalar(text("SELECT count(*) FROM events WHERE action='photo_scope_changed'")) == 0
    command.upgrade(alembic_config, "head")
    with db_engine.connect() as connection:
        assert dict(catalog(connection)) == HEAD_CATALOG
