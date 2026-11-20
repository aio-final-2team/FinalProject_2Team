"""T19 가상 원·계정·반·아이·상담실. 요청과 카드는 T27에서 채운다.

저장소 루트에서 PYTHONPATH=apps/api python -m db.seeds.demo 로 실행한다.
모의 seed의 고정 ID를 함께 쓰고, 이미 있는 행은 덮어쓰지 않는다.
출처 PR #262 roster_c4.json(가상): 별빛반 18명도 app.mock.seed에서 함께 읽는다.
"""

from argon2 import PasswordHasher
from sqlalchemy import text

from app.core.db import transaction
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
                VALUES (:child_id, :org_id, :user_id, 'other') ON CONFLICT DO NOTHING
            """), {"child_id": child["id"], "org_id": seed.ORG, "user_id": guardian})
    for room in seed.ROOMS:
        connection.execute(text("""
            INSERT INTO rooms (id, org_id, name) VALUES (:id, :org_id, :name) ON CONFLICT DO NOTHING
        """), {**room, "org_id": seed.ORG})


if __name__ == "__main__":
    with transaction() as connection:
        seed_demo(connection)
    print("가상 원 시드 완료: 계정 5개, 비밀번호 demo1234 (이미 있는 행은 유지)")
