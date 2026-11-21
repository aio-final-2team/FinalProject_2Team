"""새 읽기 API의 DB 원본 메시지·기존 시드 보완·적재 실패 표시를 검사해요."""

from datetime import datetime

import pytest
from sqlalchemy import text

from app.mock import seed
from db.seeds.demo import seed_demo


@pytest.fixture
def teacher(db_client):
    response = db_client.post("/api/v1/auth/login", json={"login_id": "teacher01", "password": "demo1234"})
    assert response.status_code == 200, response.text
    return {"Authorization": "Bearer " + response.json()["access_token"]}


def test_request_detail_reads_full_conversation_without_mutation(db_client, teacher, seeded_db):
    at = datetime.fromisoformat("2026-11-19T15:30:00+00:00")
    with seeded_db.begin() as connection:
        values = {"org": seed.ORG, "id": seed.REQUEST_COUGH, "teacher": seed.TEACHER, "parent": seed.PARENT}
        assert connection.scalar(text("SHOW TimeZone")) == "Asia/Seoul"
        connection.execute(text("UPDATE requests SET type='complaint',created_at=:at,parent_confirmed_at=:at WHERE id=:id"),
                           {**values, "at": at})
        connection.execute(text("UPDATE request_messages SET created_at=:at WHERE request_id=:id"),
                           {**values, "at": at})
        connection.execute(text("""
            INSERT INTO request_messages (org_id,request_id,sender_type,sender_id,body)
            VALUES (:org,:id,'user',:teacher,'[TEST] 교직원'),
                   (:org,:id,'agent',NULL,'[TEST] 공개 대화'),
                   (:org,:id,'user',:parent,'[TEST] 보호자 추가 대화')
        """), values)
        before = connection.scalar(text("SELECT count(*) FROM events"))
    for _ in range(2):
        response = db_client.get(f"/api/v1/requests/{seed.REQUEST_COUGH}", headers=teacher)
        assert response.status_code == 200, response.text
        data = response.json()
        assert [msg["body"] for msg in data["messages"]] == ["기침해요", "[TEST] 교직원", "[TEST] 공개 대화", "[TEST] 보호자 추가 대화"]
        for value in (data["request"]["created_at"], data["request"]["parent_confirmed_at"],
                      data["messages"][0]["created_at"]):
            assert value == "2026-11-20T00:30:00+09:00"
            assert datetime.fromisoformat(value) == at
        assert data["request"]["updated_at"].endswith("+09:00")
        assert (data["timeline"], data["consultation"], data["rejection"]) == ([], None, None)
    with seeded_db.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM events")) == before


def test_seed_backfills_legacy_request_once_and_preserves_existing_content(seeded_db):
    with seeded_db.begin() as connection:
        connection.execute(text("DELETE FROM request_messages WHERE request_id=:id"), {"id": seed.REQUEST_COUGH})
        connection.execute(text("UPDATE requests SET title=NULL WHERE id=:id"), {"id": seed.REQUEST_COUGH})
        connection.execute(text("UPDATE requests SET title='[TEST] 교사가 고친 제목' WHERE id=:id"),
                           {"id": seed.REQUEST_PICKUP})
        seed_demo(connection)
        seed_demo(connection)
        assert connection.scalar(text("SELECT title FROM requests WHERE id=:id"), {"id": seed.REQUEST_COUGH}) == "기침해요"
        assert connection.scalar(text("SELECT title FROM requests WHERE id=:id"), {"id": seed.REQUEST_PICKUP}) == "[TEST] 교사가 고친 제목"
        messages = connection.execute(text("SELECT * FROM request_messages WHERE request_id=:id"),
                                      {"id": seed.REQUEST_COUGH}).mappings().all()
        assert len(messages) == 1 and messages[0]["body"] == "기침해요"
        assert connection.scalar(text("SELECT count(*) FROM request_messages")) == len(seed.DEMO_NOTE_REQUESTS)


def test_document_list_keeps_failure_details_and_defaults_missing_date(db_client, teacher, seeded_db):
    created_at = datetime.fromisoformat("2026-11-19T23:30:00+00:00")
    with seeded_db.begin() as connection:
        connection.execute(text("UPDATE documents SET ingest_status='failed',created_at=:at WHERE id=:id"),
                           {"id": seed.MENU, "at": created_at})
        connection.execute(text("""
            INSERT INTO events (org_id,actor_type,action,detail) VALUES (:org,'system','tool_failed',
              jsonb_build_object('document_id',CAST(:id AS text),'code','UPSTREAM_UNAVAILABLE',
                                 'message','[TEST] 자료 적재 실패','private','[TEST] 내부값'))
        """), {"org": seed.ORG, "id": seed.MENU})
    response = db_client.get("/api/v1/documents", headers=teacher)
    assert response.status_code == 200, response.text
    menu = next(d for d in response.json()["items"] if d["id"] == str(seed.MENU))
    assert menu["ingest_status"] == "failed" and menu["effective_from"] == "2026-11-20"
    assert menu["error"] == {"code": "UPSTREAM_UNAVAILABLE", "message": "[TEST] 자료 적재 실패"}


def test_medication_staff_read_does_not_process_request(db_client, teacher, seeded_db):
    with seeded_db.connect() as connection:
        before = {table: connection.scalar(text(f"SELECT count(*) FROM {table}"))
                  for table in ("cards", "events", "notifications")}
    response = db_client.get(f"/api/v1/requests/{seed.demo_id('7201')}", headers=teacher)
    assert response.status_code == 200, response.text
    assert response.json()["request"]["status"] == "received"
    with seeded_db.connect() as connection:
        assert {table: connection.scalar(text(f"SELECT count(*) FROM {table}")) for table in before} == before
        assert connection.scalar(text("SELECT status FROM requests WHERE id=:id"), {"id": seed.demo_id('7201')}) == "received"
