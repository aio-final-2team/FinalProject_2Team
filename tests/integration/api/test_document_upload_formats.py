"""C1 모의 API도 실제 PDF·DOCX·HWPX에서 글을 꺼내고 같은 오류를 준다."""

from app.core.constants import MAX_DOCUMENT_BYTES
from app.mock import seed, store
from tests.document_formats import archive_bytes, document_bytes, rejection_cases
from tests.integration.api.helpers import BASE, err
from tests.integration.api.test_resources import upload


def test_document_upload_formats_extract_and_dedupe(client, teacher):
    for suffix in ("pdf", "docx", "hwpx"):
        content = document_bytes(suffix)
        response = upload(client, teacher, "[TEST]." + suffix.upper(), content)
        assert response.status_code == 202, response.text
        doc = response.json()["document"]
        assert doc["ingest_status"] == "succeeded" and doc["error"] is None
        detail = client.get(f"{BASE}/documents/{doc['id']}", headers=teacher).json()["document"]
        text = "\n".join(c["content"] for c in detail["chunks"])
        assert "[TEST] picnic supplies" in text and "not body text" not in text
        if suffix == "docx":
            assert text.index("picnic") < text.index("table supplies") < text.index("after table")
        if suffix == "hwpx":
            assert text.index("picnic") < text.index("section 2") < text.index("section 10")
        duplicate = upload(client, teacher, "duplicate." + suffix, content)
        assert duplicate.status_code == 200 and duplicate.json()["document"]["id"] == doc["id"]


def test_document_upload_formats_fail_without_replacing(client, teacher):
    old = upload(client, teacher).json()["document"]
    for filename, content, message in rejection_cases():
        response = upload(client, teacher, filename, content, replaces_document_id=old["id"])
        doc = response.json()["document"]
        assert response.status_code == 202 and doc["ingest_status"] == "failed"
        assert doc["chunk_count"] == 0 and doc["supersedes_id"] is None
        assert doc["error"] == {"code": "UPSTREAM_UNAVAILABLE", "message": message}
        assert client.get(f"{BASE}/documents/{old['id']}", headers=teacher).json()["document"]["status"] == "active"


def test_document_upload_formats_size_limits(client, teacher):
    for suffix in ("pdf", "docx", "hwpx"):
        err(upload(client, teacher, "large." + suffix, b"a" * (MAX_DOCUMENT_BYTES + 1)), 413, "VALIDATION_FAILED")
    for suffix in ("docx", "hwpx"):
        packed = archive_bytes({"one": b"a" * (MAX_DOCUMENT_BYTES // 2),
                                "two": b"b" * (MAX_DOCUMENT_BYTES // 2 + 1), "format": suffix})
        assert len(packed) < MAX_DOCUMENT_BYTES
        doc = upload(client, teacher, "packed." + suffix, packed).json()["document"]
        assert doc["ingest_status"] == "failed" and doc["chunk_count"] == 0
        assert doc["error"] == {"code": "UPSTREAM_UNAVAILABLE", "message": "자료 파일은 2MiB 이하여야 해요."}


def test_document_upload_formats_keep_role_and_class_scope(client, teacher, parent):
    for suffix in ("pdf", "docx", "hwpx"):
        content = document_bytes(suffix)
        err(upload(client, parent, "[TEST]." + suffix, content), 403, "FORBIDDEN_ROLE")
        err(upload(client, teacher, "[TEST]." + suffix, content,
                   **{"classroom_ids[]": str(seed.CLASS_SUN)}), 404, "NOT_FOUND")
    assert len([e for e in store.state().events if e.action == "permission_denied"]) == 3
