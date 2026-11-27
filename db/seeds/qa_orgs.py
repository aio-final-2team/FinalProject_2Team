"""기존 시드를 임시 표에서 재사용해 QA 원을 만들어요. 공개 표·기존 QA 행은 덮지 않아요."""

import json
import logging
import re
from uuid import UUID

from argon2 import PasswordHasher
from sqlalchemy import text

from app.core import media
from app.core.config import settings
from app.core.db import transaction
from app.core.qa_orgs import QA_ORGS, qa_id
from app.mock import seed
from app.modules.documents import embedding
from db.seeds.demo import seed_demo
from db.seeds.documents import seed_documents
from db.seeds.memories import seed_memories
from db.seeds.care_notes import seed_care_notes
from db.seeds.consultations import seed_consultations
from db.seeds.daily_records import seed_daily_records

# FK 자식부터. 요청의 source_note_id 때문에 requests를 daily_notes보다 먼저 지워요.
DELETE_ORDER = tuple("saved_answer_sources saved_answers notifications events approvals card_evidence "
                     "consultation_bookings consultation_slots memories memory_rules cards request_messages requests "
                     "daily_notes daily_note_inputs daily_records feed_photo_children feed_photos feed_posts "
                     "document_classrooms document_chunks documents staff_busy_blocks rooms child_guardians children "
                     "classroom_staff user_consents user_settings users classrooms".split())
INSERT_ORDER = tuple("organizations classrooms users user_consents user_settings classroom_staff children "
                     "child_guardians rooms staff_busy_blocks documents document_chunks document_classrooms requests "
                     "request_messages cards card_evidence approvals consultation_slots consultation_bookings memories "
                     "memory_rules saved_answers saved_answer_sources daily_note_inputs daily_notes daily_records "
                     "events notifications feed_posts feed_photos feed_photo_children".split())
UUID_PATTERN = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")


def template(connection):
    # LIKE는 FK·트리거를 복사하지 않아요. IDENTITY 시퀀스는 임시 표 전용으로 새로 생겨요.
    # savepoint rollback으로 임시 표·시퀀스·search_path를 함께 복원해 풀 연결에도 남기지 않아요.
    point = connection.begin_nested()
    try:
        for table in INSERT_ORDER:
            connection.execute(text(f"CREATE TEMP TABLE {table} (LIKE public.{table} INCLUDING ALL) ON COMMIT DROP"))
            if connection.scalar(text("""SELECT data_type='uuid' FROM information_schema.columns
                WHERE table_schema='public' AND table_name=:table AND column_name='id'"""), {"table": table}):
                # 자동 UUID도 원본 표별 삽입 순서에서 고정해 reset 뒤 연결이 같아요.
                connection.execute(text(f"CREATE TEMP SEQUENCE qa_{table}_ids"))
                connection.execute(text(f"ALTER TABLE pg_temp.{table} ALTER id SET DEFAULT "
                                        f"md5('qa-source:{table}:' || nextval('pg_temp.qa_{table}_ids'))::uuid"))
        connection.execute(text("SET LOCAL search_path=pg_temp,public"))
        seed_demo(connection, write_media=False)
        for seeder in (seed_documents, seed_memories, seed_care_notes, seed_consultations, seed_daily_records):
            seeder(connection)
        connection.execute(text("""UPDATE pg_temp.document_chunks q SET embedding=d.embedding,
            embedding_model=d.embedding_model, embedding_version=d.embedding_version
            FROM public.document_chunks d WHERE d.org_id=:demo AND d.content=q.content AND d.embedding IS NOT NULL
        """), {"demo": seed.ORG})
        # 같은 자료는 한 번만 채우고 다섯 원에 복사해요. 공개 표를 fill_missing에 넘기지 않아요.
        embedding.fill_missing(connection)
        return {table: [dict(row) for row in connection.execute(text(f"SELECT * FROM pg_temp.{table}")).mappings()]
                for table in INSERT_ORDER}
    finally:
        point.rollback()


def lock(connection, org):
    connection.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
                       {"key": f"qa-sandbox:{qa_id(org['tag'], seed.ORG)}"})


def populate(connection, org, source):
    tag = org["tag"]
    integer_base = (next(i for i, row in enumerate(QA_ORGS) if row["tag"] == tag) + 1) * 10**12

    def convert(value, key=""):
        if isinstance(value, UUID):
            return str(qa_id(tag, value))
        if isinstance(value, dict):
            return {k: convert(v, k) for k, v in value.items()}
        if isinstance(value, list):
            return [convert(v) for v in value]
        if type(value) is int and (key == "id" or key.endswith("_id")):
            return integer_base + value
        if isinstance(value, str):
            return UUID_PATTERN.sub(lambda match: str(qa_id(tag, match[0])), value)
        return value

    password_hash = PasswordHasher().hash(settings.qa_password)
    for table in INSERT_ORDER:
        rows = []
        for original in source[table]:
            row = convert(original)
            if table == "organizations":
                row["name"] = org["name"]
            if table == "users":
                row.update(login_id=tag + "." + original["login_id"], password_hash=password_hash)
            for key in ("client_request_id", "dedupe_key"):
                if row.get(key):
                    row[key] = tag + ":" + row[key]
            if table == "feed_photos":
                data = seed.feed_photo(original["id"])
                metadata = media.inspect(data)
                row["storage_path"] = f"{row['id']}.{metadata['extension']}"
                if not media.path(row["storage_path"]).is_file():
                    media.save(data, metadata, file_id=row["id"])
            rows.append({"row": json.dumps(row, default=str)})
        if rows:
            conflict = "ON CONFLICT (id) DO NOTHING" if table == "organizations" else ""
            connection.execute(text(f"INSERT INTO public.{table} OVERRIDING SYSTEM VALUE "
                f"SELECT * FROM jsonb_populate_record(NULL::public.{table},CAST(:row AS jsonb)) "
                f"{conflict}"), rows)
    return {table: len(source[table]) for table in ("users", "children", "documents")}


def seed_qa_orgs(connection):
    if not settings.qa_tools:
        return
    if not settings.qa_password:
        logging.getLogger("yuchion.api").info("QA_PASSWORD가 비어 있어 QA 원 시드를 건너뛰어요")
        return
    source = None
    for org in QA_ORGS:
        lock(connection, org)
        if connection.scalar(text("SELECT EXISTS(SELECT 1 FROM organizations WHERE id=:id)"),
                             {"id": qa_id(org["tag"], seed.ORG)}):
            continue
        if source is None:
            source = template(connection)
        populate(connection, org, source)


if __name__ == "__main__":
    with transaction() as connection:
        seed_qa_orgs(connection)
