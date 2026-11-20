"""가상 원·계정·반·아이·상담실과 알림장용 식단·보호자 요청 22개.

저장소 루트에서 PYTHONPATH=apps/api python -m db.seeds.demo 로 실행한다.
모의 seed의 고정 ID를 함께 쓰고, 이미 있는 행은 덮어쓰지 않는다.
출처 PR #262 roster_c4.json(가상): 별빛반 18명도 app.mock.seed에서 함께 읽는다.
출처 PR #269 guardian_requests.json(가상): 20개 요청·16명 보호자도 같은 시드를 쓴다.
"""

from datetime import datetime

from argon2 import PasswordHasher
from sqlalchemy import text

from app.core.db import transaction
from app.core.schedule import KST
from app.mock import seed


def seed_demo(connection):
    connection.execute(text("""
        INSERT INTO organizations (id, name, is_virtual)
        VALUES (:id, '가상 햇살유치원', true) ON CONFLICT DO NOTHING
    """), {"id": seed.ORG})
    for classroom, age in zip(seed.CLASSROOMS, (4, 5), strict=True):
        connection.execute(text("""
            INSERT INTO classrooms (id, org_id, name, age_group, school_year)
            VALUES (:id, :org_id, :name, :age, 2026) ON CONFLICT DO NOTHING
        """), {**classroom, "org_id": seed.ORG, "age": age})
    password_hash = PasswordHasher().hash(seed.DEMO_PASSWORD)
    for user in seed.USERS:
        connection.execute(text("""
            INSERT INTO users (id, org_id, role, login_id, display_name, password_hash)
            VALUES (:id, :org_id, :role, :login_id, :display_name, :password_hash)
            ON CONFLICT DO NOTHING
        """), {**user, "org_id": seed.ORG, "password_hash": password_hash})
    for assignment in seed.CLASSROOM_STAFF:
        connection.execute(text("""
            INSERT INTO classroom_staff (classroom_id, org_id, user_id, valid_from, valid_to)
            VALUES (:classroom_id, :org_id, :user_id, :valid_from, :valid_to) ON CONFLICT DO NOTHING
        """), {**assignment, "org_id": seed.ORG})
    for child in seed.CHILDREN:
        connection.execute(text("""
            INSERT INTO children (id, org_id, classroom_id, display_name, is_virtual)
            VALUES (:id, :org_id, :classroom_id, :display_name, true) ON CONFLICT DO NOTHING
        """), {**child, "org_id": seed.ORG})
        for guardian in child["guardian_ids"]:
            connection.execute(text("""
                INSERT INTO child_guardians (child_id, org_id, user_id, relation)
                VALUES (:child_id, :org_id, :user_id, :relation) ON CONFLICT DO NOTHING
            """), {"child_id": child["id"], "org_id": seed.ORG, "user_id": guardian,
                   "relation": seed.GUARDIAN_RELATIONS.get((child["id"], guardian), "other")})
    for room in seed.ROOMS:
        connection.execute(text("""
            INSERT INTO rooms (id, org_id, name) VALUES (:id, :org_id, :name) ON CONFLICT DO NOTHING
        """), {**room, "org_id": seed.ORG})
    for document_id, title, kind, status, content in seed.DEMO_DOCUMENTS:
        connection.execute(text("""
            INSERT INTO documents (id,org_id,title,doc_type,source,status,ingest_status,content_sha256)
            VALUES (:id,:org,:title,:kind,'virtual',:status,'succeeded',:sha) ON CONFLICT DO NOTHING
        """), {"id": document_id, "org": seed.ORG, "title": title, "kind": kind,
               "status": status, "sha": f"demo:{document_id}"})
        connection.execute(text("""
            INSERT INTO document_chunks (document_id,org_id,chunk_index,content)
            VALUES (:id,:org,0,:content) ON CONFLICT DO NOTHING
        """), {"id": document_id, "org": seed.ORG, "content": content})
    for request in seed.DEMO_NOTE_REQUESTS:
        connection.execute(text("""
            INSERT INTO requests (id,org_id,classroom_id,child_id,requester_id,client_request_id,type,body,created_at)
            VALUES (:id,:org,:class,:child_id,:requester_id,:key,:type,:body,:now) ON CONFLICT DO NOTHING
        """), {**request, "org": seed.ORG, "class": seed.CLASS_STAR, "key": f"demo:{request['id']}",
               "now": request.get("created_at", datetime.now(KST))})


if __name__ == "__main__":
    with transaction() as connection:
        seed_demo(connection)
    print(f"가상 원 시드 완료: 계정 {len(seed.USERS)}개, 비밀번호 demo1234 (이미 있는 행은 유지)")
