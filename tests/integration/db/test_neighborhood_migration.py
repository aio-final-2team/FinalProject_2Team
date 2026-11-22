"""[TEST] 0013 CHECK 확장·바로 앞 판 왕복·선택 시드의 동일성을 확인해요."""

from dataclasses import replace

from alembic import command
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core import config
from app.mock import seed, store
from db.seeds.demo import seed_demo
from tests.integration.db.test_migrations import HEAD_CATALOG, catalog, schema_dump


def test_neighborhood_revision_and_optional_seed(seeded_db, alembic_config, monkeypatch):
    monkeypatch.setattr(config, "settings", replace(config.settings, feature_neighborhood_feed=True))
    store.reset()
    command.downgrade(alembic_config, "0012")
    previous = schema_dump()
    with seeded_db.begin() as c:
        original = dict(c.execute(text("SELECT * FROM feed_posts WHERE id=:id"), {"id": seed.FEED_POSTS[0]["id"]}).mappings().one())
        seed_demo(c)  # 기능을 켜도 옛 CHECK에는 새 시드를 넣지 않아요.
        assert c.scalar(text("SELECT count(*) FROM organizations")) == 1
    command.upgrade(alembic_config, "head")
    with seeded_db.begin() as c:
        seed_demo(c)
        seed_demo(c)
        assert dict(catalog(c)) == HEAD_CATALOG
        assert c.scalar(text("SELECT count(*) FROM organizations")) == 3
        orgs = {r["id"]: dict(r) for r in c.execute(text("SELECT id,name,region FROM organizations")).mappings()}
        assert orgs == store.state().organizations
        for org in seed.NEIGHBORHOOD_ORGS:
            assert c.scalar(text("SELECT id FROM users WHERE login_id=:login"), {"login": org["login_id"]}) == org["parent_id"]
            assert c.scalar(text("SELECT user_id FROM child_guardians WHERE child_id=:id"), {"id": org["child_id"]}) == org["parent_id"]
        c.execute(text("UPDATE children SET photo_scope='neighborhood' WHERE id=:id"), {"id": seed.CHILD})
        c.execute(text("""INSERT INTO feed_posts(id,org_id,lane,author_id,body)
            VALUES (:id,:org,'neighborhood',:author,'[TEST] 동네')"""),
                  {"id": seed.demo_id("e10"), "org": seed.ORG, "author": seed.PARENT})
        for statement in ("UPDATE children SET photo_scope='public'", "UPDATE feed_posts SET lane='public'",
                          "UPDATE feed_posts SET classroom_id=NULL WHERE lane='class'",
                          "UPDATE feed_posts SET classroom_id='00000000-0000-4000-8000-000000000101' WHERE lane='neighborhood'"):
            with pytest.raises(IntegrityError), c.begin_nested():
                c.execute(text(statement))
        c.execute(text("UPDATE organizations SET region=NULL WHERE id=:id"), {"id": seed.ORG})
        seed_demo(c)
        assert c.scalar(text("SELECT region FROM organizations WHERE id=:id"), {"id": seed.ORG}) is None
        assert c.scalar(text("SELECT photo_scope FROM children WHERE id=:id"), {"id": seed.CHILD}) == "neighborhood"
    command.downgrade(alembic_config, "0012")
    assert schema_dump() == previous
    with seeded_db.connect() as c:
        assert dict(c.execute(text("SELECT * FROM feed_posts WHERE id=:id"), {"id": original["id"]}).mappings().one()) == original
        assert c.scalar(text("SELECT photo_scope FROM children WHERE id=:id"), {"id": seed.CHILD}) == "org"
        assert c.scalar(text("SELECT count(*) FROM feed_posts WHERE id=:id"), {"id": seed.demo_id("e10")}) == 0
    command.upgrade(alembic_config, "head")
