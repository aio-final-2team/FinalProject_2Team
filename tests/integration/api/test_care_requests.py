"""T46 팀 확인 전 초안: 보호자 요청부터 실제 확인·완료와 알림장까지 두 모드로 검사해요."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from app import backend
from app.core.db import transaction
from app.mock import notes, notifications, request_actions, seed, store
from tests.integration.api.helpers import BASE, err


@pytest.fixture(autouse=True, params=["mock", "db"])
def care_backend(request, monkeypatch):
    if request.param == "db":
        request.getfixturevalue("seeded_db")
        from app.core import users
        from app.modules.daily_notes import notes as db_notes
        from app.modules.notifications import notifications as db_notifications
        from app.modules.requests import requests
        modules = users, requests, db_notes, db_notifications
    else:
        modules = store, request_actions, notes, notifications
    for name, module in zip(("users", "request_actions", "notes", "notifications"), modules, strict=True):
        monkeypatch.setattr(backend, name, module)
    return request.param


def create(client, parent, kind="medication", **extra):
    payload = {"client_request_id": str(uuid4()), "type": kind, "child_id": str(seed.CHILD),
               "body": "[TEST] 보호자가 적은 원문 2mL\n점심 뒤 1회"}
    if kind == "pickup":
        payload["pickup_guardian_id"] = str(seed.PARENT)
    return client.post(BASE + "/requests", headers=parent, json={**payload, **extra})


def decide(client, actor, rid, decision="confirm", **extra):
    return client.post(f"{BASE}/requests/{rid}/care-decisions", headers=actor,
                       json={"decision": decision, **extra})


def events(mode, rid):
    if mode == "mock":
        return [e.__dict__ for e in store.events_of(UUID(rid))]
    with transaction() as connection:
        return [dict(e) for e in connection.execute(text("SELECT * FROM events WHERE request_id=:id ORDER BY id"),
                                                   {"id": rid}).mappings()]


@pytest.mark.parametrize("kind", ["medication", "pickup"])
def test_care_requires_human_confirm_then_complete_and_keeps_original(client, parent, teacher, care_backend, kind):
    response = create(client, parent, kind, client_request_id="care-once-1234")
    assert response.status_code == 202, response.text
    rid = response.json()["request"]["id"]
    pickup = {"pickup_guardian_id": str(seed.PARENT)} if kind == "pickup" else {}
    assert create(client, parent, kind, client_request_id="care-once-1234").json()["request"]["id"] == rid
    initial = client.get(f"{BASE}/requests/{rid}", headers=parent).json()
    assert initial["request"]["status"] == "received" and initial["care"]["confirmed_at"] is None
    assert initial["messages"][0]["body"] == "[TEST] 보호자가 적은 원문 2mL\n점심 뒤 1회"
    assert len(initial["messages"]) == 1 and initial["sources"] == []
    stream = client.get(f"{BASE}/requests/{rid}/stream", headers=parent)
    assert "event: done" in stream.text and "event: stage" not in stream.text
    err(decide(client, teacher, rid, "complete", **pickup), 409, "INVALID_TRANSITION")
    err(decide(client, parent, rid, **pickup), 403, "FORBIDDEN_ROLE")
    confirmed = decide(client, teacher, rid, **pickup)
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["request"]["status"] == "assigned"
    assert confirmed.json()["care"]["confirmed_at"].endswith("+09:00")
    assert confirmed.json()["care"]["completed_at"] is None
    assert decide(client, teacher, rid, **pickup).json() == confirmed.json()
    complete = decide(client, teacher, rid, "complete", **pickup)
    assert complete.status_code == 200, complete.text
    assert complete.json()["request"]["status"] == "completed"
    assert complete.json()["care"]["completed_at"].endswith("+09:00")
    assert decide(client, teacher, rid, "complete", **pickup).json() == complete.json()
    err(decide(client, teacher, rid, **pickup), 409, "INVALID_TRANSITION")
    detail = client.get(f"{BASE}/requests/{rid}", headers=parent).json()
    assert detail["care"] == complete.json()["care"] and detail["messages"] == initial["messages"]
    audit = [e for e in events(care_backend, rid) if e["action"] != "permission_denied"]
    assert [e["action"] for e in audit] == ["created", "checked", "completed"]
    assert [(e["from_status"], e["to_status"]) for e in audit] == [
        (None, "received"), ("received", "assigned"), ("assigned", "completed")]
    assert all(e["actor_type"] == "user" and e["card_id"] is None for e in audit)
    # 완료 알림은 동일 요청당 한 번, 학부모에게 교직원 신원·보호자 원문을 더 싣지 않아요.
    items = client.get(BASE + "/notifications?size=100", headers=parent).json()["items"]
    own = [n for n in items if n["request_id"] == rid]
    assert [n["kind"] for n in own] == ["completed", "care_confirmed"]
    assert all("2mL" not in (n["body"] or "") for n in own)
    if care_backend == "mock":
        assert not store.cards_of(UUID(rid))
        requested = [n for n in store.state().notifications.values() if n.request_id == UUID(rid)]
    else:
        with transaction() as connection:
            assert connection.scalar(text("SELECT count(*) FROM cards WHERE request_id=:id"), {"id": rid}) == 0
            requested = [dict(n) for n in connection.execute(text("SELECT * FROM notifications WHERE request_id=:id"),
                                                            {"id": rid}).mappings()]
    requested = [n if isinstance(n, dict) else n.__dict__ for n in requested]
    assert len(requested) == 3 and len({n["dedupe_key"] for n in requested}) == 3
    staff_notice = next(n for n in requested if n["kind"] == "care_requested")
    assert str(staff_notice["recipient_id"]) == str(seed.TEACHER)


@pytest.mark.parametrize("kind,guardian", [("pickup", None), ("pickup", str(seed.PARENT_OTHER)),
                                           ("pickup", str(seed.TEACHER)), ("medication", str(seed.PARENT))])
def test_pickup_guardian_is_required_registered_and_only_for_pickup(client, parent, kind, guardian):
    err(create(client, parent, kind, pickup_guardian_id=guardian), 422, "VALIDATION_FAILED")


def test_pickup_rechecks_current_registration_and_matching_identity(client, parent, teacher, care_backend):
    rid = create(client, parent, "pickup").json()["request"]["id"]
    for guardian in (None, seed.PARENT_OTHER):
        err(decide(client, teacher, rid, pickup_guardian_id=str(guardian) if guardian else None), 422, "VALIDATION_FAILED")
    assert decide(client, teacher, rid, pickup_guardian_id=str(seed.PARENT)).status_code == 200
    # 등록 뒤 보호자 연결이 지워지면 실제 인계 완료를 기록하지 못해요.
    if care_backend == "mock":
        store.state().children[seed.CHILD].guardian_ids = []
    else:
        with transaction() as connection:
            connection.execute(text("DELETE FROM child_guardians WHERE child_id=:child AND user_id=:user"),
                               {"child": seed.CHILD, "user": seed.PARENT})
    err(decide(client, teacher, rid, "complete", pickup_guardian_id=str(seed.PARENT)), 422, "VALIDATION_FAILED")
    assert client.get(f"{BASE}/requests/{rid}", headers=teacher).json()["request"]["status"] == "assigned"


def test_care_scope_staff_queue_and_guardian_list(client, parent, parent_other, teacher, teacher_other, director):
    rid = create(client, parent).json()["request"]["id"]
    path = f"{BASE}/children/{seed.CHILD}/pickup-guardians"
    for actor in (parent, teacher, director):
        result = client.get(path, headers=actor)
        assert result.status_code == 200, result.text
        assert [g["id"] for g in result.json()["items"]] == [str(seed.PARENT)]
    for actor in (parent_other, teacher_other):
        err(client.get(path, headers=actor), 404, "NOT_FOUND")
        err(client.get(f"{BASE}/requests/{rid}", headers=actor), 404, "NOT_FOUND")
    err(decide(client, teacher_other, rid), 404, "NOT_FOUND")
    err(client.get(BASE + "/care-requests", headers=parent), 403, "FORBIDDEN_ROLE")
    for actor in (teacher, director):
        result = client.get(BASE + "/care-requests", headers=actor, params={"classroom_id": str(seed.CLASS_STAR)})
        assert result.status_code == 200, result.text
        assert rid in {r["id"] for r in result.json()["items"]}
        assert all(r["type"] in ("medication", "pickup") for r in result.json()["items"])
        assert client.get(BASE + "/care-requests", headers=actor, params={"page": 10**30}).json()["items"] == []
    err(client.get(BASE + "/care-requests", headers=teacher_other,
                   params={"classroom_id": str(seed.CLASS_STAR)}), 404, "NOT_FOUND")
    own = client.get(BASE + "/requests", headers=parent).json()
    assert rid in {r["id"] for r in own["items"]}
    assert decide(client, director, rid).status_code == 200
    assigned = client.get(BASE + "/care-requests?status=assigned", headers=teacher).json()
    assert assigned["total"] == 1 and assigned["items"][0]["next_action"] == "complete"


@pytest.mark.parametrize("kind", ["medication", "pickup"])
def test_note_lines_show_current_care_state_without_rewriting_draft(client, parent, teacher, care_backend, kind):
    rid = create(client, parent, kind).json()["request"]["id"]
    day = store.now().date().isoformat()
    draft = client.post(BASE + "/daily-notes/drafts", headers=teacher, json={
        "classroom_id": str(seed.CLASS_STAR), "note_date": day, "activities": "[TEST] 놀이", "supplies": "수건"})
    assert draft.status_code == 202, draft.text
    def note_line():
        result = client.get(BASE + "/daily-notes", headers=teacher,
                            params={"date": day, "classroom_id": str(seed.CLASS_STAR)})
        assert result.status_code == 200, result.text
        note = next(n for n in result.json()["items"] if n["child_id"] == str(seed.CHILD))
        return note, next(line for line in note["content"]["items"] if line["source"]["request_id"] == rid)
    original, line = note_line()
    assert line["key"] == kind and line["request_status"] == "received"
    before = line["value"]
    pickup = {"pickup_guardian_id": str(seed.PARENT)} if kind == "pickup" else {}
    for action, expected in (("confirm", "assigned"), ("complete", "completed")):
        assert decide(client, teacher, rid, action, **pickup).status_code == 200
        assert note_line()[1]["request_status"] == expected
        assert note_line()[1]["value"] == before
    # 알림장 확인·발송은 요청의 실제 완료를 대신하지 않아요. 읽기용 상태를 저장하지 않아요.
    result = client.patch(f"{BASE}/daily-notes/{original['id']}", headers=teacher,
                          json={"content": original["content"]})
    assert result.status_code == 200, result.text
    if care_backend == "mock":
        note = store.state().notes[UUID(original["id"])]
        assert all("request_status" not in i for i in note.content["items"])
        assert note.ai_original == note.content
    else:
        with transaction() as connection:
            row = connection.execute(text("SELECT content,ai_original FROM daily_notes WHERE id=:id"),
                                     {"id": original["id"]}).mappings().one()
            assert all("request_status" not in i for i in row["content"]["items"])
            assert row["content"] == row["ai_original"]


def test_non_care_and_seed_pickup_without_registered_id_cannot_be_fulfilled(client, teacher):
    err(decide(client, teacher, str(seed.REQUEST_COUGH)), 409, "INVALID_TRANSITION")
    err(decide(client, teacher, str(seed.REQUEST_PICKUP), pickup_guardian_id=str(seed.PARENT_OTHER)),
        422, "VALIDATION_FAILED")


def test_inactive_registered_guardian_is_hidden_and_rejected(client, parent, care_backend):
    if care_backend == "mock":
        child = store.state().children[seed.CHILD]
        child.guardian_ids = [*child.guardian_ids, seed.PARENT_OTHER]
        store.state().users[seed.PARENT_OTHER].is_active = False
    else:
        with transaction() as connection:
            connection.execute(text("""
                INSERT INTO child_guardians (org_id,child_id,user_id,relation) VALUES (:org,:child,:user,'other')
            """), {"org": seed.ORG, "child": seed.CHILD, "user": seed.PARENT_OTHER})
            connection.execute(text("UPDATE users SET is_active=false WHERE id=:id"), {"id": seed.PARENT_OTHER})
    rows = client.get(f"{BASE}/children/{seed.CHILD}/pickup-guardians", headers=parent).json()["items"]
    assert [r["id"] for r in rows] == [str(seed.PARENT)]
    err(create(client, parent, "pickup", pickup_guardian_id=str(seed.PARENT_OTHER)), 422, "VALIDATION_FAILED")


def test_expired_teacher_assignment_cannot_list_or_confirm_care(client, parent, teacher, care_backend):
    from datetime import timedelta

    rid = create(client, parent).json()["request"]["id"]
    yesterday = store.now().date() - timedelta(days=1)
    if care_backend == "mock":
        store.state().classroom_staff[0].valid_to = yesterday
    else:
        with transaction() as connection:
            connection.execute(text("UPDATE classroom_staff SET valid_to=:until WHERE user_id=:user"),
                               {"until": yesterday, "user": seed.TEACHER})
    assert client.get(BASE + "/care-requests", headers=teacher).json()["items"] == []
    err(decide(client, teacher, rid), 404, "NOT_FOUND")


def test_note_care_line_requires_matching_request_type_and_source(client, parent, teacher):
    rid = create(client, parent).json()["request"]["id"]
    day = store.now().date().isoformat()
    draft = client.post(BASE + "/daily-notes/drafts", headers=teacher, json={
        "classroom_id": str(seed.CLASS_STAR), "note_date": day, "activities": "[TEST] 놀이", "supplies": "수건"})
    assert draft.status_code == 202, draft.text
    note = next(n for n in client.get(BASE + "/daily-notes", headers=teacher,
                                    params={"date": day, "classroom_id": str(seed.CLASS_STAR)}).json()["items"]
                if n["child_id"] == str(seed.CHILD))
    for source in ({"type": "teacher_input"}, {"type": "request", "request_id": rid}):
        line = {"key": "pickup", "label": "[TEST] 귀가", "value": "[TEST] 잘못된 출처", "source": source}
        err(client.patch(f"{BASE}/daily-notes/{note['id']}", headers=teacher,
                         json={"content": {"items": [line]}}), 422, "VALIDATION_FAILED")
