"""[TEST] QA 원의 격리·재시드·트랜잭션과 안전한 진단 계약."""

import secrets
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from uuid import uuid4

import pytest
from fastapi import Depends
from sqlalchemy import text

from app import backend
from app.api.routes import qa_reset, qa_sandbox
from app.core import config, media, request_id, users
from app.core.auth import current_user
from app.core.db import transaction
from app.core.qa_orgs import QA_ORGS, qa_id
from app.main import app
from app.mock import seed, store
from app.modules.daily_notes import notes
from app.modules.requests import requests
from app.modules.consents import consents
from db.seeds import qa_orgs
from db.seeds.demo import seed_demo
from db.seeds.documents import seed_documents
from db.seeds.memories import seed_memories
from db.seeds.care_notes import seed_care_notes
from db.seeds.consultations import seed_consultations
from db.seeds.daily_records import seed_daily_records

BASE = "/api/v1"
RESET = BASE + "/qa/sandbox/reset"


@pytest.fixture
def qa_db(seeded_db, monkeypatch, tmp_path):
    settings = replace(config.settings, data_backend="db", qa_tools=True,
                       qa_password=secrets.token_urlsafe(20), media_dir=str(tmp_path))
    for module in (qa_sandbox, qa_reset, qa_orgs, request_id, media):
        monkeypatch.setattr(module, "settings", settings)
    for name, module in dict(users=users, notes=notes, request_actions=requests, consents=consents).items():
        monkeypatch.setattr(backend, name, module)
    with transaction() as connection:
        for seeder in (seed_documents, seed_memories, seed_care_notes, seed_consultations, seed_daily_records):
            seeder(connection)
        qa_orgs.seed_qa_orgs(connection)
    return settings


def login(client, tag="sj", role="teacher01"):
    response = client.post(BASE + "/auth/login", json={"login_id": f"{tag}.{role}" if tag else role,
        "password": qa_sandbox.settings.qa_password if tag else seed.DEMO_PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": "Bearer " + response.json()["access_token"]}


def snapshot(org):
    with transaction() as connection:
        return {table: sorted([dict(row) for row in connection.execute(text(f"SELECT * FROM {table} WHERE org_id=:org"),
                {"org": org}).mappings()], key=lambda row: str(sorted(row.items()))) for table in qa_orgs.DELETE_ORDER}


def create(client, headers, tag="sj", trace=None):
    return client.post(BASE + "/requests", headers={**headers, **({"X-Request-ID": trace} if trace else {})},
        json={"client_request_id": str(uuid4()), "type": "inquiry", "body": "[TEST] QA 원 문의",
              "child_id": str(qa_id(tag, seed.CHILD) if tag else seed.CHILD)})


def test_five_orgs_match_seed_and_second_boot_preserves_edits(qa_db):
    with transaction() as connection:
        actual = set(connection.scalars(text("""SELECT c.table_name FROM information_schema.columns c
            JOIN information_schema.tables t USING(table_catalog,table_schema,table_name)
            WHERE c.table_schema='public' AND c.column_name='org_id' AND t.table_type='BASE TABLE'""")))
        assert set(qa_orgs.DELETE_ORDER) == actual
    demo = snapshot(seed.ORG)
    for org in QA_ORGS:
        current = snapshot(qa_id(org["tag"], seed.ORG))
        assert {t: len(rows) for t, rows in current.items()} == {t: len(rows) for t, rows in demo.items()}
        assert {u["display_name"] for u in current["users"]} == {u["display_name"] for u in demo["users"]}
    with transaction() as connection:
        connection.execute(text("UPDATE children SET display_name='[TEST] 유지' WHERE id=:id"),
                           {"id": qa_id("sj", seed.CHILD)})
    before = snapshot(qa_id("sj", seed.ORG))
    with transaction() as connection:
        qa_orgs.seed_qa_orgs(connection)
        assert connection.scalar(text("SELECT count(*) FROM organizations")) == 6
    assert snapshot(qa_id("sj", seed.ORG)) == before
    assert snapshot(seed.ORG) == demo


def test_login_sees_own_children_and_rejects_other_orgs(client, qa_db):
    headers = login(client)
    own = client.get(f"{BASE}/classrooms/{qa_id('sj', seed.CLASS_STAR)}/children", headers=headers)
    assert own.status_code == 200 and str(qa_id("sj", seed.CHILD)) in own.text
    for org, classroom, request in ((seed.ORG, seed.CLASS_STAR, seed.REQUEST_COUGH),
            (qa_id("ym", seed.ORG), qa_id("ym", seed.CLASS_STAR), qa_id("ym", seed.REQUEST_COUGH))):
        assert client.get(f"{BASE}/classrooms/{classroom}/children", headers=headers).status_code == 404
        assert client.get(f"{BASE}/requests/{request}", headers=headers).status_code == 404


def test_reset_restores_all_tables_and_keeps_other_org_rows_and_token(client, qa_db):
    headers, parent = login(client), login(client, role="parent01")
    org = qa_id("sj", seed.ORG)
    initial = snapshot(org)
    assert create(client, parent).status_code == 202
    response = client.post(BASE + "/daily-notes/drafts", headers=headers,
        json={"classroom_id": str(qa_id("sj", seed.CLASS_STAR)), "note_date": store.now().date().isoformat(),
              "activities": "[TEST] 산책", "supplies": "[TEST] 수건"})
    assert response.status_code == 202, response.text
    before = snapshot(org)
    others = {o: snapshot(o) for o in (seed.ORG, qa_id("ym", seed.ORG))}
    response = client.post(RESET, headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["org_name"] == "QA 성주 원"
    assert body["deleted"] == {table: len(rows) for table, rows in before.items()}
    assert body["seeded"] == {table: len(initial[table]) for table in ("users", "children", "documents")}
    after = snapshot(org)
    assert {t: len(r) for t, r in after.items()} == {t: len(r) + (t == "events") for t, r in initial.items()}
    for table in initial:
        assert {r["id"] for r in initial[table] if "id" in r} <= {r["id"] for r in after[table] if "id" in r}
    audits = [e for e in after["events"] if e["detail"].get("tool") == "qa_sandbox_reset"]
    assert len(audits) == 1 and audits[0]["detail"]["deleted"] == body["deleted"]
    assert audits[0]["actor_id"] == qa_id("sj", seed.TEACHER)
    assert {o: snapshot(o) for o in others} == others
    assert client.get(f"{BASE}/classrooms/{qa_id('sj', seed.CLASS_STAR)}/children", headers=headers).status_code == 200
    assert client.post(RESET, headers=parent).status_code == 200


def test_reset_failure_rolls_back_all_deletions(client, qa_db, monkeypatch):
    headers = login(client)
    before = snapshot(qa_id("sj", seed.ORG))
    def fail(*args):
        raise RuntimeError("[TEST] seed failure")
    monkeypatch.setattr(qa_orgs, "populate", fail)
    assert client.post(RESET, headers=headers).status_code == 500
    assert snapshot(qa_id("sj", seed.ORG)) == before


def test_concurrent_resets_are_serialized(client, qa_db):
    headers = login(client)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: client.post(RESET, headers=headers), range(2)))
    assert [r.status_code for r in responses] == [200, 200]
    assert len([e for e in snapshot(qa_id("sj", seed.ORG))["events"]
                if e["detail"].get("tool") == "qa_sandbox_reset"]) == 1


def test_demo_and_disabled_and_unauthenticated_reset_are_hidden(client, qa_db, monkeypatch):
    assert client.post(RESET, headers=login(client, tag="")).status_code == 404
    assert client.post(RESET).status_code == 401
    monkeypatch.setattr(qa_reset, "settings", replace(qa_db, qa_tools=False))
    for path in (RESET, BASE + "/qa/traces/a", BASE + "/qa/info"):
        response = client.post(path, content="{") if path == RESET else client.get(path)
        assert response.status_code == 404 and response.json()["error"]["code"] == "NOT_FOUND"


def test_document_vectors_are_copied_and_photos_have_separate_real_files(qa_db):
    vector = "[" + ",".join(["0.5"] * 1024) + "]"
    missing_demo_photo = media.path(f"{seed.FEED_PHOTOS[0][0]}.jpg")
    missing_demo_photo.unlink(missing_ok=True)
    with transaction() as connection:
        connection.execute(text("UPDATE document_chunks SET embedding=CAST(:v AS vector),embedding_model='[TEST]' "
                                "WHERE org_id=:org"), {"v": vector, "org": seed.ORG})
        source = qa_orgs.template(connection)
        assert not missing_demo_photo.exists()
        assert all(r["embedding"] == vector for r in source["document_chunks"])
        connection.execute(text("UPDATE document_chunks SET embedding=NULL WHERE org_id=:org"),
                           {"org": qa_id("sj", seed.ORG)})
    # reset 경로도 같은 template 벡터를 쓰고, 기존 사진 파일은 원별로 남겨요.
    with transaction() as connection:
        org = QA_ORGS[0]
        for table in qa_orgs.DELETE_ORDER:
            connection.execute(text(f"DELETE FROM {table} WHERE org_id=:org"), {"org": qa_id("sj", seed.ORG)})
        qa_orgs.populate(connection, org, source)
        assert connection.scalar(text("SELECT bool_and(embedding::text=:v) FROM document_chunks WHERE org_id=:org"),
                                 {"org": qa_id("sj", seed.ORG), "v": vector})
    photos = snapshot(qa_id("sj", seed.ORG))["feed_photos"]
    demo_paths = {p["storage_path"] for p in snapshot(seed.ORG)["feed_photos"]}
    assert len(photos) == 5
    for photo in photos:
        assert photo["storage_path"] not in demo_paths and media.path(photo["storage_path"]).is_file()
        assert photo["storage_path"].startswith(str(photo["id"]))


def test_request_trace_is_scoped_to_org(client, qa_db):
    trace = str(uuid4())
    response = create(client, login(client, role="parent01"), trace=trace)
    assert response.status_code == 202 and response.headers["X-Request-ID"] == trace
    own = client.get(f"{BASE}/qa/traces/{trace}", headers=login(client)).json()
    assert own["events"] and own["errors"] == []
    times = [e["created_at"] for e in own["events"]]
    assert times == sorted(times)
    assert client.get(f"{BASE}/qa/traces/{trace}", headers=login(client, "ym")).json()["events"] == []


@pytest.mark.parametrize("mode", ["mock", "db"])
def test_error_trace_is_safe_and_bounded_and_scoped(client, monkeypatch, request, mode):
    if mode == "db":
        request.getfixturevalue("qa_db")
        headers = login(client)
    else:
        monkeypatch.setattr(qa_reset, "settings", replace(config.settings, qa_tools=True))
        monkeypatch.setattr(qa_sandbox, "settings", replace(config.settings, qa_tools=True, data_backend="mock"))
        monkeypatch.setattr(request_id, "settings", replace(config.settings, qa_tools=True))
        headers = login(client, "")
    request_id.qa_errors.clear()
    def explode(user=Depends(current_user)):
        raise RuntimeError("[TEST] private input must stay out of response")
    route_count = len(app.router.routes)
    app.add_api_route("/_qa_test_error", explode, methods=["GET"])
    try:
        trace = str(uuid4())
        failed = client.get("/_qa_test_error", headers={**headers, "X-Request-ID": trace})
        assert failed.status_code == 500
        response = client.get(f"{BASE}/qa/traces/{trace}", headers=headers)
        assert response.status_code == 200 and len(response.json()["errors"]) == 1
        error = response.json()["errors"][0]
        assert error["status"] == 500 and error["error_type"] == "RuntimeError" and ":" in error["where"]
        assert "private input" not in failed.text + response.text + repr(request_id.qa_errors)
        if mode == "db":
            assert client.get(f"{BASE}/qa/traces/{trace}", headers=login(client, "ym")).json()["errors"] == []
        for _ in range(501):
            request_id.qa_errors.append(dict(request_id.qa_errors[-1]))
        assert len(request_id.qa_errors) == 500
        monkeypatch.setattr(request_id, "settings", replace(request_id.settings, qa_tools=False))
        before = list(request_id.qa_errors)
        client.get("/_qa_test_error", headers=headers)
        assert list(request_id.qa_errors) == before
    finally:
        del app.router.routes[route_count:]
        request_id.qa_errors.clear()


def test_mock_reset_empty_trace_validation_and_info(client, teacher, parent, monkeypatch):
    for module in (qa_reset, qa_sandbox):
        monkeypatch.setattr(module, "settings", replace(config.settings, qa_tools=True, data_backend="mock"))
    assert client.post(RESET, headers=teacher).status_code == 404
    trace = client.get(BASE + "/qa/traces/missing", headers=teacher)
    assert trace.status_code == 200 and trace.json() == {"trace_id": "missing", "events": [], "errors": []}
    assert client.get(BASE + "/qa/traces/" + "x" * 129, headers=teacher).status_code == 422
    assert client.get(BASE + "/qa/traces/missing").status_code == 401
    assert create(client, parent, tag="", trace="mock-live").status_code == 202
    assert client.get(BASE + "/qa/traces/mock-live", headers=teacher).json()["events"]
    assert client.get(BASE + "/qa/info").json()["migration"] is None


def test_info_is_public_allowlisted_and_reports_deployment(client, qa_db, monkeypatch):
    monkeypatch.setenv("GIT_SHA", "[TEST] abc123")
    monkeypatch.setenv("DEPLOYED_AT", "2026-11-27T12:00:00+09:00")
    response = client.get(BASE + "/qa/info")
    assert response.status_code == 200
    info = response.json()
    assert info["commit"] == "[TEST] abc123" and info["migration"] == "0020"
    assert info["deployed_at"] == "2026-11-27T12:00:00+09:00" and info["data_backend"] == "db"
    assert info["qa_orgs"] == list(QA_ORGS)
    assert not any(word in response.text.lower() for word in ("password", "secret", "key", "postgresql"))


def test_info_with_token_names_my_org_and_classrooms_for_console(client, qa_db):
    mine = client.get(BASE + "/qa/info", headers=login(client)).json()["me"]
    assert mine["role"] == "teacher" and mine["org_name"] == "QA 성주 원"
    assert {(c["id"], c["name"]) for c in mine["classrooms"]} == {
        (str(qa_id("sj", seed.CLASS_STAR)), "만 4세 별빛반"), (str(qa_id("sj", seed.CLASS_SUN)), "만 5세 햇님반")}
    # 틀린 토큰은 오류 대신 me=null이고, 다른 원 반은 섞이지 않아요.
    assert client.get(BASE + "/qa/info", headers={"Authorization": "Bearer [TEST] bad"}).json()["me"] is None
    ym = client.get(BASE + "/qa/info", headers=login(client, tag="ym")).json()["me"]
    assert str(qa_id("sj", seed.CLASS_STAR)) not in {c["id"] for c in ym["classrooms"]}


def test_console_page_only_on_qa_server(client, qa_db, monkeypatch):
    page = client.get(BASE + "/qa/console")
    assert page.status_code == 200 and page.headers["content-type"].startswith("text/html")
    assert "유치온 QA 도구" in page.text and "/qa/sandbox/reset" in page.text
    assert "/qa/console" not in client.get("/openapi.json").json()["paths"]
    off = replace(qa_db, qa_tools=False)
    for module in (qa_sandbox, qa_reset):
        monkeypatch.setattr(module, "settings", off)
    assert client.get(BASE + "/qa/console").status_code == 404

def test_empty_password_or_disabled_seed_leaves_demo_intact(seeded_db, monkeypatch):
    before = snapshot(seed.ORG)
    for enabled, password in ((True, ""), (False, secrets.token_urlsafe(20))):
        monkeypatch.setenv("QA_PASSWORD", password)
        assert config.load_settings().qa_password == password
        monkeypatch.setattr(qa_orgs, "settings", replace(config.settings, qa_tools=enabled, qa_password=password))
        with transaction() as connection:
            qa_orgs.seed_qa_orgs(connection)
            assert connection.scalar(text("SELECT count(*) FROM organizations")) == 1
        assert snapshot(seed.ORG) == before
        with transaction() as connection:
            seed_demo(connection)
        assert snapshot(seed.ORG) == before
