"""C1 DB 적재: 추출한 글의 저장·실패 이력·기존 충돌 검사를 확인한다."""

import pytest
from sqlalchemy import text

from app.core.constants import MAX_DOCUMENT_BYTES
from app.mock import seed
from tests.document_formats import archive_bytes, document_bytes, rejection_cases
from tests.integration.api.conftest import _login
from tests.integration.api.helpers import BASE, err
from tests.integration.api.test_resources import upload
from tests.integration.db.test_documents_t20 import WINTER_1226


@pytest.fixture
def teacher(db_client):
    return _login(db_client, "teacher01")


def test_document_upload_formats_store_text_and_dedupe(db_client, teacher, seeded_db):
    for suffix in ("pdf", "docx", "hwpx"):
        content = document_bytes(suffix)
        response = upload(db_client, teacher, "[TEST]." + suffix, content)
        doc = response.json()["document"]
        assert response.status_code == 202 and doc["ingest_status"] == "succeeded" and doc["error"] is None
        detail = db_client.get(f"{BASE}/documents/{doc['id']}", headers=teacher).json()["document"]
        with seeded_db.connect() as connection:
            stored = connection.scalars(text("SELECT content FROM document_chunks WHERE document_id=:id ORDER BY chunk_index"),
                                        {"id": doc["id"]}).all()
        assert stored == [c["content"] for c in detail["chunks"]]
        assert "[TEST] picnic supplies" in stored[0] and "not body text" not in stored[0]
        duplicate = upload(db_client, teacher, "again." + suffix, content)
        assert duplicate.status_code == 200 and duplicate.json()["document"]["id"] == doc["id"]
    parent = _login(db_client, "parent01")
    err(upload(db_client, parent, "[TEST].pdf", document_bytes("pdf")), 403, "FORBIDDEN_ROLE")
    err(upload(db_client, teacher, "[TEST].hwpx", document_bytes("hwpx"),
               **{"classroom_ids[]": str(seed.CLASS_SUN)}), 404, "NOT_FOUND")
    with seeded_db.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM events WHERE action='permission_denied'")) == 1


def test_document_upload_formats_failure_events(db_client, teacher, seeded_db):
    for filename, content, message in rejection_cases():
        response = upload(db_client, teacher, filename, content)
        doc = response.json()["document"]
        assert response.status_code == 202 and doc["ingest_status"] == "failed" and doc["chunk_count"] == 0
        assert doc["error"] == {"code": "UPSTREAM_UNAVAILABLE", "message": message}
        with seeded_db.connect() as connection:
            detail = connection.scalar(text("SELECT detail FROM events WHERE action='tool_failed' AND detail->>'document_id'=:id"),
                                       {"id": doc["id"]})
        assert {key: detail[key] for key in ("code", "message")} == doc["error"]


def test_document_upload_formats_archive_total_limit(db_client, teacher, seeded_db):
    for suffix in ("docx", "hwpx"):
        packed = archive_bytes({"one": b"a" * (MAX_DOCUMENT_BYTES // 2),
                                "two": b"b" * (MAX_DOCUMENT_BYTES // 2 + 1), "format": suffix})
        response = upload(db_client, teacher, "packed." + suffix, packed)
        doc = response.json()["document"]
        assert response.status_code == 202 and doc["ingest_status"] == "failed" and doc["chunk_count"] == 0
        assert doc["error"] == {"code": "UPSTREAM_UNAVAILABLE", "message": "자료 파일은 2MiB 이하여야 해요."}
    err(upload(db_client, teacher, "large.pdf", b"a" * (MAX_DOCUMENT_BYTES + 1)), 413, "VALIDATION_FAILED")
    with seeded_db.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM documents WHERE title='large.pdf'")) == 0


def test_document_upload_formats_reuse_conflict_parsing(db_client, teacher):
    old = upload(db_client, teacher, content="## 일정\n- 겨울방학: 2026년 12월 24일\n".encode()).json()["document"]
    content = document_bytes("hwpx", WINTER_1226)
    response = upload(db_client, teacher, "[TEST] 일정.hwpx", content)
    doc = response.json()["document"]
    assert response.status_code == 202 and doc["ingest_status"] == "succeeded"
    assert doc["status"] == "conflict_pending" and doc["supersedes_id"] is None
    assert doc["conflicts"][0]["label"] == "겨울방학" and doc["conflicts"][0]["location"] == "1쪽 겨울방학 기간"
    assert db_client.get(f"{BASE}/documents/{old['id']}", headers=teacher).json()["document"]["status"] == "active"
