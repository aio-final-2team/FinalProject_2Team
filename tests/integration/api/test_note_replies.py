"""알림장 답장·준비물 확인을 같은 HTTP로 mock·시험 PG에 대조해요."""

from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from app import backend
from app.core.auth import issue_token
from app.core.db import transaction
from app.mock import seed, store
from tests.integration.api.helpers import BASE, err, decision
from tests.integration.api.test_daily_notes import (
    note_backend as note_backend, note_flow_backend as note_flow_backend, sent_child_note)
from tests.integration.api.test_requests import _create, audit, reply_card
from tests.integration.api.test_resources import draft, note_list


@pytest.fixture(autouse=True)
def replies_backend(note_flow_backend, monkeypatch):
    if note_flow_backend == "db":
        from app.modules.cards import cards
        from app.modules.consents import consents
    else:
        from app.mock import cards, consents
    monkeypatch.setattr(backend, "cards", cards)
    monkeypatch.setattr(backend, "consents", consents)
    return note_flow_backend


def post(client, headers, note, endpoint="replies", **kwargs):
    return client.post(f"{BASE}/daily-notes/{note['id']}/{endpoint}", headers=headers,
                       json={"body": "[TEST] 내일 준비물은 무엇인가요?"}, **kwargs)


def counts(mode):
    if mode == "mock":
        state = store.state()
        return (*(len(getattr(state, k)) for k in ("requests", "messages", "cards", "notifications")),
                sum(e.action == "permission_denied" for e in state.events))
    with transaction() as connection:
        return (*(connection.scalar(text(f"SELECT count(*) FROM {table}"))
                  for table in ("requests", "request_messages", "cards", "notifications")),
                connection.scalar(text("SELECT count(*) FROM events WHERE action='permission_denied'")))


def test_note_replies_reuse_create_and_follow_card_approval(client, teacher, parent, replies_backend, monkeypatch):
    note = sent_child_note(client, teacher)
    before = note.copy()
    assert note["replies"] == [] and note["supplies_checked_at"] is None
    original = backend.request_actions.create
    calls = []

    def traced_create(user, **values):
        calls.append(values)
        return original(user, **values)

    monkeypatch.setattr(backend.request_actions, "create", traced_create)
    response = post(client, {**parent, "X-Request-ID": "[TEST]-note-reply"}, note)
    assert response.status_code == 202, response.text
    rid = response.json()["request_id"]
    assert set(response.json()) == {"request_id"}
    assert len(calls) == 1 and calls[0]["type"] == "inquiry"
    assert calls[0]["source_note_id"] == UUID(note["id"]) and calls[0]["child_id"] == seed.CHILD
    source = {"note_id": note["id"], "note_date": note["note_date"]}
    detail = client.get(f"{BASE}/requests/{rid}", headers=parent).json()
    assert detail["request"]["source_note"] == source and detail["request"]["type"] == "inquiry"
    assert detail["messages"][0]["body"] == calls[0]["body"]
    assert audit(replies_backend, rid, "created")[0]["detail"]["trace_id"] == "[TEST]-note-reply"
    card = reply_card(replies_backend, rid)
    assert client.get(f"{BASE}/cards/{card['id']}", headers=teacher).json()["request"]["source_note"] == source
    if replies_backend == "mock":
        notices = [n for n in store.state().notifications.values() if str(n.request_id) == rid]
    else:
        with transaction() as connection:
            notices = connection.execute(text("SELECT * FROM notifications WHERE request_id=:id"), {"id": rid}).all()
    assert notices
    approved = decision(client, teacher, card["id"], "edit_approve", card["version"],
                        edited_content={"text": "[TEST] 내일 준비물은 수건이에요."})
    assert approved.status_code == 200, approved.text
    second = post(client, parent, note).json()["request_id"]
    items = client.get(BASE + "/daily-notes", headers=parent, params={"date": note["note_date"]}).json()["items"]
    assert len(items) == 1
    replies = items[0]["replies"]
    assert [r["request_id"] for r in replies] == [rid, second]
    assert replies[0]["status"] == approved.json()["request"]["status"] == "sent_or_booked"
    assert replies[0]["created_at"]
    assert set(replies[0]) == {"request_id", "body", "status", "created_at"}
    assert {k: v for k, v in items[0].items() if k != "replies"} == {k: v for k, v in before.items() if k != "replies"}
    ordinary = _create(client, parent, type="inquiry").json()["request"]["id"]
    assert client.get(f"{BASE}/requests/{ordinary}", headers=parent).json()["request"]["source_note"] is None
    plain_card = reply_card(replies_backend, ordinary)
    assert client.get(f"{BASE}/cards/{plain_card['id']}", headers=teacher).json()["request"]["source_note"] is None


@pytest.mark.parametrize("endpoint", ["replies", "supplies-check"])
def test_note_replies_guardian_role_scope_and_denial_log(client, teacher, teacher_other, director, parent_other, replies_backend, endpoint):
    note = sent_child_note(client, teacher)
    before = counts(replies_backend)
    err(post(client, {}, note, endpoint), 401, "UNAUTHENTICATED")
    for headers in (teacher, teacher_other, director):
        err(post(client, headers, note, endpoint), 403, "FORBIDDEN_ROLE")
    for target in (note, {"id": str(uuid4())}):
        err(post(client, parent_other, target, endpoint), 404, "NOT_FOUND")
    after = counts(replies_backend)
    assert after[:4] == before[:4] and after[4] == before[4] + 2
    foreign, other = uuid4(), uuid4()
    if replies_backend == "mock":
        store.state().users[other] = store.User(other, foreign, "parent", "test-foreign", "test", "[TEST] 보호자")
    else:
        with transaction() as connection:
            connection.execute(text("INSERT INTO organizations(id,name) VALUES (:id,'[TEST] 다른 원')"), {"id": foreign})
            connection.execute(text("""INSERT INTO users(id,org_id,role,login_id,display_name,password_hash)
                VALUES (:id,:org,'parent','test-foreign','[TEST] 보호자','test')"""), {"id": other, "org": foreign})
    foreign_headers = {"Authorization": "Bearer " + issue_token(backend.users.get_user(other))}
    err(post(client, foreign_headers, note, endpoint), 404, "NOT_FOUND")
    assert counts(replies_backend)[4] == after[4] + 1
    if replies_backend == "mock":
        store.state().children[seed.CHILD].guardian_ids.append(seed.PARENT_OTHER)
    else:
        with transaction() as connection:
            connection.execute(text("INSERT INTO child_guardians(org_id,child_id,user_id,relation) VALUES (:org,:child,:user,'other')"),
                               {"org": seed.ORG, "child": seed.CHILD, "user": seed.PARENT_OTHER})
    assert post(client, parent_other, note, endpoint).status_code == (202 if endpoint == "replies" else 200)


@pytest.mark.parametrize("endpoint", ["replies", "supplies-check"])
@pytest.mark.parametrize("status", ["draft", "needs_check", "ready"])
def test_note_replies_unsent_is_hidden_and_unchanged(client, teacher, parent, replies_backend, endpoint, status):
    assert draft(client, teacher).status_code == 202
    note = next(n for n in note_list(client, teacher).json()["items"] if n["child_id"] == str(seed.CHILD))
    assert client.patch(f"{BASE}/daily-notes/{note['id']}", headers=teacher, json={
        "resolved_checks": [c["id"] for c in note["open_checks"]], "confirm": True}).status_code == 200
    if replies_backend == "mock":
        store.state().notes[UUID(note["id"])].status = status
    else:
        with transaction() as connection:
            connection.execute(text("UPDATE daily_notes SET status=:status WHERE id=:id"), {"id": note["id"], "status": status})
    before = counts(replies_backend)
    err(post(client, parent, note, endpoint), 404, "NOT_FOUND")
    after = counts(replies_backend)
    assert after[:4] == before[:4] and after[4] == before[4] + 1


def test_note_replies_validate_body_and_inherit_consent_gate(client, teacher, parent, replies_backend):
    from tests.integration.api.test_consents import expire

    note = sent_child_note(client, teacher)
    before = counts(replies_backend)
    for body in ({}, {"body": ""}, {"body": "x" * 2001}):
        err(client.post(f"{BASE}/daily-notes/{note['id']}/replies", headers=parent, json=body), 422, "VALIDATION_FAILED")
    expire(replies_backend, seed.PARENT)
    err(post(client, parent, note), 403, "CONSENT_REQUIRED")
    assert counts(replies_backend) == before


def test_supplies_check_preserves_first_timestamp_and_is_visible_to_all_roles(client, teacher, director, parent, replies_backend):
    note = sent_child_note(client, teacher)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: post(client, parent, note, "supplies-check"), range(2)))
    assert all(r.status_code == 200 for r in responses)
    first = responses[0].json()
    assert first["supplies_checked_at"] and all(r.json() == first for r in responses)
    assert client.post(f"{BASE}/daily-notes/{note['id']}/supplies-check", headers=parent).json() == first
    for headers in (parent, teacher, director):
        response = client.get(BASE + "/daily-notes", headers=headers,
                              params={"classroom_id": str(seed.CLASS_STAR), "date": note["note_date"]})
        assert response.status_code == 200, response.text
        result = response.json()
        saved = next(n for n in result["items"] if n["id"] == note["id"])
        assert saved == {**note, **first}


@pytest.mark.parametrize("value", [None, "", "   "])
def test_supplies_check_rejects_missing_or_empty_line(client, teacher, parent, replies_backend, value):
    note = sent_child_note(client, teacher)
    items = [line for line in note["content"]["items"] if line["key"] != "supplies"]
    if value is not None:
        items.append({"key": "supplies", "label": "준비물", "value": value, "source": {"type": "teacher_input"}})
    response = client.post(f"{BASE}/daily-notes/{note['id']}/correct", headers=teacher,
                           json={"version": note["version"], "content": {"items": items}, "reason_text": "[TEST] 준비물 없음"})
    assert response.status_code == 200, response.text
    err(post(client, parent, note, "supplies-check"), 409, "INVALID_TRANSITION")
    assert next(n for n in note_list(client, teacher).json()["items"] if n["id"] == note["id"])["supplies_checked_at"] is None
