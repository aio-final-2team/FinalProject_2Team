"""0019의 기존 데이터 보존·기관 FK·되돌리기를 실제 PG로 확인해요."""

from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.mock import seed
from tests.integration.db.test_migrations import schema_dump


def test_note_replies_0019_round_trip_defaults_foreign_key_and_retention(seeded_db, alembic_config):
    command.downgrade(alembic_config, "0016")
    previous = schema_dump()
    with seeded_db.connect() as connection:
        requests_before = connection.execute(text("SELECT * FROM requests ORDER BY id")).mappings().all()
    command.upgrade(alembic_config, "head")
    with seeded_db.begin() as connection:
        assert connection.execute(text("SELECT * FROM requests ORDER BY id")).mappings().all() == [
            {**r, "source_note_id": None, "intent": None} for r in requests_before]
        entry = connection.scalar(text("""INSERT INTO daily_note_inputs(org_id,classroom_id,author_id,note_date)
            VALUES (:org,:class,:user,CURRENT_DATE) RETURNING id"""),
            {"org": seed.ORG, "class": seed.CLASS_STAR, "user": seed.TEACHER})
        note = connection.execute(text("""INSERT INTO daily_notes(org_id,input_id,child_id,note_date)
            VALUES (:org,:input,:child,CURRENT_DATE) RETURNING id,supplies_checked_at"""),
            {"org": seed.ORG, "input": entry, "child": seed.CHILD}).mappings().one()
        assert note["supplies_checked_at"] is None
        connection.execute(text("UPDATE requests SET source_note_id=:note WHERE id=:id"),
                           {"note": note["id"], "id": seed.REQUEST_COUGH})
        connection.execute(text("UPDATE daily_notes SET supplies_checked_at=now() WHERE id=:id"), {"id": note["id"]})
        foreign = uuid4()
        foreign_user = uuid4()
        connection.execute(text("INSERT INTO organizations(id,name) VALUES (:id,'[TEST] 다른 원')"), {"id": foreign})
        connection.execute(text("""INSERT INTO users(id,org_id,role,login_id,display_name,password_hash)
            VALUES (:id,:org,'parent','test-foreign','[TEST] 보호자','test')"""), {"id": foreign_user, "org": foreign})
        for note_id, org in ((uuid4(), seed.ORG), (note["id"], foreign)):
            with pytest.raises(IntegrityError) as error, connection.begin_nested():
                connection.execute(text("""INSERT INTO requests(org_id,requester_id,client_request_id,type,body,source_note_id)
                    VALUES (:org,:user,:key,'inquiry','[TEST] 답장',:note)"""),
                    {"org": org, "user": seed.PARENT if org == seed.ORG else foreign_user, "key": str(uuid4()), "note": note_id})
            assert error.value.orig.sqlstate == "23503"
            assert error.value.orig.diag.constraint_name == "requests_source_note_org_fkey"
        with pytest.raises(IntegrityError), connection.begin_nested():
            connection.execute(text("DELETE FROM daily_notes WHERE id=:id"), {"id": note["id"]})
    command.downgrade(alembic_config, "0016")
    assert schema_dump() == previous
    with seeded_db.connect() as connection:
        assert connection.execute(text("SELECT * FROM requests ORDER BY id")).mappings().all() == requests_before
    command.upgrade(alembic_config, "head")
    with seeded_db.connect() as connection:
        assert connection.scalar(text("SELECT source_note_id FROM requests WHERE id=:id"), {"id": seed.REQUEST_COUGH}) is None
        assert connection.scalar(text("SELECT supplies_checked_at FROM daily_notes WHERE id=:id"), {"id": note["id"]}) is None
