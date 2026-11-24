"""마이그레이션 head 카탈로그·설계 DDL 대조·up/down/up·시드·트랜잭션."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from alembic import command
from argon2 import PasswordHasher
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core import db
from app.core.schedule import KST
from app.mock import seed
from db.seeds.demo import seed_demo

ROOT = Path(__file__).resolve().parents[3]
HEAD_CATALOG = {"tables": 30, "views": 2, "triggers": 2, "foreign_keys": 64, "columns": 295}


def catalog(connection):
    # 확장 함수·Alembic 관리 표는 설계서의 표·컬럼 개수에서 뺀다.
    return connection.execute(text("""
        SELECT
          (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
           WHERE n.nspname='public' AND c.relkind='r' AND c.relname<>'alembic_version') AS tables,
          (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
           WHERE n.nspname='public' AND c.relkind='v') AS views,
          (SELECT count(*) FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
           JOIN pg_namespace n ON n.oid=c.relnamespace
           WHERE n.nspname='public' AND NOT t.tgisinternal) AS triggers,
          (SELECT count(*) FROM pg_constraint k JOIN pg_namespace n ON n.oid=k.connamespace
           WHERE n.nspname='public' AND k.contype='f') AS foreign_keys,
          (SELECT count(*) FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid
           JOIN pg_namespace n ON n.oid=c.relnamespace
           WHERE n.nspname='public' AND c.relkind='r' AND c.relname<>'alembic_version'
           AND a.attnum>0 AND NOT a.attisdropped) AS columns
    """)).mappings().one()


def schema_dump():
    container = os.getenv("TEST_DB_CONTAINER")
    if container:
        args = ["docker", "exec", container, "pg_dump", "-U", "yuchion", "-d", "yuchion_test"]
        env = os.environ.copy()
    else:
        executable = shutil.which("pg_dump")
        assert executable, "직접 DB 시험에는 pg_dump가 필요해요. tools/test_db.sh는 컨테이너 것을 써요."
        args = [executable]
        url = db.database_url()
        env = {**os.environ, "PGHOST": url.host or "localhost", "PGPORT": str(url.port or 5432),
               "PGUSER": url.username or "", "PGPASSWORD": url.password or "", "PGDATABASE": url.database or ""}
    result = subprocess.run([*args, "--schema-only", "--no-owner", "--no-privileges"],
                            env=env, text=True, capture_output=True, check=True)
    # 최근 pg_dump의 무작위 psql 보호 키만 제외한다. DDL 본문은 그대로 비교한다.
    return "\n".join(line for line in result.stdout.splitlines()
                     if not line.startswith(("\\restrict ", "\\unrestrict ")))


def test_upgrade_downgrade_upgrade(db_engine, alembic_config):
    command.upgrade(alembic_config, "head")
    with db_engine.connect() as connection:
        first_catalog = dict(catalog(connection))
    assert first_catalog == HEAD_CATALOG
    first_dump = schema_dump()

    command.downgrade(alembic_config, "base")
    with db_engine.connect() as connection:
        assert dict(catalog(connection)) == dict.fromkeys(first_catalog, 0)
        assert connection.scalar(text("SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
                                      "WHERE n.nspname='public'")) == 0
        assert connection.scalar(text("SELECT count(*) FROM pg_extension WHERE extname IN ('vector','btree_gist')")) == 0

    command.upgrade(alembic_config, "head")
    with db_engine.connect() as connection:
        assert dict(catalog(connection)) == first_catalog
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0015"
    assert schema_dump() == first_dump

    # 최신 설계를 직접 적용한 스키마도 마이그레이션 head와 같아야 한다.
    command.downgrade(alembic_config, "base")
    with db_engine.begin() as connection:
        connection.exec_driver_sql((ROOT / "Docs/Step2/db_schema_draft.sql").read_text(encoding="utf-8"))
    assert schema_dump() == first_dump
    command.stamp(alembic_config, "head")


def test_child_memos_backfill_constraints_and_revision_round_trip(db_engine, alembic_config):
    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "0001")
    with db_engine.begin() as connection:
        seed_demo(connection)
        before = dict(connection.execute(text("""
            INSERT INTO daily_note_inputs (org_id, classroom_id, author_id, note_date, activities, supplies)
            VALUES (:org, :classroom, :author, '2026-11-20', '[TEST] 블록 놀이', '[TEST] 수건')
            RETURNING *
        """), {"org": seed.ORG, "classroom": seed.CLASS_STAR, "author": seed.TEACHER}).mappings().one())
    v1_dump = schema_dump()

    command.upgrade(alembic_config, "head")
    with db_engine.begin() as connection:
        assert dict(connection.execute(text("SELECT * FROM daily_note_inputs WHERE id=:id"),
                                       {"id": before["id"]}).mappings().one()) == {**before, "child_memos": []}
        memos = [{"child_id": str(seed.CHILD), "memo": "  블록으로 높은 탑을 쌓음\n함께 놀이  "}]
        for value in ([], memos):
            saved = connection.scalar(text("""
                UPDATE daily_note_inputs SET child_memos=CAST(:value AS jsonb)
                WHERE id=:id RETURNING child_memos
            """), {"id": before["id"], "value": json.dumps(value, ensure_ascii=False)})
            assert saved == value
        # SQL NULL과 JSON null·객체·문자열·숫자·불리언을 각각 거부한다.
        for invalid in (None, "null", "{}", '"메모"', "1", "true"):
            with pytest.raises(IntegrityError) as error, connection.begin_nested():
                connection.execute(text("UPDATE daily_note_inputs SET child_memos=CAST(:value AS jsonb) WHERE id=:id"),
                                   {"id": before["id"], "value": invalid})
            assert error.value.orig.sqlstate == ("23502" if invalid is None else "23514")
            if invalid is not None:
                assert error.value.orig.diag.constraint_name == "daily_note_inputs_child_memos_array"
        assert connection.scalar(text("SELECT child_memos FROM daily_note_inputs WHERE id=:id"),
                                 {"id": before["id"]}) == memos
        # 새 입력도 생략하면 빈 배열을 받는다.
        assert connection.scalar(text("""
            INSERT INTO daily_note_inputs (org_id, classroom_id, author_id, note_date)
            VALUES (:org, :classroom, :author, '2026-11-21') RETURNING child_memos
        """), {"org": seed.ORG, "classroom": seed.CLASS_STAR, "author": seed.TEACHER}) == []

    command.downgrade(alembic_config, "0001")
    assert schema_dump() == v1_dump
    with db_engine.connect() as connection:
        assert dict(catalog(connection)) == {"tables": 27, "views": 2, "triggers": 2, "foreign_keys": 57, "columns": 266}
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0001"
        assert dict(connection.execute(text("SELECT * FROM daily_note_inputs WHERE id=:id"),
                                       {"id": before["id"]}).mappings().one()) == before

    command.upgrade(alembic_config, "head")
    with db_engine.begin() as connection:
        assert dict(catalog(connection)) == HEAD_CATALOG
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0015"
        assert dict(connection.execute(text("SELECT * FROM daily_note_inputs WHERE id=:id"),
                                       {"id": before["id"]}).mappings().one()) == {**before, "child_memos": []}
        connection.execute(text("DELETE FROM daily_note_inputs"))


def test_requeue_action_upgrade_downgrade_preserves_requests_and_old_events(seeded_db, alembic_config):
    with seeded_db.begin() as connection:
        original = connection.scalar(text("""
            INSERT INTO events(org_id,request_id,actor_type,action)
            VALUES (:org,:request,'system','created') RETURNING id
        """), {"org": seed.ORG, "request": seed.REQUEST_COUGH})
        connection.execute(text("""
            INSERT INTO events(org_id,request_id,actor_type,action)
            VALUES (:org,:request,'system','agent_requeued')
        """), {"org": seed.ORG, "request": seed.REQUEST_COUGH})
        request_before = dict(connection.execute(text("SELECT * FROM requests WHERE id=:id"),
                                                 {"id": seed.REQUEST_COUGH}).mappings().one())
    command.downgrade(alembic_config, "0005")
    # 없어진 칸을 포함하는 SELECT * 준비 구문이 풀 연결에 남지 않게 해요.
    seeded_db.dispose()
    request_before.pop("care_detail")  # 0012보다 이전 판에는 없는 칸이에요.
    with seeded_db.begin() as connection:
        assert connection.scalar(text("SELECT count(*) FROM events WHERE id=:id"), {"id": original}) == 1
        assert connection.scalar(text("SELECT count(*) FROM events WHERE action='agent_requeued'")) == 0
        assert dict(connection.execute(text("SELECT * FROM requests WHERE id=:id"),
                                       {"id": seed.REQUEST_COUGH}).mappings().one()) == request_before
        with pytest.raises(IntegrityError) as error, connection.begin_nested():
            connection.execute(text("INSERT INTO events(org_id,actor_type,action) VALUES (:org,'system','agent_requeued')"),
                               {"org": seed.ORG})
        assert error.value.orig.diag.constraint_name == "events_action_check"
    command.upgrade(alembic_config, "head")
    with seeded_db.begin() as connection:
        connection.execute(text("INSERT INTO events(org_id,actor_type,action) VALUES (:org,'system','agent_requeued')"),
                           {"org": seed.ORG})
        assert dict(catalog(connection)) == HEAD_CATALOG


def test_0012_care_backfill_and_round_trip_preserve_events_and_notifications(seeded_db, alembic_config):
    command.downgrade(alembic_config, "0011")
    inputs = [
        ("medication", {"medication_name": "[TEST] 시럽", "medication_dose": "2.5mL", "medication_time": "점심 뒤"}),
        ("pickup", {"pickup_guardian_id": str(seed.PARENT), "pickup_name": "[TEST] 보호자", "pickup_relation": "mother"}),
        ("medication", {"medication_name": "[TEST] 약", "medication_dose": None}),
        ("pickup", {}),
        ("inquiry", {"medication_name": "[TEST] 일반 문의의 별도 정보"}),
    ]
    requests, receipts = {}, {}
    with seeded_db.begin() as connection:
        for index, (kind, fields) in enumerate(inputs):
            request_id = connection.scalar(text("""
                INSERT INTO requests (org_id,classroom_id,child_id,requester_id,client_request_id,type,body)
                VALUES (:org,:class,:child,:parent,:key,:kind,'[TEST] 0012 접수') RETURNING id
            """), {"org": seed.ORG, "class": seed.CLASS_STAR, "child": seed.CHILD, "parent": seed.PARENT,
                   "key": f"[TEST] care-backfill-{index}", "kind": kind})
            requests[request_id] = fields if kind in ("medication", "pickup") else {}
            detail = {**fields, "trace_id": f"[TEST] receipt-{index}"}
            row = dict(connection.execute(text("""
                INSERT INTO events (org_id,request_id,actor_type,actor_id,action,to_status,detail)
                VALUES (:org,:request,'user',:parent,'created','received',CAST(:detail AS jsonb)) RETURNING *
            """), {"org": seed.ORG, "request": request_id, "parent": seed.PARENT,
                   "detail": json.dumps(detail, ensure_ascii=False)}).mappings().one())
            receipts[row["id"]] = row
        # 추가 글·교직원 확인 이력의 값은 접수 입력이 아니므로 그대로 남아요.
        untouched = dict(connection.execute(text("""
            INSERT INTO events (org_id,request_id,actor_type,action,to_status,detail)
            VALUES (:org,:request,'system','checked','assigned',
                    '{"pickup_snapshot": {"pickup_name": "[TEST] 확인 당시 인계자"}}') RETURNING *
        """), {"org": seed.ORG, "request": list(requests)[1]}).mappings().one())
        no_receipt = connection.scalar(text("""
            INSERT INTO requests (org_id,requester_id,client_request_id,type,body)
            VALUES (:org,:parent,'[TEST] no-receipt','pickup','[TEST] 접수 이력 없는 기존 요청') RETURNING id
        """), {"org": seed.ORG, "parent": seed.PARENT})
    old_dump = schema_dump()

    command.upgrade(alembic_config, "head")
    new_actions = ("message_added", "out_of_scope_answered", "cancelled", "care_updated",
                   "daily_note_corrected", "slot_conflict_reproposed", "report_acknowledged")
    new_kinds = ("parent_message", "reassigned", "consultation_booked", "note_corrected", "cancelled", "care_rejected")
    with seeded_db.begin() as connection:
        assert dict(connection.execute(text("SELECT id,care_detail FROM requests WHERE id=ANY(:ids)"),
                                       {"ids": list(requests)}).all()) == requests
        assert connection.scalar(text("SELECT care_detail FROM requests WHERE id=:id"), {"id": no_receipt}) == {}
        for event_id, before in receipts.items():
            after = dict(connection.execute(text("SELECT * FROM events WHERE id=:id"), {"id": event_id}).mappings().one())
            fields = requests[before["request_id"]]
            expected = {"trace_id": before["detail"]["trace_id"], "fields": sorted(fields)}
            if before["request_id"] == list(requests)[-1]:
                expected = before["detail"]  # 일반 문의는 백필·이력 정리 대상이 아니에요.
            assert after == {**before, "detail": expected}
        assert dict(connection.execute(text("SELECT * FROM events WHERE id=:id"),
                                       {"id": untouched["id"]}).mappings().one()) == untouched
        with pytest.raises(IntegrityError) as error, connection.begin_nested():
            connection.execute(text("UPDATE requests SET care_detail=NULL WHERE id=:id"), {"id": no_receipt})
        assert error.value.orig.sqlstate == "23502"
        for action in new_actions:
            connection.execute(text("INSERT INTO events (org_id,actor_type,action) VALUES (:org,'system',:action)"),
                               {"org": seed.ORG, "action": action})
        for kind in new_kinds:
            connection.execute(text("""
                INSERT INTO notifications (org_id,recipient_id,kind,title,dedupe_key)
                VALUES (:org,:parent,:kind,'[TEST] 새 알림',:key)
            """), {"org": seed.ORG, "parent": seed.PARENT, "kind": kind, "key": f"[TEST] 0012-{kind}"})
        for table, column in (("events", "action"), ("notifications", "kind")):
            with pytest.raises(IntegrityError) as error, connection.begin_nested():
                connection.execute(text(f"UPDATE {table} SET {column}='[TEST] invalid'"))
            assert error.value.orig.diag.constraint_name == f"{table}_{column}_check"
        events_before = connection.execute(text("SELECT * FROM events ORDER BY id")).mappings().all()
        notifications_before = connection.execute(text("SELECT * FROM notifications ORDER BY id")).mappings().all()

    command.downgrade(alembic_config, "0011")
    with seeded_db.begin() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0011"
        assert connection.scalar(text("""
            SELECT count(*) FROM information_schema.columns WHERE table_name='requests' AND column_name='care_detail'
        """)) == 0
        for before in events_before:
            expected = receipts.get(before["id"], before)
            assert dict(connection.execute(text("SELECT * FROM events WHERE id=:id"),
                                           {"id": before["id"]}).mappings().one()) == expected
        assert connection.scalar(text("SELECT count(*) FROM events")) == len(events_before)
        assert connection.execute(text("SELECT * FROM notifications ORDER BY id")).mappings().all() == notifications_before
        for table, column, value in (("events", "action", new_actions[0]), ("notifications", "kind", new_kinds[0])):
            with pytest.raises(IntegrityError) as error, connection.begin_nested():
                connection.execute(text(f"UPDATE {table} SET {column}=:value"), {"value": value})
            assert error.value.orig.diag.constraint_name == f"{table}_{column}_check"

    command.upgrade(alembic_config, "head")
    with seeded_db.begin() as connection:
        assert connection.execute(text("SELECT * FROM events ORDER BY id")).mappings().all() == events_before
        assert connection.execute(text("SELECT * FROM notifications ORDER BY id")).mappings().all() == notifications_before
        assert connection.scalar(text("SELECT bool_and(convalidated) FROM pg_constraint "
                                      "WHERE conname IN ('events_action_check','notifications_kind_check')")) is True
        # 새 값이 없는 DB의 downgrade는 제약 검증 상태까지 원래 스키마와 같아요.
        connection.execute(text("DELETE FROM events WHERE action=ANY(:values)"), {"values": list(new_actions)})
        connection.execute(text("DELETE FROM notifications WHERE kind=ANY(:values)"), {"values": list(new_kinds)})
    command.downgrade(alembic_config, "0011")
    assert schema_dump() == old_dump
    command.upgrade(alembic_config, "head")


def test_consultation_report_acknowledge_revision_preserves_decisions_on_downgrade(seeded_db, alembic_config):
    command.downgrade(alembic_config, "0013")
    old_dump = schema_dump()
    command.upgrade(alembic_config, "head")
    with seeded_db.begin() as connection:
        rid = connection.scalar(text("""
            INSERT INTO requests (org_id,requester_id,client_request_id,type,body)
            VALUES (:org,:parent,'[TEST] acknowledge-migration','consultation','[TEST] 원장 보고') RETURNING id
        """), {"org": seed.ORG, "parent": seed.PARENT})
        cid = connection.scalar(text("""
            INSERT INTO cards (org_id,request_id,kind,assignee_id)
            VALUES (:org,:request,'director_report',:director) RETURNING id
        """), {"org": seed.ORG, "request": rid, "director": seed.DIRECTOR})
        row = dict(connection.execute(text("""
            INSERT INTO approvals (org_id,card_id,card_version,decided_by,decision)
            VALUES (:org,:card,1,:director,'acknowledge') RETURNING *
        """), {"org": seed.ORG, "card": cid, "director": seed.DIRECTOR}).mappings().one())
    command.downgrade(alembic_config, "0013")
    with seeded_db.begin() as connection:
        assert dict(connection.execute(text("SELECT * FROM approvals WHERE id=:id"),
                                       {"id": row["id"]}).mappings().one()) == row
        assert connection.scalar(text("SELECT convalidated FROM pg_constraint WHERE conname='approvals_decision_check'")) is False
        with pytest.raises(IntegrityError) as error, connection.begin_nested():
            connection.execute(text("UPDATE approvals SET decision='acknowledge' WHERE id=:id"), {"id": row["id"]})
        assert error.value.orig.diag.constraint_name == "approvals_decision_check"
    command.upgrade(alembic_config, "head")
    with seeded_db.begin() as connection:
        assert dict(connection.execute(text("SELECT * FROM approvals WHERE id=:id"),
                                       {"id": row["id"]}).mappings().one()) == row
        assert connection.scalar(text("SELECT convalidated FROM pg_constraint WHERE conname='approvals_decision_check'")) is True
        connection.execute(text("DELETE FROM approvals WHERE id=:id"), {"id": row["id"]})
    command.downgrade(alembic_config, "0013")
    assert schema_dump() == old_dump
    command.upgrade(alembic_config, "head")


def test_note_original_backfill_and_event_fk_revision_round_trip(db_engine, alembic_config):
    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "0002")
    with db_engine.begin() as connection:
        seed_demo(connection)
        input_id = connection.scalar(text("""
            INSERT INTO daily_note_inputs (org_id,classroom_id,author_id,note_date)
            VALUES (:org,:class,:author,'2026-11-20') RETURNING id
        """), {"org": seed.ORG, "class": seed.CLASS_STAR, "author": seed.TEACHER})
        note_id = connection.scalar(text("""
            INSERT INTO daily_notes (org_id,input_id,child_id,note_date,content)
            VALUES (:org,:input,:child,'2026-11-20','{"items": []}') RETURNING id
        """), {"org": seed.ORG, "input": input_id, "child": seed.CHILD})
    old_dump = schema_dump()
    command.upgrade(alembic_config, "head")
    with db_engine.begin() as connection:
        assert connection.scalar(text("SELECT ai_original FROM daily_notes WHERE id=:id"), {"id": note_id}) == {"items": []}
        other_org = connection.scalar(text("INSERT INTO organizations (name) VALUES ('[TEST] 다른 기관') RETURNING id"))
        for action in ("daily_note_drafted", "daily_note_edited", "daily_note_confirmed", "daily_note_sent"):
            connection.execute(text("""
                INSERT INTO events (org_id,daily_note_id,actor_type,action)
                VALUES (:org,:note,'system',:action)
            """), {"org": seed.ORG, "note": note_id, "action": action})
        with pytest.raises(IntegrityError) as error, connection.begin_nested():
            connection.execute(text("""
                INSERT INTO events (org_id,daily_note_id,actor_type,action)
                VALUES (:org,:note,'system','daily_note_drafted')
            """), {"org": other_org, "note": note_id})
        assert error.value.orig.sqlstate == "23503"
    command.downgrade(alembic_config, "0002")
    assert schema_dump() == old_dump
    with db_engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM daily_notes")) == 1
        assert connection.scalar(text("SELECT count(*) FROM events")) == 0
    command.upgrade(alembic_config, "head")
    with db_engine.connect() as connection:
        assert dict(catalog(connection)) == HEAD_CATALOG
        assert connection.scalar(text("SELECT ai_original FROM daily_notes WHERE id=:id"), {"id": note_id}) == {"items": []}


def test_0015_note_correction_backfill_constraints_and_round_trip(seeded_db, alembic_config):
    command.downgrade(alembic_config, "0014")
    with seeded_db.begin() as connection:
        input_id = connection.scalar(text("""
            INSERT INTO daily_note_inputs (org_id,classroom_id,author_id,note_date)
            VALUES (:org,:class,:author,'2026-11-20') RETURNING id
        """), {"org": seed.ORG, "class": seed.CLASS_STAR, "author": seed.TEACHER})
        before = dict(connection.execute(text("""
            INSERT INTO daily_notes (org_id,input_id,child_id,note_date,status,content,ai_original,
                                     confirmed_by,confirmed_at,sent_at)
            VALUES (:org,:input,:child,'2026-11-20','sent','{"items": []}','{"items": []}',:teacher,now(),now())
            RETURNING *
        """), {"org": seed.ORG, "input": input_id, "child": seed.CHILD, "teacher": seed.TEACHER}).mappings().one())
    old_dump = schema_dump()
    command.upgrade(alembic_config, "head")
    with seeded_db.begin() as connection:
        assert dict(connection.execute(text("SELECT * FROM daily_notes WHERE id=:id"),
                                       {"id": before["id"]}).mappings().one()) == {
            **before, "version": 1, "corrected_at": None}
        for value, state in ((0, "23514"), (None, "23502")):
            with pytest.raises(IntegrityError) as error, connection.begin_nested():
                connection.execute(text("UPDATE daily_notes SET version=:version WHERE id=:id"),
                                   {"id": before["id"], "version": value})
            assert error.value.orig.sqlstate == state
        connection.execute(text("UPDATE daily_notes SET version=2,corrected_at=now() WHERE id=:id"), {"id": before["id"]})
        event_id = connection.scalar(text("""
            INSERT INTO events (org_id,daily_note_id,actor_type,actor_id,action,from_status,to_status,detail)
            VALUES (:org,:note,'user',:teacher,'daily_note_corrected','sent','sent',
                    CAST(:detail AS jsonb)) RETURNING id
        """), {"org": seed.ORG, "note": before["id"], "teacher": seed.TEACHER,
               "detail": json.dumps({"reason_text": "[TEST] 정정", "version": 2})})
        event = dict(connection.execute(text("SELECT * FROM events WHERE id=:id"), {"id": event_id}).mappings().one())
    command.downgrade(alembic_config, "0014")
    assert schema_dump() == old_dump
    with seeded_db.connect() as connection:
        assert dict(connection.execute(text("SELECT * FROM daily_notes WHERE id=:id"),
                                       {"id": before["id"]}).mappings().one()) == before
        assert dict(connection.execute(text("SELECT * FROM events WHERE id=:id"), {"id": event_id}).mappings().one()) == event
    command.upgrade(alembic_config, "head")
    with seeded_db.begin() as connection:
        assert dict(catalog(connection)) == HEAD_CATALOG
        assert dict(connection.execute(text("SELECT * FROM events WHERE id=:id"), {"id": event_id}).mappings().one()) == event
        # 보존 확인을 마친 이 시험의 0012 이력은 정리해 다음 base 왕복 시험과 격리해요.
        connection.execute(text("DELETE FROM events WHERE id=:id"), {"id": event_id})


def test_seed_twice_keeps_same_rows_and_password_hash(db_engine, alembic_config):
    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "head")
    # CLI부터 시험해서 import 경로·DATABASE_URL·트랜잭션도 함께 확인한다.
    root = Path(__file__).resolve().parents[3]
    env = {**os.environ, "PYTHONPATH": str(root / "apps/api")}

    def run_seed(*args):
        subprocess.run([sys.executable, "-m", "db.seeds.demo", *args], cwd=root, env=env,
                       capture_output=True, text=True, check=True)
    tables = ("organizations", "classrooms", "users", "classroom_staff", "children", "child_guardians", "rooms",
              "documents", "document_chunks", "requests", "feed_posts", "feed_photos", "feed_photo_children")

    def snapshot():
        with db_engine.connect() as connection:
            return {table: connection.execute(text(f"SELECT * FROM {table} ORDER BY 1, 2")).mappings().all()
                    for table in tables}

    run_seed()
    first = snapshot()
    run_seed()
    assert snapshot() == first
    assert {table: len(rows) for table, rows in first.items()} == dict(zip(tables, (1, 2, 21, 2, 21, 19, 1, 3, 3, 22, 4, 5, 5), strict=True))
    classrooms = {row["id"]: row for row in first["classrooms"]}
    assert (classrooms[seed.CLASS_STAR]["name"], classrooms[seed.CLASS_STAR]["age_group"]) == ("만 4세 별빛반", 4)
    assert (classrooms[seed.CLASS_SUN]["name"], classrooms[seed.CLASS_SUN]["age_group"]) == ("만 5세 햇님반", 5)
    assert first["organizations"][0]["id"] == seed.ORG
    assert first["organizations"][0]["is_virtual"] is True
    users = {row["id"]: row for row in first["users"]}
    for expected in seed.USERS:
        user = users[expected["id"]]
        for key in ("id", "role", "login_id", "display_name"):
            assert user[key] == expected[key]
        assert user["org_id"] == seed.ORG
        assert user["password_hash"].startswith("$argon2id$")
        assert PasswordHasher().verify(user["password_hash"], seed.DEMO_PASSWORD)
    children = {row["id"]: row for row in first["children"]}
    assert children.keys() == {row["id"] for row in seed.CHILDREN}
    for expected in seed.CHILDREN:
        child = children[expected["id"]]
        assert (child["display_name"], child["classroom_id"], child["org_id"], child["is_virtual"]) == (
            expected["display_name"], expected["classroom_id"], seed.ORG, True)
    assert sum(row["classroom_id"] == seed.CLASS_STAR for row in children.values()) == 20
    assert sum(row["classroom_id"] == seed.CLASS_SUN for row in children.values()) == 1
    assert children.keys().isdisjoint(seed.demo_id(f"55{number:02d}") for number in range(1, 19))
    assert {(row["classroom_id"], row["user_id"], row["valid_from"], row["valid_to"])
            for row in first["classroom_staff"]} == {
        (row["classroom_id"], row["user_id"], row["valid_from"], row["valid_to"])
        for row in seed.CLASSROOM_STAFF}
    assert {(row["child_id"], row["user_id"], row["relation"]) for row in first["child_guardians"]} == {
        (child["id"], guardian, seed.GUARDIAN_RELATIONS.get((child["id"], guardian), "other"))
        for child in seed.CHILDREN for guardian in child["guardian_ids"]}
    requests = {row["id"]: row for row in first["requests"]}
    for expected in seed.DEMO_NOTE_REQUESTS:
        assert all(requests[expected["id"]][key] == value for key, value in expected.items())
        assert requests[expected["id"]]["org_id"] == seed.ORG
    documents = {row["id"]: row for row in first["documents"]}
    chunks = {row["document_id"]: row["content"] for row in first["document_chunks"]}
    for document_id, title, kind, status, content in seed.DEMO_DOCUMENTS:
        assert (documents[document_id]["title"], documents[document_id]["doc_type"],
                documents[document_id]["status"], chunks[document_id]) == (title, kind, status, content)

    # 날짜 갱신은 데모 요청과 첫 보호자 메시지를 맞춘다. 일반 요청은 그대로 둔다.
    unrelated = uuid4()
    with db_engine.begin() as connection:
        connection.execute(text("""
            INSERT INTO requests (id,org_id,classroom_id,child_id,requester_id,client_request_id,type,body,created_at)
            SELECT :id,org_id,classroom_id,child_id,requester_id,:key,type,'[TEST] 일반 요청',created_at
            FROM requests WHERE id=:source
        """), {"id": unrelated, "key": f"test:{unrelated}", "source": seed.REQUEST_COUGH})
    before_refresh = snapshot()
    start = datetime.now(UTC)
    run_seed("--refresh-note-requests")
    end = datetime.now(UTC)
    refreshed = snapshot()
    originals = {r["id"]: r["created_at"] for r in seed.DEMO_NOTE_REQUESTS if "created_at" in r}
    latest = max(value.astimezone(KST).date() for value in originals.values())
    shift = end.astimezone(KST).date() - latest
    for table in tables:
        if table != "requests":
            assert refreshed[table] == before_refresh[table]
            continue
        for old, new in zip(before_refresh[table], refreshed[table], strict=True):
            if old["id"] == unrelated:
                assert new == old
            else:
                if old["id"] in originals:
                    assert new["created_at"] == originals[old["id"]] + shift
                else:
                    assert start <= new["created_at"] <= end
                assert dict(new) == {**old, "created_at": new["created_at"]}
    assert max(r["created_at"].astimezone(KST).date() for r in refreshed["requests"]
               if r["id"] in originals) == end.astimezone(KST).date()
    run_seed()
    assert snapshot() == refreshed


@pytest.mark.parametrize("now", ["2026-12-31T15:05:00+00:00", "2026-11-09T14:55:00+00:00"])
def test_refresh_requests_preserves_fixture_offsets_and_daily_input(seeded_db, monkeypatch, now):
    from db.seeds import demo
    from app.modules.daily_notes.runner import _payload

    current = datetime.fromisoformat(now)

    class Clock:
        @staticmethod
        def now(tz):
            return current.astimezone(tz)

    monkeypatch.setattr(demo, "datetime", Clock)
    today = current.astimezone(KST).date()
    originals = {r["id"]: r["created_at"] for r in seed.DEMO_NOTE_REQUESTS if "created_at" in r}
    shift = today - max(dt.astimezone(KST).date() for dt in originals.values())
    with seeded_db.begin() as connection:
        first_messages = dict(connection.execute(text("SELECT request_id,id FROM request_messages")).all())
        extra = connection.scalar(text("""
            INSERT INTO request_messages (org_id,request_id,sender_type,sender_id,body,created_at)
            SELECT org_id,id,'user',requester_id,'[TEST] 추가 대화',created_at + interval '1 minute'
            FROM requests WHERE id=:id RETURNING id
        """), {"id": seed.demo_id("7214")})
        extra_before = dict(connection.execute(text("SELECT * FROM request_messages WHERE id=:id"),
                                               {"id": extra}).mappings().one())
        for _ in range(2):
            seed_demo(connection, refresh_note_requests=True)
            actual = dict(connection.execute(text("SELECT id,created_at FROM requests")).all())
            messages = dict(connection.execute(text("SELECT id,created_at FROM request_messages")).all())
            assert all(messages[mid] == actual[rid] for rid, mid in first_messages.items())
            assert dict(connection.execute(text("SELECT * FROM request_messages WHERE id=:id"),
                                           {"id": extra}).mappings().one()) == extra_before
            assert len(messages) == len(first_messages) + 1
            for rid, original in originals.items():
                assert actual[rid] == original + shift
            assert actual[seed.REQUEST_COUGH] == actual[seed.REQUEST_PICKUP] == current
        for day in (today, today - timedelta(days=1)):
            # 오늘 초안에는 최신 fixture의 GR-02·10·19만, 전날 요청은 전날에 남아요.
            payload = _payload(connection, {"id": uuid4(), "org_id": seed.ORG,
                               "classroom_id": seed.CLASS_STAR, "note_date": day,
                               "activities": "[TEST] 날짜 이동", "supplies": "", "child_memos": []})
            observed = {r["request_id"] for child in payload["children"] for r in child["requests"]}
            assert observed == {str(rid) for rid, dt in actual.items() if dt.astimezone(KST).date() == day}
            if day == today:
                assert observed == {str(seed.REQUEST_COUGH), str(seed.REQUEST_PICKUP),
                                    *(str(seed.demo_id(f"72{n:02d}")) for n in (2, 10, 19))}
    assert {r["id"]: r["created_at"] for r in seed.DEMO_NOTE_REQUESTS if "created_at" in r} == originals


def test_transaction_commits_and_rolls_back(db_engine, alembic_config):
    command.upgrade(alembic_config, "head")
    assert db.get_engine() is db_engine
    with db.transaction() as connection:
        org_id = connection.scalar(text("INSERT INTO organizations (name) VALUES ('[TEST] rollback') RETURNING id"))
    with pytest.raises(RuntimeError, match="rollback"):
        with db.transaction() as connection:
            connection.execute(text("UPDATE organizations SET name='changed' WHERE id=:id"), {"id": org_id})
            raise RuntimeError("rollback")
    with db.transaction() as connection:
        assert connection.scalar(text("SELECT name FROM organizations WHERE id=:id"), {"id": org_id}) == "[TEST] rollback"
        connection.execute(text("DELETE FROM organizations WHERE id=:id"), {"id": org_id})
