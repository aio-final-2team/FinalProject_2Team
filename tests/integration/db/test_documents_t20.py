"""T20 자료 창고(DB): 원 자료 적재, 낱말 검색, 자료 올리기·충돌 표시·새 판·실패를 검사해요."""

from datetime import date
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from app.core.errors import ApiError
from app.mock import seed
from app.modules.documents.search import search_documents
from db.seeds.documents import seed_documents

WINTER_1226 = """---
title: "겨울방학 일정 다시 알림"
doc_type: notice
kindergarten_id: KG-DEMO-01
classroom: "전체"
classroom_keys: []
effective_from: 2026-11-23
visibility: all
source: uploaded
is_virtual: true
---

# 겨울방학 일정 다시 알림

## 1쪽 겨울방학 기간
- 겨울방학: 2026년 12월 26일(토) ~ 2027년 1월 3일(일)
"""


@pytest.fixture
def docs(seeded_db):
    with seeded_db.begin() as connection:
        result = seed_documents(connection)
    return result


@pytest.fixture
def teacher(db_client):
    response = db_client.post("/api/v1/auth/login", json={"login_id": "teacher01", "password": "demo1234"})
    assert response.status_code == 200, response.text
    return {"Authorization": "Bearer " + response.json()["access_token"]}


def staff():
    return SimpleNamespace(id=seed.TEACHER, org_id=seed.ORG, role="teacher")


def parent():
    return SimpleNamespace(id=seed.PARENT, org_id=seed.ORG, role="parent")


def upload(client, headers, name, content, **extra):
    data = {"doc_type": "notice", "visibility": "all", "effective_from": "2026-11-23", **extra}
    return client.post("/api/v1/documents", headers=headers, data=data,
                       files={"file": (name, content.encode("utf-8"), "text/markdown")})


def test_fixture_documents_load_with_locations_and_classrooms(seeded_db, docs):
    assert len(docs["added"]) == 29 and docs["skipped"] == ["NT-2026-31"]  # C3(새싹반)은 시드에 없음
    with seeded_db.begin() as connection:
        assert seed_documents(connection)["added"] == []  # 다시 해도 같은 내용은 건너뜀
        row = connection.execute(text("""
            SELECT d.title, ch.location, ARRAY(SELECT classroom_id FROM document_classrooms dc
                                               WHERE dc.document_id=d.id) AS classes
            FROM documents d JOIN document_chunks ch ON ch.document_id=d.id
            WHERE d.title='김장 체험 안내 (만 4·5세반)' AND ch.chunk_index=1
        """)).mappings().one()
    assert row["location"] == "1쪽 준비물" and set(row["classes"]) == {seed.CLASS_STAR, seed.CLASS_SUN}


def test_search_finds_winter_break_with_location_and_date(docs):
    found = search_documents(staff(), str(seed.ORG), "notice", "겨울방학은 언제부터인가요?",
                             on_date=date(2026, 11, 20))["chunks"]
    top = found[0]
    assert top["document_title"] == "겨울방학 안내" and top["location"] == "1쪽 겨울방학 기간"
    assert top["effective_from"] == date(2026, 11, 2) and "12월 24일" in top["content"] and 0 < top["score"] <= 1
    schedule = search_documents(staff(), str(seed.ORG), "schedule", "겨울방학", on_date=date(2026, 11, 20))["chunks"]
    assert any("12-26" in c["content"] or "12월 26일" in c["content"] for c in schedule)  # 충돌 상대는 학사 일정에


def test_search_scope_for_parent_class_and_other_org(docs):
    sun_only = search_documents(parent(), str(seed.ORG), "notice", "현장체험학습 도시락",
                                classroom_id=seed.CLASS_STAR, on_date=date(2026, 11, 20))["chunks"]
    assert all(c["document_title"] != "11월 현장체험학습 안내 (만 5세반)" for c in sun_only)  # 별빛반 아이는 햇님반 자료 못 봄
    sun = search_documents(parent(), str(seed.ORG), "notice", "현장체험학습 도시락",
                           classroom_id=seed.CLASS_SUN, on_date=date(2026, 11, 20))["chunks"]
    assert sun[0]["document_title"] == "11월 현장체험학습 안내 (만 5세반)"
    with pytest.raises(ApiError) as error:
        search_documents(staff(), "00000000-0000-4000-8000-00000000ffff", "notice", "겨울방학")
    assert error.value.status == 404
    with pytest.raises(ApiError):
        search_documents(staff(), str(seed.ORG), "law", "겨울방학")  # 도구 doc_type은 네 가지만
    future = search_documents(staff(), str(seed.ORG), "notice", "크리스마스", on_date=date(2026, 11, 20))["chunks"]
    assert future == []  # 시행일(12/01) 전 자료는 아직 찾지 않음


def test_upload_conflicting_notice_is_pending_with_conflicts(db_client, teacher, docs):
    response = upload(db_client, teacher, "겨울방학_다시알림.md", WINTER_1226)
    assert response.status_code == 202, response.text
    doc = response.json()["document"]
    assert doc["ingest_status"] == "succeeded" and doc["status"] == "conflict_pending" and doc["chunk_count"] == 1
    conflict = next(c for c in doc["conflicts"] if c["other_document_title"] == "겨울방학 안내")
    assert conflict["kind"] == "date" and conflict["location"] == "1쪽 겨울방학 기간"
    detail = db_client.get(f"/api/v1/documents/{doc['id']}", headers=teacher).json()["document"]
    assert detail["conflicts"] == doc["conflicts"]
    again = upload(db_client, teacher, "겨울방학_다시알림.md", WINTER_1226)
    assert again.status_code == 200 and again.json()["document"]["id"] == doc["id"]  # 같은 내용은 새로 만들지 않음
    hits = search_documents(staff(), str(seed.ORG), "notice", "겨울방학", on_date=date(2026, 11, 30))["chunks"]
    assert all(c["document_title"] != "겨울방학 일정 다시 알림" for c in hits)  # 확인 대기 문서는 검색에 안 나옴


def test_upload_plain_text_new_version_supersedes_old(db_client, teacher, seeded_db, docs):
    first = upload(db_client, teacher, "가정통신_준비물.txt", "## 준비물\n- 실내화: 이름 쓰기\n").json()["document"]
    assert first["status"] == "active" and first["conflicts"] == [] and first["chunk_count"] == 1
    second = upload(db_client, teacher, "가정통신_준비물_2판.txt", "## 준비물\n- 실내화: 이름 쓰기, 가방에 넣기\n",
                    replaces_document_id=first["id"]).json()["document"]
    assert second["status"] == "active" and second["supersedes_id"] == first["id"]
    old = db_client.get(f"/api/v1/documents/{first['id']}", headers=teacher).json()["document"]
    assert old["status"] == "superseded"


def test_upload_unreadable_file_fails_with_message(db_client, teacher, docs):
    response = upload(db_client, teacher, "식단표.hwp", "binary")
    doc = response.json()["document"]
    assert response.status_code == 202 and doc["ingest_status"] == "failed" and doc["chunk_count"] == 0
    assert doc["error"] == {"code": "UPSTREAM_UNAVAILABLE", "message": "지금은 .md·.txt 글 파일만 읽을 수 있어요"}


def test_teacher_cannot_target_or_read_other_class_document(db_client, teacher, seeded_db, docs):
    response = upload(db_client, teacher, "햇님반.md", "## 안내\n- 소풍: 12월 1일\n", **{"classroom_ids[]": str(seed.CLASS_SUN)})
    assert response.status_code == 404  # teacher01은 별빛반 담임
    with seeded_db.begin() as connection:
        sun_doc = connection.scalar(text("SELECT id FROM documents WHERE title='만 5세반 12월 주간 활동 계획'"))
    assert db_client.get(f"/api/v1/documents/{sun_doc}", headers=teacher).status_code == 404
