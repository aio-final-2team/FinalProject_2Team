"""[TEST] 0012 왕복과 기관 짝 FK·상태 CHECK를 검사해요."""

from alembic import command
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.mock import seed
from db.seeds.demo import seed_video_consult
from tests.integration.db.test_migrations import HEAD_CATALOG, catalog, schema_dump


def test_voice_revision_roundtrip_and_constraints(seeded_db, alembic_config):
    command.downgrade(alembic_config, "0011")
    with seeded_db.begin() as c:
        seed_video_consult(c)
        booking = dict(c.execute(text("SELECT * FROM consultation_bookings WHERE id=:id"),
                                 {"id": seed.VIDEO_BOOKING}).mappings().one())
    previous = schema_dump()
    command.upgrade(alembic_config, "head")
    with seeded_db.begin() as c:
        params = {"org": seed.ORG, "booking": seed.VIDEO_BOOKING, "req": seed.VIDEO_REQUEST}
        statement = "INSERT INTO consultation_voice_analyses(org_id,booking_id,request_id,sha256) VALUES (:org,:booking,:req,repeat('a',64))"
        c.execute(text(statement), params)
        for column, value in (("org", seed.demo_id("9999")), ("booking", seed.demo_id("9999"))):
            with pytest.raises(IntegrityError), c.begin_nested():
                c.execute(text(statement), {**params, column: value})
        with pytest.raises(IntegrityError), c.begin_nested():
            c.execute(text("UPDATE consultation_voice_analyses SET status='retry'"))
        for action in ("voice_analysis_requested", "voice_analysis_completed"):
            c.execute(text("INSERT INTO events(org_id,request_id,actor_type,action) VALUES (:org,:req,'system',:action)"),
                      {**params, "action": action})
        assert dict(catalog(c)) == HEAD_CATALOG
    command.downgrade(alembic_config, "0011")
    assert schema_dump() == previous
    with seeded_db.connect() as c:
        assert dict(c.execute(text("SELECT * FROM consultation_bookings WHERE id=:id"),
                              {"id": seed.VIDEO_BOOKING}).mappings().one()) == booking
        assert c.scalar(text("SELECT count(*) FROM events WHERE action LIKE 'voice_analysis_%'")) == 0
    command.upgrade(alembic_config, "head")
