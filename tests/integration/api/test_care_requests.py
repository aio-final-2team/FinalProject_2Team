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
    detail = client.get(f"{BASE}/requests/{rid}", headers=actor).json()
    version = (detail.get("care") or {}).get("version", 1)
    return client.post(f"{BASE}/requests/{rid}/care-decisions", headers=actor,
                       json={"decision": decision, "version": version, **extra})


def events(mode, rid):
    if mode == "mock":
        return [e.__dict__ for e in store.events_of(UUID(rid))]
    with transaction() as connection:
        return [dict(e) for e in connection.execute(text("SELECT * FROM events WHERE request_id=:id ORDER BY id"),
                                                   {"id": rid}).mappings()]


@pytest.mark.parametrize("kind,fields", [
    ("medication", {"medication_name": "[TEST] 시럽", "medication_dose": "2.5mL", "medication_time": "점심 뒤"}),
    ("pickup", {"pickup_guardian_id": None, "pickup_name": "[TEST] 할머니", "pickup_relation": "할머니"}),
    ("pickup", {"pickup_guardian_id": str(seed.PARENT)}),
])
def test_care_values_live_on_request_and_receipt_only_names_fields(client, parent, teacher, care_backend, kind, fields):
    key = str(uuid4())
    response = create(client, parent, kind, client_request_id=key, **fields)
    assert response.status_code == 202, response.text
    rid = response.json()["request"]["id"]
    detail = client.get(f"{BASE}/requests/{rid}", headers=teacher).json()["care"]
    names = ("medication_name", "medication_dose", "medication_time") if kind == "medication" else (
        "pickup_guardian_id", "pickup_name", "pickup_relation")
    expected = {name: detail[name] for name in names}
    assert all(detail[name] == value for name, value in fields.items())
    if kind == "pickup" and fields["pickup_guardian_id"]:
        assert detail["pickup_name"] and detail["pickup_relation"]
    if care_backend == "mock":
        stored = store.state().requests[UUID(rid)].care_detail
    else:
        with transaction() as connection:
            stored = connection.scalar(text("SELECT care_detail FROM requests WHERE id=:id"), {"id": rid})
    assert stored == expected
    receipt = next(e for e in events(care_backend, rid) if e["action"] == "created" and e["to_status"] == "received")
    assert set(receipt["detail"]) == {"trace_id", "fields"}
    assert set(receipt["detail"]["fields"]) == set(expected)
    # 같은 접수 키의 재전송은 구조화 값·이력도 처음 것 그대로 둔다.
    repeated = create(client, parent, kind, client_request_id=key, **fields)
    assert repeated.status_code == 200 and repeated.json()["request"]["id"] == rid
    assert len(events(care_backend, rid)) == 1
    assert client.get(f"{BASE}/requests/{rid}", headers=parent).json()["care"] == detail


def test_care_list_includes_current_child_identity(client, parent, teacher, director, care_backend):
    rid = create(client, parent).json()["request"]["id"]
    if care_backend == "mock":
        store.state().children[seed.CHILD].display_name = "[TEST] 바뀐 아이 이름"
    else:
        with transaction() as connection:
            connection.execute(text("UPDATE children SET display_name='[TEST] 바뀐 아이 이름' WHERE id=:id"),
                               {"id": seed.CHILD})
    for actor in (teacher, director):
        result = client.get(BASE + "/care-requests?size=100", headers=actor)
        assert result.status_code == 200, result.text
        item = next(r for r in result.json()["items"] if r["id"] == rid)
        assert item["child_id"] == str(seed.CHILD) and item["child_name"] == "[TEST] 바뀐 아이 이름"


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


@pytest.mark.parametrize("kind,guardian", [("pickup", str(seed.PARENT_OTHER)),
                                           ("pickup", str(seed.TEACHER)), ("medication", str(seed.PARENT))])
def test_explicit_guardian_id_must_belong_to_child_and_only_for_pickup(client, parent, kind, guardian):
    err(create(client, parent, kind, pickup_guardian_id=guardian), 422, "VALIDATION_FAILED")


def test_pickup_rechecks_current_registration_and_matching_identity(client, parent, teacher, care_backend):
    rid = create(client, parent, "pickup").json()["request"]["id"]
    for guardian in (None, seed.PARENT_OTHER):
        err(decide(client, teacher, rid, pickup_guardian_id=str(guardian) if guardian else None), 422, "VALIDATION_FAILED")
    assert decide(client, teacher, rid, pickup_guardian_id=str(seed.PARENT)).status_code == 200
    # 확인 뒤 연결이 지워져도 확인 당시 인계자로 실제 완료를 기록해요.
    if care_backend == "mock":
        store.state().children[seed.CHILD].guardian_ids = []
    else:
        with transaction() as connection:
            connection.execute(text("DELETE FROM child_guardians WHERE child_id=:child AND user_id=:user"),
                               {"child": seed.CHILD, "user": seed.PARENT})
    completed = decide(client, teacher, rid, "complete", pickup_guardian_id=str(seed.PARENT))
    assert completed.status_code == 200, completed.text
    assert completed.json()["request"]["status"] == "completed"


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
    assert line["value"] == "[TEST] 보호자가 적은 원문 2mL\n점심 뒤 1회"
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


def test_non_care_rejected_but_seed_grandmother_pickup_can_be_confirmed(client, teacher):
    err(decide(client, teacher, str(seed.REQUEST_COUGH)), 409, "INVALID_TRANSITION")
    before = client.get(f"{BASE}/requests/{seed.REQUEST_PICKUP}", headers=teacher).json()
    assert before["messages"][0]["body"] == "오늘 할머니가 데리러 가요"
    assert before["care"]["unregistered_pickup"] is True
    result = decide(client, teacher, str(seed.REQUEST_PICKUP))
    assert result.status_code == 200, result.text
    assert result.json()["care"]["confirmed_at"] is not None


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


def notices(mode, rid):
    if mode == "mock":
        return [n.__dict__ for n in store.state().notifications.values() if str(n.request_id) == str(rid)]
    with transaction() as connection:
        return [dict(n) for n in connection.execute(text("SELECT * FROM notifications WHERE request_id=:id ORDER BY id"),
                                                   {"id": rid}).mappings()]


def test_unregistered_pickup_is_marked_and_director_notified_once(client, parent, teacher, care_backend):
    result = create(client, parent, "pickup", pickup_guardian_id=None, pickup_name="[TEST] 할머니",
                    pickup_relation="할머니")
    assert result.status_code == 202, result.text
    rid = result.json()["request"]["id"]
    detail = client.get(f"{BASE}/requests/{rid}", headers=teacher).json()
    assert detail["care"]["pickup_name"] == "[TEST] 할머니"
    assert detail["care"]["pickup_relation"] == "할머니"
    assert detail["care"]["unregistered_pickup"] is True
    queue = client.get(BASE + "/care-requests?size=100", headers=teacher).json()["items"]
    item = next(r for r in queue if r["id"] == rid)
    assert item["unregistered_pickup"] and item["version"] == 1 and item["next_action"] == "confirm"
    for _ in range(2):
        assert decide(client, teacher, rid).status_code == 200
    warnings = [e for e in events(care_backend, rid) if e["detail"].get("unregistered_pickup")]
    assert len(warnings) == 1 and warnings[0]["detail"]["label"] == "미등록 인계자 확인"
    assert str(warnings[0]["actor_id"]) == str(seed.TEACHER)
    director_notices = [n for n in notices(care_backend, rid) if str(n["recipient_id"]) == str(seed.DIRECTOR)]
    assert len(director_notices) == 1 and director_notices[0]["body"] == "미등록 인계자 확인"
    assert decide(client, teacher, rid, "complete").status_code == 200


@pytest.mark.parametrize("identity", [{}, {"pickup_name": "[TEST] 김영희", "pickup_relation": "할머니"}])
def test_unregistered_pickup_reconfirmation_keeps_one_director_notice(client, parent, teacher, care_backend, identity):
    rid = create(client, parent, "pickup", pickup_guardian_id=None, **identity).json()["request"]["id"]
    for version in range(1, 4):
        confirmed = decide(client, teacher, rid)
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["care"]["version"] == version
        assert decide(client, teacher, rid).json() == confirmed.json()
        if version < 3:
            correction = client.post(f"{BASE}/requests/{rid}/messages", headers=parent,
                                     json={"body": "[TEST] 귀가 시간만 정정해요. 인계자는 같아요."})
            assert correction.status_code == 201, correction.text
    warnings = [e for e in events(care_backend, rid) if e["detail"].get("unregistered_pickup")]
    assert [e["detail"]["version"] for e in warnings] == [1, 2, 3]
    rows = notices(care_backend, rid)
    director_notices = [n for n in rows if str(n["recipient_id"]) == str(seed.DIRECTOR)]
    assert len(director_notices) == 1 and director_notices[0]["body"] == "미등록 인계자 확인"
    assert len([n for n in rows if n["kind"] == "care_confirmed"]) == 3
    assert len([n for n in rows if n["body"] == "보호자가 내용을 추가했어요. 다시 확인해 주세요."]) == 2


@pytest.mark.parametrize("changed", [{"pickup_name": "[TEST] 이영희"}, {"pickup_relation": "이모"}])
def test_unregistered_pickup_notice_distinguishes_identity_and_request(client, parent, teacher, care_backend, changed):
    identity = {"pickup_guardian_id": None, "pickup_name": "[TEST] 김영희", "pickup_relation": "할머니"}
    rid = create(client, parent, "pickup", **identity).json()["request"]["id"]
    assert decide(client, teacher, rid).status_code == 200
    # 인계자 수정 HTTP는 없어요. 확인 이력→알림 경계에 바뀐 신원을 주입해 키를 검증해요.
    for snapshot in ({**identity, **changed}, {**identity, **changed}, identity):
        detail = {"unregistered_pickup": True, "pickup_snapshot": snapshot}
        if care_backend == "mock":
            with store._lock:
                store.add_event(store.state().requests[UUID(rid)], "checked", **detail)
        else:
            from app.modules.requests.events import record
            with transaction() as connection:
                req = connection.execute(text("SELECT * FROM requests WHERE id=:id FOR NO KEY UPDATE"),
                                         {"id": rid}).mappings().one()
                record(connection, req, "checked", **detail)
    director_notices = [n for n in notices(care_backend, rid) if str(n["recipient_id"]) == str(seed.DIRECTOR)]
    assert len(director_notices) == 2
    assert all(n["body"] == "미등록 인계자 확인" for n in director_notices)
    other = create(client, parent, "pickup", **identity).json()["request"]["id"]
    assert decide(client, teacher, other).status_code == 200
    other_notices = [n for n in notices(care_backend, other) if str(n["recipient_id"]) == str(seed.DIRECTOR)]
    assert len(other_notices) == 1
    assert other_notices[0]["dedupe_key"] not in {n["dedupe_key"] for n in director_notices}


@pytest.mark.parametrize("fields,missing", [({}, ["medication_name", "medication_dose", "medication_time"]),
    ({"medication_name": "[TEST] 약", "medication_dose": "  "}, ["medication_dose", "medication_time"]),
    ({"medication_name": "[TEST] 약", "medication_dose": "2.5mL", "medication_time": "점심 뒤"}, [])])
def test_medication_missing_values_are_shown_without_guessing(client, parent, teacher, fields, missing):
    result = create(client, parent, **fields)
    assert result.status_code == 202, result.text
    rid = result.json()["request"]["id"]
    detail = client.get(f"{BASE}/requests/{rid}", headers=teacher).json()
    assert detail["request"]["missing_fields"] == detail["care"]["missing_fields"] == missing
    assert detail["care"]["medication_time"] == fields.get("medication_time")
    item = next(r for r in client.get(BASE + "/care-requests?size=100", headers=teacher).json()["items"] if r["id"] == rid)
    assert item["missing_fields"] == missing
    assert decide(client, teacher, rid).status_code == 200


@pytest.mark.parametrize("kind", ["medication", "pickup"])
def test_parent_correction_clears_confirmation_and_rejects_seen_old_version(client, parent, teacher, care_backend, kind):
    rid = create(client, parent, kind).json()["request"]["id"]
    pickup = {"pickup_guardian_id": str(seed.PARENT)} if kind == "pickup" else {}
    confirmed = decide(client, teacher, rid, **pickup)
    assert confirmed.status_code == 200, confirmed.text
    count = len(notices(care_backend, rid))
    posted = client.post(f"{BASE}/requests/{rid}/messages", headers=parent,
                         json={"body": "[TEST] 정정: 5mL 말고 2.5mL예요. 취소할게요."})
    assert posted.status_code == 201, posted.text
    changed = client.get(f"{BASE}/requests/{rid}", headers=teacher).json()
    assert changed["request"]["status"] == "received"
    assert changed["care"]["confirmed_at"] is None and changed["care"]["version"] == 2
    assert len(changed["messages"]) == 2
    item = next(r for r in client.get(BASE + "/care-requests?size=100", headers=teacher).json()["items"] if r["id"] == rid)
    assert item["version"] == 2 and item["next_action"] == "confirm"
    updated = notices(care_backend, rid)
    assert len(updated) == count + 1
    notice = next(n for n in updated if n["body"] == "보호자가 내용을 추가했어요. 다시 확인해 주세요.")
    assert str(notice["recipient_id"]) == str(seed.TEACHER)
    for action in ("confirm", "complete"):
        err(decide(client, teacher, rid, action, version=1, **pickup), 409, "CARD_VERSION_CONFLICT")
    assert decide(client, teacher, rid, **pickup).status_code == 200
    assert decide(client, teacher, rid, "complete", **pickup).status_code == 200


def test_received_message_also_changes_version_and_decisions_require_it(client, parent, teacher):
    rid = create(client, parent).json()["request"]["id"]
    assert client.post(f"{BASE}/requests/{rid}/messages", headers=parent, json={"body": "[TEST] 취소"}).status_code == 201
    err(decide(client, teacher, rid, version=1), 409, "CARD_VERSION_CONFLICT")
    err(client.post(f"{BASE}/requests/{rid}/care-decisions", headers=teacher, json={"decision": "confirm"}),
        422, "VALIDATION_FAILED")


@pytest.mark.parametrize("change", ["inactive", "unlinked"])
def test_completion_uses_confirmed_pickup_snapshot(client, parent, teacher, care_backend, change):
    rid = create(client, parent, "pickup").json()["request"]["id"]
    confirmed = decide(client, teacher, rid, pickup_guardian_id=str(seed.PARENT))
    assert confirmed.status_code == 200
    snapshot = confirmed.json()["care"]
    if care_backend == "mock":
        if change == "inactive":
            store.state().users[seed.PARENT].is_active = False
        else:
            store.state().children[seed.CHILD].guardian_ids = []
    else:
        with transaction() as connection:
            connection.execute(text("UPDATE users SET is_active=false WHERE id=:user") if change == "inactive" else text(
                "DELETE FROM child_guardians WHERE user_id=:user AND child_id=:child"),
                {"user": seed.PARENT, "child": seed.CHILD})
    result = decide(client, teacher, rid, "complete", pickup_guardian_id=str(seed.PARENT))
    assert result.status_code == 200, result.text
    assert result.json()["care"]["pickup_name"] == snapshot["pickup_name"]
    assert result.json()["care"]["confirmed_at"] == snapshot["confirmed_at"]


def test_pickup_change_is_immediate_after_hours(client, parent, teacher, care_backend, monkeypatch):
    from datetime import datetime
    from app.core.schedule import KST

    evening = datetime(2026, 11, 20, 19, 15, tzinfo=KST)
    if care_backend == "mock":
        monkeypatch.setattr(store, "now", lambda: evening)
    rid = create(client, parent, "pickup").json()["request"]["id"]
    assert decide(client, teacher, rid, pickup_guardian_id=str(seed.PARENT)).status_code == 200
    assert client.post(f"{BASE}/requests/{rid}/messages", headers=parent, json={"body": "[TEST] 귀가 변경"}).status_code == 201
    row = next(n for n in notices(care_backend, rid) if n["body"] == "보호자가 내용을 추가했어요. 다시 확인해 주세요.")
    assert row["deliver_after"] == row["created_at"]


@pytest.mark.parametrize("sort", ["created_at", "-created_at", "updated_at", "-updated_at"])
def test_care_list_sort_is_shared_with_other_lists(client, parent, teacher, sort):
    ids = [create(client, parent).json()["request"]["id"] for _ in range(3)]
    assert client.post(f"{BASE}/requests/{ids[0]}/messages", headers=parent, json={"body": "[TEST] 변경"}).status_code == 201
    result = client.get(BASE + "/care-requests?size=100", headers=teacher, params={"sort": sort})
    assert result.status_code == 200, result.text
    ordered = [r["id"] for r in result.json()["items"] if r["id"] in ids]
    expected = [ids[1], ids[2], ids[0]] if sort.lstrip("-") == "updated_at" else ids
    assert ordered == (list(reversed(expected)) if sort.startswith("-") else expected)


def test_concurrent_confirm_and_cancellation_never_confirm_after_cancel_20_rounds(client, parent, teacher, care_backend):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from fastapi.testclient import TestClient
    from app.main import app

    with ThreadPoolExecutor(max_workers=2) as pool:
        for _ in range(20):
            rid = create(client, parent).json()["request"]["id"]
            gate = Barrier(2)
            def send(cancel):
                with TestClient(app) as concurrent_client:
                    gate.wait(timeout=5)
                    if cancel:
                        return concurrent_client.post(f"{BASE}/requests/{rid}/messages", headers=parent,
                                                      json={"body": "[TEST] 취소할게요"})
                    return concurrent_client.post(f"{BASE}/requests/{rid}/care-decisions", headers=teacher,
                                                  json={"decision": "confirm", "version": 1})
            confirmation, cancellation = pool.submit(send, False), pool.submit(send, True)
            checked, cancelled = confirmation.result(timeout=10), cancellation.result(timeout=10)
            assert checked.status_code in (200, 409), checked.text
            assert cancelled.status_code == 201, cancelled.text
            if checked.status_code == 409:
                assert checked.json()["error"]["code"] == "CARD_VERSION_CONFLICT"
            audit = events(care_backend, rid)
            cancel_id = next(e["id"] for e in audit if e["detail"].get("care_message"))
            assert all(e["id"] < cancel_id for e in audit if e["detail"].get("care_decision") == "confirm")
            final = client.get(f"{BASE}/requests/{rid}", headers=teacher).json()
            assert final["request"]["status"] == "received" and final["care"]["confirmed_at"] is None
            assert final["care"]["version"] == 2
