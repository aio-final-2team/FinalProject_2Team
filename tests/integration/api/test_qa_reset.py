"""[TEST] QA 알림장 초기화의 범위·참조·재시작을 mock·임시 PG에서 대조해요."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from threading import Event
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from app import backend
from app.api.routes import qa_reset
from app.core import config
from app.core.db import transaction
from app.mock import seed, store
from app.mock.records import Approval, Evidence, Memory
from tests.integration.api.helpers import BASE, err
from tests.integration.api.test_daily_notes import batch, correction_body, sent_child_note
from tests.integration.api.test_resources import draft, note_list

PATH = BASE + "/qa/daily-notes/reset"
ZERO = dict.fromkeys(("inputs", "notes", "cards", "notifications", "events"), 0)


@pytest.fixture(autouse=True, params=["mock", "db"])
def reset_backend(request, monkeypatch, _reset_store):
    if request.param == "db":
        request.getfixturevalue("seeded_db")
        from app.core import users
        from app.modules.daily_notes import notes, reset
        from app.modules.requests import requests as request_actions
        from app.modules.daily_records import records as daily_records
    else:
        from app.mock import notes, qa_reset as reset, request_actions, daily_records
        users = store
    for name, module in dict(users=users, notes=notes, qa_reset=reset, request_actions=request_actions,
                             daily_records=daily_records).items():
        monkeypatch.setattr(backend, name, module)
    monkeypatch.setattr(qa_reset, "settings", replace(qa_reset.settings, qa_tools=True))
    return request.param


def reset(client, headers, **extra):
    return client.post(PATH, headers=headers, json={**batch(), **extra})


def rows(mode, table):
    if mode == "mock":
        value = getattr(store.state(), {"daily_note_inputs": "note_inputs", "daily_notes": "notes",
                                       "card_evidence": "evidence", "consultation_slots": "slots",
                                       "request_messages": "messages"}.get(table, table))
        result = [dict(r) if isinstance(r, dict) else vars(r).copy()
                  for r in (value.values() if isinstance(value, dict) else value)]
    else:
        with transaction() as connection:
            result = [dict(row) for row in connection.execute(text(f"SELECT * FROM {table}")).mappings()]
    return sorted(result, key=lambda row: str(row.get("id", (row.get("card_id"), row.get("chunk_id")))))


def test_disabled_hides_route_before_auth_role_and_body(client, parent, teacher, reset_backend, monkeypatch):
    monkeypatch.setattr(qa_reset, "settings", replace(qa_reset.settings, qa_tools=False))
    for headers in ({}, parent, teacher):
        for body in ({}, {"classroom_id": "bad", "extra": True}):
            err(client.post(PATH, headers=headers, json=body), 404, "NOT_FOUND")
        err(client.post(PATH, headers=headers, content="{"), 404, "NOT_FOUND")
    assert PATH in client.get("/openapi.json").json()["paths"]


def test_sent_notes_and_dependencies_reset_then_same_day_redraft(client, teacher, parent, reset_backend):
    note = sent_child_note(client, teacher)
    assert client.post(f"{BASE}/daily-notes/{note['id']}/correct", headers=teacher,
                       json=correction_body(note)).status_code == 200
    reply = client.post(f"{BASE}/daily-notes/{note['id']}/replies", headers=parent,
                        json={"body": "[TEST] 내일 준비물 문의"})
    assert reply.status_code == 202, reply.text
    rid = UUID(reply.json()["request_id"])
    record = client.post(f"{BASE}/classrooms/{seed.CLASS_STAR}/records", headers=teacher,
                         json={"child_id": str(seed.CHILD), "body": "[TEST] 남길 하루 기록"})
    assert record.status_code == 201, record.text
    card = next(c for c in rows(reset_backend, "cards") if c["subject_type"] == "daily_note_batch")
    cid = card["id"]
    if reset_backend == "mock":
        state = store.state()
        state.approvals.append(Approval(state.next_int(), cid, seed.ORG, 1, seed.TEACHER, "approve", store.now()))
        state.evidence.append(Evidence(cid, seed.ORG, next(iter(state.chunks)), 1, "[TEST] 근거"))
        memory = Memory(state.next_int(), seed.ORG, seed.TEACHER, "tone", "[TEST] 남길 기억", source_card_id=cid)
        state.memories[memory.id] = memory
    else:
        with transaction() as connection:
            connection.execute(text("""INSERT INTO approvals(org_id,card_id,card_version,decided_by,decision)
                VALUES (:org,:card,1,:actor,'approve')"""), {"org": seed.ORG, "card": cid, "actor": seed.TEACHER})
            connection.execute(text("""INSERT INTO card_evidence(org_id,card_id,chunk_id,rank,quote)
                SELECT :org,:card,id,1,'[TEST] 근거' FROM document_chunks LIMIT 1"""), {"org": seed.ORG, "card": cid})
            connection.execute(text("""INSERT INTO memories(org_id,owner_id,kind,content,source_card_id)
                VALUES (:org,:actor,'tone','[TEST] 남길 기억',:card)"""),
                               {"org": seed.ORG, "card": cid, "actor": seed.TEACHER})
    before = {table: rows(reset_backend, table) for table in ("daily_note_inputs", "daily_notes", "cards",
              "events", "notifications", "requests", "request_messages", "daily_records", "memories", "users")}
    note_ids = {n["id"] for n in before["daily_notes"]}
    expected = {"inputs": 1, "notes": 20, "cards": 1,
                "events": sum(e["daily_note_id"] in note_ids or e["card_id"] == cid for e in before["events"]),
                "notifications": sum(n["card_id"] == cid or (n["subject_type"] == "daily_note"
                                     and n["subject_id"] in note_ids) for n in before["notifications"])}
    assert expected["notifications"] > 0 and expected["events"] > 0
    assert {"note_sent", "note_corrected"} <= {n["kind"] for n in before["notifications"]}
    response = reset(client, teacher)
    assert response.status_code == 200, response.text
    assert response.json() == {**batch(), "deleted": expected, "unlinked_replies": 1}
    assert note_list(client, teacher).json()["items"] == []
    for table in ("daily_note_inputs", "daily_notes"):
        assert rows(reset_backend, table) == []
    assert rows(reset_backend, "requests") == [{**r, "source_note_id": None} if r["id"] == rid else r
                                               for r in before["requests"]]
    for table in ("users", "daily_records", "request_messages"):
        assert rows(reset_backend, table) == before[table]
    assert rows(reset_backend, "cards") == [c for c in before["cards"] if c["id"] != cid]
    assert rows(reset_backend, "memories") == [{**m, "source_card_id": None} if m["source_card_id"] == cid else m
                                               for m in before["memories"]]
    assert all(a["card_id"] != cid for a in rows(reset_backend, "approvals"))
    assert all(e["card_id"] != cid for e in rows(reset_backend, "card_evidence"))
    assert all(e["card_id"] != cid and e["daily_note_id"] not in note_ids for e in rows(reset_backend, "events"))
    assert rows(reset_backend, "notifications") == [n for n in before["notifications"]
        if n["card_id"] != cid and not (n["subject_type"] == "daily_note" and n["subject_id"] in note_ids)]
    detail = client.get(f"{BASE}/requests/{rid}", headers=parent)
    assert detail.status_code == 200 and detail.json()["request"]["source_note"] is None
    assert draft(client, teacher, activities="[TEST] 같은 날짜 재시험").status_code == 202
    assert len(note_list(client, teacher).json()["items"]) == 20
    assert note_ids.isdisjoint(n["id"] for n in rows(reset_backend, "daily_notes"))


def test_other_classroom_date_and_org_are_unchanged(client, teacher, teacher_other, reset_backend):
    yesterday = (store.now().date() - timedelta(days=1)).isoformat()
    for headers, extra in ((teacher, {}), (teacher, {"note_date": yesterday}),
                           (teacher_other, {"classroom_id": str(seed.CLASS_SUN)})):
        assert draft(client, headers, activities="[TEST] 삭제 범위 확인", **extra).status_code == 202
    foreign_org, foreign_class = uuid4(), uuid4()
    if reset_backend == "mock":
        store.state().classrooms[foreign_class] = store.Classroom(foreign_class, foreign_org, "[TEST] 다른 원")
    else:
        with transaction() as connection:
            connection.execute(text("INSERT INTO organizations(id,name) VALUES (:id,'[TEST] 다른 원')"), {"id": foreign_org})
            connection.execute(text("""INSERT INTO classrooms(id,org_id,name,school_year,age_group)
                VALUES (:id,:org,'[TEST] 다른 반',2026,4)"""),
                               {"id": foreign_class, "org": foreign_org})
    before = {table: rows(reset_backend, table) for table in ("daily_note_inputs", "daily_notes", "cards", "events", "notifications")}
    kept_inputs = {i["id"] for i in before["daily_note_inputs"]
                   if i["classroom_id"] != seed.CLASS_STAR or i["note_date"].isoformat() == yesterday}
    kept_notes = {n["id"] for n in before["daily_notes"] if n["input_id"] in kept_inputs}
    kept_cards = {c["id"] for c in before["cards"] if c["subject_id"] in kept_inputs}
    assert reset(client, teacher).status_code == 200
    assert all(i in rows(reset_backend, "daily_note_inputs") for i in before["daily_note_inputs"] if i["id"] in kept_inputs)
    assert all(n in rows(reset_backend, "daily_notes") for n in before["daily_notes"] if n["id"] in kept_notes)
    for table in ("cards", "events", "notifications"):
        assert all(r in rows(reset_backend, table) for r in before[table]
                   if r.get("card_id", r["id"]) in kept_cards or r.get("daily_note_id") in kept_notes)
    err(reset(client, teacher, classroom_id=str(foreign_class)), 404, "NOT_FOUND")


def test_roles_scope_and_director_without_consent(client, parent, teacher, teacher_other, director, reset_backend):
    from tests.integration.api.test_consents import expire

    assert draft(client, teacher, activities="[TEST] 권한 확인").status_code == 202
    before = rows(reset_backend, "daily_notes")
    err(reset(client, {}), 401, "UNAUTHENTICATED")
    err(reset(client, parent), 403, "FORBIDDEN_ROLE")
    err(reset(client, teacher_other), 404, "NOT_FOUND")
    err(reset(client, director, classroom_id=str(uuid4())), 404, "NOT_FOUND")
    assert rows(reset_backend, "daily_notes") == before
    expire(reset_backend, seed.DIRECTOR)
    response = reset(client, director)
    assert response.status_code == 200 and response.json()["deleted"]["notes"] == 20


def test_audit_uses_tool_called_without_deleted_foreign_keys(client, teacher, reset_backend):
    assert draft(client, teacher, activities="[TEST] 감사 기록").status_code == 202
    response = reset(client, teacher)
    assert response.status_code == 200, response.text
    audit = [e for e in rows(reset_backend, "events") if e["detail"].get("tool") == "qa_daily_note_reset"]
    assert len(audit) == 1
    event = audit[0]
    assert event["action"] == "tool_called" and event["actor_type"] == "user" and event["actor_id"] == seed.TEACHER
    assert event["org_id"] == seed.ORG and event["agent_name"] is None
    assert event["request_id"] is event["card_id"] is event["daily_note_id"] is None
    assert {k: v for k, v in event["detail"].items() if k != "trace_id"} == {
        "tool": "qa_daily_note_reset", **batch(), "deleted": response.json()["deleted"]}


def test_missing_target_is_idempotent_and_defaults_to_kst_today(client, teacher, reset_backend):
    for _ in range(2):
        response = client.post(PATH, headers=teacher, json={"classroom_id": str(seed.CLASS_STAR)})
        assert response.status_code == 200, response.text
        assert response.json() == {**batch(), "deleted": ZERO, "unlinked_replies": 0}


def test_input_and_env_validation(client, teacher, reset_backend, monkeypatch):
    for value in ("true", "1", "false", "0", "TRUE", "yes", ""):
        monkeypatch.setenv("QA_TOOLS", value)
        assert config.load_settings().qa_tools == (value in ("true", "1"))
    monkeypatch.delenv("QA_TOOLS")
    assert config.load_settings().qa_tools is False
    for body in ({}, {"classroom_id": "bad"}, {**batch(), "extra": True},
                 {**batch(), "note_date": "bad"}, {**batch(), "note_date": None}):
        err(client.post(PATH, headers=teacher, json=body), 422, "VALIDATION_FAILED")
    assert rows(reset_backend, "daily_note_inputs") == []


def test_runner_finishes_quietly_after_reset_during_writer(client, teacher, reset_backend, monkeypatch, caplog):
    if reset_backend == "mock":
        pytest.skip("mock은 동기 초안 생성이라 대기 중 runner가 없어요")
    from app.modules.daily_notes import runner, stub_writer

    for old_failure in (False, True):
        started, release = Event(), Event()

        def writer(payload, token):
            started.set()
            assert release.wait(20)
            if old_failure:
                raise RuntimeError("[TEST] 삭제 뒤 이전 writer 실패")
            return stub_writer.write(payload)

        monkeypatch.setattr(runner, "_write", writer)
        with ThreadPoolExecutor(max_workers=1) as pool:
            running = pool.submit(draft, client, teacher, activities="[TEST] 실행 중 초기화")
            try:
                assert started.wait(15)
                input_id = rows(reset_backend, "daily_note_inputs")[0]["id"]
                response = reset(client, teacher)
                assert response.status_code == 200 and response.json()["deleted"]["inputs"] == 1
            finally:
                release.set()
            assert running.result(timeout=15).status_code == 202
        runner.run_daily_note_drafts(input_id)
    assert rows(reset_backend, "daily_notes") == []
    assert rows(reset_backend, "daily_note_inputs") == []
    assert "알림장 초안 실패" not in caplog.text
