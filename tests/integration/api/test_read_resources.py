"""알림장 화면의 요청 출처·식단 자료 읽기를 두 백엔드에서 검사해요."""

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text

from app import backend
from app.core.db import transaction
from app.mock import documents, request_actions, seed, store
from app.mock.records import Approval, Evidence
from tests.integration.api.helpers import BASE, err


@pytest.fixture(autouse=True, params=["mock", "db"])
def read_backend(request, monkeypatch):
    if request.param == "db":
        request.getfixturevalue("seeded_db")
        from app.core import users
        from app.modules.documents import documents as db_documents
        from app.modules.requests import requests as db_requests
        modules = users, db_documents, db_requests
    else:
        modules = store, documents, request_actions
    for name, module in zip(("users", "documents", "request_actions"), modules, strict=True):
        monkeypatch.setattr(backend, name, module)
    return request.param


@pytest.mark.parametrize("request_id,request_type,body,actor", [
    (seed.REQUEST_COUGH, "inquiry", "기침해요", "teacher01"),
    (seed.REQUEST_COUGH, "inquiry", "기침해요", "director01"),
    (seed.REQUEST_COUGH, "inquiry", "기침해요", "parent01"),
    (seed.REQUEST_PICKUP, "pickup", "오늘 할머니가 데리러 가요", "teacher01"),
    (seed.demo_id("7214"), "inquiry", "요즘 기침을 조금 해요. 낮잠 때 잘 봐 주세요.", "teacher01"),
])
def test_seed_request_has_first_guardian_message(client, request_id, request_type, body, actor):
    token = client.post(BASE + "/auth/login", json={"login_id": actor, "password": "demo1234"}).json()["access_token"]
    response = client.get(f"{BASE}/requests/{request_id}", headers={"Authorization": "Bearer " + token})
    assert response.status_code == 200, response.text
    data = response.json()
    assert set(data) == {"request", "messages", "timeline", "consultation", "rejection", "sources"}
    req = data["request"]
    assert (req["id"], req["type"], req["title"], req["status"]) == (str(request_id), request_type, body, "received")
    assert req["missing_fields"] == [] and req["hold_until"] is None
    assert req["parent_confirmed_at"] is None
    assert all(req[key].endswith("+09:00") for key in ("created_at", "updated_at"))
    assert "risk_level" not in req and "assignee_id" not in req
    assert data["messages"][0]["sender_type"] == "user" and data["messages"][0]["body"] == body
    assert data["messages"][0]["created_at"].endswith("+09:00")
    assert isinstance(data["messages"][0]["id"], int) and data["messages"][0]["id"] > 0
    assert data["sources"] == []


def test_request_read_checks_auth_scope_and_uuid(client, teacher, teacher_other, parent_other):
    path = f"{BASE}/requests/{seed.REQUEST_COUGH}"
    err(client.get(path), 401, "UNAUTHENTICATED")
    for actor in (teacher_other, parent_other):
        err(client.get(path, headers=actor), 404, "NOT_FOUND")
    err(client.get(f"{BASE}/requests/{uuid4()}", headers=teacher), 404, "NOT_FOUND")
    err(client.get(BASE + "/requests/not-a-uuid", headers=teacher), 422, "VALIDATION_FAILED")


def test_request_reassignment_is_limited_to_that_request(client, teacher_other, read_backend):
    card_id = uuid4()
    if read_backend == "mock":
        store.state().cards[card_id] = store.Card(card_id, seed.ORG, seed.REQUEST_COUGH, "reply_draft",
                                                 assignee_id=seed.TEACHER_OTHER)
    else:
        with transaction() as connection:
            connection.execute(text("""
                INSERT INTO cards (id,org_id,request_id,kind,assignee_id)
                VALUES (:id,:org,:request,'reply_draft',:teacher)
            """), {"id": card_id, "org": seed.ORG, "request": seed.REQUEST_COUGH, "teacher": seed.TEACHER_OTHER})
    assert client.get(f"{BASE}/requests/{seed.REQUEST_COUGH}", headers=teacher_other).status_code == 200
    err(client.get(f"{BASE}/requests/{seed.REQUEST_PICKUP}", headers=teacher_other), 404, "NOT_FOUND")
    if read_backend == "mock":
        store.state().cards[card_id].assignee_id = seed.TEACHER
    else:
        with transaction() as connection:
            connection.execute(text("UPDATE cards SET assignee_id=:teacher WHERE id=:id"),
                               {"id": card_id, "teacher": seed.TEACHER})
    err(client.get(f"{BASE}/requests/{seed.REQUEST_COUGH}", headers=teacher_other), 404, "NOT_FOUND")


@pytest.mark.parametrize("status,approved,expected", [
    ("awaiting_review", True, False), ("sent_or_booked", False, False),
    ("sent_or_booked", True, True), ("completed", True, True),
])
def test_sources_require_sent_request_approval_and_parent_visibility(
        client, teacher, parent, read_backend, status, approved, expected):
    card_id = uuid4()
    if read_backend == "mock":
        store.state().requests[seed.REQUEST_COUGH].status = status
        store.state().documents[seed.NOTICE].visibility = "staff"
        store.state().cards[card_id] = store.Card(card_id, seed.ORG, seed.REQUEST_COUGH, "reply_draft",
                                                 assignee_id=seed.TEACHER)
        for rank, document_id in enumerate((seed.MENU, seed.NOTICE), 1):
            chunk = documents.chunks(store.state().documents[document_id])[0]
            store.state().evidence.append(Evidence(card_id, seed.ORG, chunk.id, rank, "[TEST] 근거"))
        if approved:
            store.state().approvals.append(Approval(store.state().next_int(), card_id, seed.ORG, 1,
                                                    seed.TEACHER, "approve", store.now()))
    else:
        with transaction() as connection:
            connection.execute(text("UPDATE requests SET status=:status WHERE id=:id"),
                               {"id": seed.REQUEST_COUGH, "status": status})
            connection.execute(text("UPDATE documents SET visibility='staff' WHERE id=:id"), {"id": seed.NOTICE})
            values = {"id": card_id, "org": seed.ORG, "request": seed.REQUEST_COUGH, "teacher": seed.TEACHER}
            connection.execute(text("""
                INSERT INTO cards (id,org_id,request_id,kind,assignee_id)
                VALUES (:id,:org,:request,'reply_draft',:teacher)
            """), values)
            for rank, document_id in enumerate((seed.MENU, seed.NOTICE), 1):
                connection.execute(text("""
                    INSERT INTO card_evidence (card_id,org_id,chunk_id,rank)
                    SELECT :id,:org,id,:rank FROM document_chunks WHERE document_id=:doc
                """), {**values, "doc": document_id, "rank": rank})
            if approved:
                connection.execute(text("""
                    INSERT INTO approvals (card_id,org_id,card_version,decided_by,decision)
                    VALUES (:id,:org,1,:teacher,'approve')
                """), values)
    for actor, titles in ((parent, ["가상 식단표"]), (teacher, ["가상 식단표", "가상 행사 안내"])):
        response = client.get(f"{BASE}/requests/{seed.REQUEST_COUGH}", headers=actor)
        assert response.status_code == 200, response.text
        sources = response.json()["sources"]
        assert [s["document_title"] for s in sources] == (titles if expected else [])
        assert all(set(s) == {"document_title", "location", "effective_from"} for s in sources)


def test_document_list_seed_pagination_sort_and_roles(client, teacher, director, parent):
    for actor in (teacher, director):
        listed = client.get(BASE + "/documents", headers=actor)
        assert listed.status_code == 200, listed.text
        data = listed.json()
        assert (data["total"], data["page"], data["size"]) == (3, 1, 20)
        menu = next(d for d in data["items"] if d["id"] == str(seed.MENU))
        assert (menu["title"], menu["doc_type"], menu["visibility"], menu["classroom_ids"]) == (
            "가상 식단표", "menu", "all", [])
        assert (menu["status"], menu["ingest_status"], menu["chunk_count"], menu["error"]) == (
            "active", "succeeded", 1, None)
        assert menu["effective_from"] and menu["effective_to"] is None
        assert menu["conflicts"] == [] and menu["supersedes_id"] is None
        assert any(d["status"] == "superseded" for d in data["items"])
        for sort in ("created_at", "-created_at"):
            pages = [client.get(BASE + "/documents", headers=actor,
                                params={"sort": sort, "size": 1, "page": page}).json() for page in range(1, 5)]
            assert all((p["total"], p["page"], p["size"]) == (3, i, 1) for i, p in enumerate(pages, 1))
            assert len({d["id"] for p in pages for d in p["items"]}) == 3
            ids = [d["id"] for p in pages for d in p["items"]]
            expected = [d["id"] for d in data["items"]]
            assert ids == (list(reversed(expected)) if sort == "created_at" else expected)
            assert pages[-1]["items"] == []
    err(client.get(BASE + "/documents", headers=parent), 403, "FORBIDDEN_ROLE")
    err(client.get(BASE + "/documents"), 401, "UNAUTHENTICATED")


@pytest.mark.parametrize("query", [{"page": 0}, {"size": 0}, {"size": 101}, {"sort": "title"}])
def test_document_list_validates_query(client, teacher, query):
    err(client.get(BASE + "/documents", headers=teacher, params=query), 422, "VALIDATION_FAILED")


def test_document_list_huge_page_is_empty(client, teacher):
    for page in (10**17, 10**30):
        response = client.get(BASE + "/documents", headers=teacher, params={"page": page, "size": 100})
        assert response.status_code == 200, response.text
        assert response.json() == {"items": [], "total": 3, "page": page, "size": 100}


def test_documents_filter_org_class_period_and_keep_staff_visibility(
        client, teacher, teacher_other, director, read_backend):
    other_org, other_doc = uuid4(), uuid4()
    today = store.now().date()
    if read_backend == "mock":
        state = store.state()
        state.document_classrooms[seed.MENU] = [seed.CLASS_STAR, seed.CLASS_SUN]
        state.document_classrooms[seed.NOTICE] = [seed.CLASS_SUN]
        state.documents[seed.MENU].visibility = "parents"
        state.documents[seed.NOTICE].visibility = "staff"
        foreign = store.Document(other_doc, other_org, "[TEST] 다른 원", "menu", "all", "foreign", today, store.now())
        state.documents[other_doc] = foreign
    else:
        with transaction() as connection:
            connection.execute(text("INSERT INTO organizations (id,name) VALUES (:org,'[TEST] 다른 원')"), {"org": other_org})
            connection.execute(text("""
                INSERT INTO documents (id,org_id,title,doc_type,source,content_sha256)
                VALUES (:doc,:org,'[TEST] 다른 원','menu','virtual','foreign')
            """), {"doc": other_doc, "org": other_org})
            for doc, classroom in ((seed.MENU, seed.CLASS_STAR), (seed.MENU, seed.CLASS_SUN),
                                    (seed.NOTICE, seed.CLASS_SUN)):
                connection.execute(text("""
                    INSERT INTO document_classrooms (document_id,org_id,classroom_id) VALUES (:doc,:org,:class)
                """), {"doc": doc, "org": seed.ORG, "class": classroom})
            connection.execute(text("UPDATE documents SET visibility='parents' WHERE id=:id"), {"id": seed.MENU})
            connection.execute(text("UPDATE documents SET visibility='staff' WHERE id=:id"), {"id": seed.NOTICE})
    for actor, expected in ((teacher, {seed.MENU, seed.OLD_NOTICE}),
                            (teacher_other, {seed.MENU, seed.NOTICE, seed.OLD_NOTICE}),
                            (director, {seed.MENU, seed.NOTICE, seed.OLD_NOTICE})):
        result = client.get(BASE + "/documents", headers=actor)
        assert result.status_code == 200, result.text
        data = result.json()
        assert {d["id"] for d in data["items"]} == {str(d) for d in expected}
        assert data["total"] == len(expected)
        menu = next(d for d in data["items"] if d["id"] == str(seed.MENU))
        assert set(menu["classroom_ids"]) == {str(seed.CLASS_STAR), str(seed.CLASS_SUN)}
        page = client.get(BASE + "/documents", headers=actor, params={"size": 1}).json()
        assert page["total"] == len(expected) and len(page["items"]) == 1
    # 배정 기간 밖이면 반 자료와 요청은 막고 원 전체 자료만 보여요.
    if read_backend == "mock":
        store.state().classroom_staff[0].valid_to = today - timedelta(days=1)
    else:
        with transaction() as connection:
            connection.execute(text("UPDATE classroom_staff SET valid_to=:until WHERE user_id=:id"),
                               {"until": today - timedelta(days=1), "id": seed.TEACHER})
    data = client.get(BASE + "/documents", headers=teacher).json()
    assert data["total"] == 1 and data["items"][0]["id"] == str(seed.OLD_NOTICE)
    err(client.get(f"{BASE}/requests/{seed.REQUEST_COUGH}", headers=teacher), 404, "NOT_FOUND")
