"""0018의 실제 제약·왕복과 최초 적재일 시드를 확인해요."""

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.schedule import KST
from app.mock import seed
from db.seeds.daily_records import seed_daily_records
from tests.integration.db.test_migrations import schema_dump


def test_daily_records_revision_round_trip(seeded_db, alembic_config):
    command.downgrade(alembic_config, "0016")
    before = schema_dump()
    command.upgrade(alembic_config, "0018")
    with seeded_db.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM daily_records")) == 0
    command.downgrade(alembic_config, "0016")
    assert schema_dump() == before
    command.upgrade(alembic_config, "head")


def test_daily_records_body_check_and_org_foreign_keys(seeded_db):
    with seeded_db.begin() as connection:
        values = {"org": seed.ORG, "class": seed.CLASS_STAR, "child": seed.CHILD, "author": seed.TEACHER, "body": "가"*500}
        sql = text("""INSERT INTO daily_records(org_id,classroom_id,child_id,note_date,body,author_id)
            VALUES (:org,:class,:child,CURRENT_DATE,:body,:author)""")
        connection.execute(sql, values)
        for changes, state in (({"body": "가"*501}, "23514"), ({"body": None}, "23502"),
                                ({"org": uuid4()}, "23503"), ({"class": uuid4()}, "23503"),
                                ({"child": uuid4()}, "23503"), ({"author": uuid4()}, "23503")):
            with pytest.raises(IntegrityError) as error, connection.begin_nested():
                connection.execute(sql, {**values, **changes})
            assert error.value.orig.sqlstate == state


def test_daily_records_demo_seed_dates_and_replay_preserve_deletion(seeded_db, monkeypatch):
    from db.seeds import daily_records
    with seeded_db.begin() as connection:
        seed_daily_records(connection)
        first = connection.execute(text("SELECT * FROM daily_records ORDER BY id")).mappings().all()
        assert len(first) == 80 and {r["note_date"] for r in first} == {
            datetime.now(KST).date(), datetime.now(KST).date()-timedelta(days=1)}
        assert all(r["classroom_id"] == seed.CLASS_STAR and r["author_id"] == seed.TEACHER for r in first)
        connection.execute(text("UPDATE daily_records SET deleted_at=now() WHERE id=:id"), {"id": first[0]["id"]})
        class Tomorrow(datetime):
            @classmethod
            def now(cls, tz):
                return datetime.now(tz)+timedelta(days=1)
        monkeypatch.setattr(daily_records, "datetime", Tomorrow)
        seed_daily_records(connection)
        after = connection.execute(text("SELECT * FROM daily_records ORDER BY id")).mappings().all()
        assert len(after) == 80 and after[0]["deleted_at"]
        assert [{**r, "deleted_at": None} for r in after] == first
