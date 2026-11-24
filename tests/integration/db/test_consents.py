"""[제안] 0016은 표만 채비하고 시드는 최초 기록을 유지해요."""

from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core import users
from app.mock import seed
from app.modules.feed.feed import record
from db.seeds.demo import seed_demo
from tests.integration.db.test_migrations import schema_dump


def test_0016_round_trip_constraints_seed_idempotency_and_event_retention(seeded_db, alembic_config):
    command.downgrade(alembic_config, "0015")
    old_dump = schema_dump()
    command.upgrade(alembic_config, "head")
    with seeded_db.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM user_consents")) == 0
    command.downgrade(alembic_config, "0015")
    assert schema_dump() == old_dump
    command.upgrade(alembic_config, "head")
    with seeded_db.begin() as connection:
        seed_demo(connection)
        first = connection.execute(text("SELECT * FROM user_consents ORDER BY id")).mappings().all()
        assert len(first) == sum(6 if u["role"] == "parent" else 3 for u in seed.USERS)
        seed_demo(connection)
        assert connection.execute(text("SELECT * FROM user_consents ORDER BY id")).mappings().all() == first
        foreign = uuid4()
        connection.execute(text("INSERT INTO organizations(id,name) VALUES (:id,'[TEST] 다른 원')"), {"id": foreign})
        for org, item, state in ((seed.ORG, "terms", "23505"), (seed.ORG, "unknown", "23514"),
                                  (foreign, "terms", "23503")):
            with pytest.raises(IntegrityError) as error, connection.begin_nested():
                connection.execute(text("""
                    INSERT INTO user_consents(org_id,user_id,item,terms_version)
                    VALUES (:org,:user,:item,:version)
                """), {"org": org, "user": seed.PARENT, "item": item, "version": first[0]["terms_version"]})
            assert error.value.orig.sqlstate == state
        record(connection, users.get_user(seed.PARENT), "consent_agreed", terms_version=first[0]["terms_version"])
        event = dict(connection.execute(text("SELECT * FROM events WHERE action='consent_agreed'")).mappings().one())
    command.downgrade(alembic_config, "0015")
    with seeded_db.connect() as connection:
        assert connection.scalar(text("SELECT to_regclass('public.user_consents')")) is None
        assert dict(connection.execute(text("SELECT * FROM events WHERE id=:id"), {"id": event["id"]}).mappings().one()) == event
    command.upgrade(alembic_config, "head")
    with seeded_db.begin() as connection:
        assert connection.scalar(text("SELECT count(*) FROM user_consents")) == 0
        connection.execute(text("DELETE FROM events WHERE id=:id"), {"id": event["id"]})
