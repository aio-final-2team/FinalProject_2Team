"""T19 완료 기준: v0.7 카탈로그·up/down/up 덤프·시드 재실행·트랜잭션."""

import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
from alembic import command
from argon2 import PasswordHasher
from sqlalchemy import text

from app.core import db
from app.mock import seed


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
    assert first_catalog == {"tables": 27, "views": 2, "triggers": 2, "foreign_keys": 57, "columns": 266}
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
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0001"
    assert schema_dump() == first_dump


def test_seed_twice_keeps_same_rows_and_password_hash(db_engine, alembic_config):
    command.upgrade(alembic_config, "head")
    # CLI부터 시험해서 import 경로·DATABASE_URL·트랜잭션도 함께 확인한다.
    root = Path(__file__).resolve().parents[3]
    env = {**os.environ, "PYTHONPATH": str(root / "apps/api")}

    def run_seed():
        subprocess.run([sys.executable, "-m", "db.seeds.demo"], cwd=root, env=env,
                       capture_output=True, text=True, check=True)
    tables = ("organizations", "classrooms", "users", "classroom_staff", "children", "child_guardians", "rooms")

    def snapshot():
        with db_engine.connect() as connection:
            return {table: connection.execute(text(f"SELECT * FROM {table} ORDER BY 1, 2")).mappings().all()
                    for table in tables}

    run_seed()
    first = snapshot()
    run_seed()
    assert snapshot() == first
    assert {table: len(rows) for table, rows in first.items()} == dict(zip(tables, (1, 2, 5, 2, 3, 3, 1), strict=True))
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
    assert {row["id"] for row in first["children"]} == {row["id"] for row in seed.CHILDREN}
    assert {(row["child_id"], row["user_id"]) for row in first["child_guardians"]} == {
        (child["id"], guardian) for child in seed.CHILDREN for guardian in child["guardian_ids"]}


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
