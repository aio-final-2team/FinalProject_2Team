"""v0.5의 원본·이력·재생성·개인 기억을 같은 HTTP 시험으로 대조한다."""

import json
from copy import deepcopy
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from app.mock import seed, store
from app.mock.records import Memory
from app.api.schemas.actions import NoteContent
from tests.integration.api.helpers import BASE, err
from tests.integration.api.test_daily_notes import batch, confirm_all, note_backend as note_backend
from tests.integration.api.test_resources import draft, note_list


@pytest.fixture(autouse=True)
def _memory_backend(note_backend, monkeypatch):
    from app import backend
    if note_backend == "db":
        from app.modules.memories import memories
    else:
        from app.mock import memories
    monkeypatch.setattr(backend, "memories", memories)


def stored(note_backend, note_id):
    if note_backend == "mock":
        note = store.state().notes[UUID(note_id)]
        result = {"content": note.content, "ai_original": note.ai_original}
    else:
        from app.core.db import transaction
        with transaction() as connection:
            result = dict(connection.execute(text("SELECT content,ai_original FROM daily_notes WHERE id=:id"),
                                             {"id": note_id}).mappings().one())
    return {key: NoteContent.model_validate(value).model_dump(mode="json") for key, value in result.items()}


def events(note_backend, note_id):
    if note_backend == "mock":
        return [e.__dict__ for e in store.state().events if str(e.daily_note_id) == note_id]
    from app.core.db import transaction
    with transaction() as connection:
        return [dict(row) for row in connection.execute(text("SELECT * FROM events WHERE daily_note_id=:id ORDER BY id"),
                                                       {"id": note_id}).mappings()]


def regenerate(client, teacher, input_id):
    return client.post(f"{BASE}/daily-notes/drafts/{input_id}/regenerate", headers=teacher)


def test_first_original_survives_edits_confirm_send_and_events_link_only_the_note(client, teacher, note_backend):
    input_id = draft(client, teacher).json()["input_id"]
    notes = note_list(client, teacher).json()["items"]
    note = next(n for n in notes if n["open_checks"])
    original = deepcopy(note["content"])
    edited = deepcopy(original)
    edited["items"][0]["value"] = "[TEST] 선생님이 고친 하루"
    response = client.patch(f"{BASE}/daily-notes/{note['id']}", headers=teacher, json={
        "content": edited, "resolved_checks": [c["id"] for c in note["open_checks"]], "confirm": True})
    assert response.status_code == 200, response.text
    confirm_all(client, teacher, [n for n in notes if n["id"] != note["id"]])
    assert client.post(BASE + "/daily-notes/send", headers=teacher, json=batch()).json() == {"sent_count": 20}
    assert stored(note_backend, note["id"]) == {"content": edited, "ai_original": original}
    history = events(note_backend, note["id"])
    assert [e["action"] for e in history] == ["daily_note_drafted", "daily_note_edited",
                                             "daily_note_confirmed", "daily_note_sent"]
    assert all(e["request_id"] is None and e["card_id"] is None for e in history)
    assert [e["actor_type"] for e in history] == ["agent", "user", "user", "user"]
    assert history[-1]["from_status"] == "ready" and history[-1]["to_status"] == "sent"
    assert all(str(e["actor_id"]) == str(seed.TEACHER) for e in history[1:])
    assert not any("선생님이" in json.dumps(e["detail"], ensure_ascii=False) for e in history)
    err(regenerate(client, teacher, input_id), 409, "INVALID_TRANSITION")


def test_regenerate_preserves_edited_notes_and_ready_including_check_ids(client, teacher, note_backend):
    input_id = draft(client, teacher).json()["input_id"]
    before = {n["id"]: n for n in note_list(client, teacher).json()["items"]}
    ready = next(n for n in before.values() if not n["open_checks"])
    confirm_all(client, teacher, [ready])
    ready = next(n for n in note_list(client, teacher).json()["items"] if n["id"] == ready["id"])
    target = next(n for n in before.values() if n["open_checks"])
    edited = deepcopy(target["content"])
    edited["items"][0]["value"] = "[TEST] 임시 수정"
    assert client.patch(f"{BASE}/daily-notes/{target['id']}", headers=teacher,
                        json={"content": edited}).status_code == 200
    target = next(n for n in note_list(client, teacher).json()["items"] if n["id"] == target["id"])
    response = regenerate(client, teacher, input_id)
    assert response.status_code == 202, response.text
    assert response.json()["kept_edited"] == 1
    assert client.get(f"{BASE}/daily-notes/drafts/{input_id}", headers=teacher).json() == {
        "input_id": input_id, "draft_status": "succeeded", "error": None}
    after = {n["id"]: n for n in note_list(client, teacher).json()["items"]}
    assert after.keys() == before.keys() and after[ready["id"]] == ready
    for note_id in before:
        assert stored(note_backend, note_id)["ai_original"] == before[note_id]["content"]
        assert after[note_id]["content"] == (edited if note_id == target["id"] else before[note_id]["content"])
        history = events(note_backend, note_id)
        assert sum(e["action"] == "daily_note_drafted" for e in history) == (1 if note_id in (ready["id"], target["id"]) else 2)
    assert after[target["id"]] == target
    regenerated = next(n for nid, n in after.items() if nid not in (target["id"], ready["id"]))
    assert events(note_backend, regenerated["id"])[-1]["detail"]["regenerated_by"] == str(seed.TEACHER)
    confirm_all(client, teacher, list(after.values()))
    assert regenerate(client, teacher, input_id).status_code == 202
    assert all(n["status"] == "ready" for n in note_list(client, teacher).json()["items"])


@pytest.mark.parametrize("status", ["failed", "queued", "running"])
def test_regenerate_recovers_failed_or_stopped_input(client, teacher, note_backend, status):
    input_id = draft(client, teacher).json()["input_id"]
    if note_backend == "mock":
        entry = store.state().note_inputs[UUID(input_id)]
        entry.draft_status = status
        entry.created_at -= timedelta(days=1)
    else:
        from app.core.db import transaction
        with transaction() as connection:
            connection.execute(text("UPDATE daily_note_inputs SET draft_status=:status, created_at=created_at-interval '1 day' WHERE id=:id"),
                               {"id": input_id, "status": status})
            connection.execute(text("UPDATE cards SET draft=draft-'draft_started_at' WHERE subject_id=:id"), {"id": input_id})
    response = regenerate(client, teacher, input_id)
    assert response.status_code == 202, response.text
    assert client.get(f"{BASE}/daily-notes/drafts/{input_id}", headers=teacher).json()["draft_status"] == "succeeded"
    assert note_list(client, teacher).json()["total"] == 20


def test_regenerate_updates_last_ai_original_then_teacher_edit_keeps_it(client, teacher, note_backend):
    input_id = draft(client, teacher).json()["input_id"]
    before = note_list(client, teacher).json()["items"][0]
    if note_backend == "mock":
        store.state().note_inputs[UUID(input_id)].activities = "[TEST] 새 AI 초안"
    else:
        from app.core.db import transaction
        with transaction() as connection:
            connection.execute(text("UPDATE daily_note_inputs SET activities='[TEST] 새 AI 초안' WHERE id=:id"),
                               {"id": input_id})
    assert regenerate(client, teacher, input_id).json()["kept_edited"] == 0
    after = next(n for n in note_list(client, teacher).json()["items"] if n["id"] == before["id"])
    assert after["content"] != before["content"]
    assert stored(note_backend, after["id"])["ai_original"] == after["content"]
    edited = deepcopy(after["content"])
    edited["items"][0]["value"] = "[TEST] 새 초안을 받은 뒤 선생님 수정"
    assert client.patch(f"{BASE}/daily-notes/{after['id']}", headers=teacher, json={"content": edited}).status_code == 200
    assert regenerate(client, teacher, input_id).json()["kept_edited"] == 1
    assert stored(note_backend, after["id"]) == {"content": edited, "ai_original": after["content"]}


@pytest.mark.parametrize("restored", [False, True])
def test_regenerate_protects_legacy_content_difference_or_restored_edit_history(client, teacher, note_backend, restored):
    input_id = draft(client, teacher).json()["input_id"]
    target = note_list(client, teacher).json()["items"][0]
    changed = deepcopy(target["content"])
    changed["items"][0]["value"] = "[TEST] 과거 수정"
    if restored:
        for content in (changed, target["content"]):
            assert client.patch(f"{BASE}/daily-notes/{target['id']}", headers=teacher, json={"content": content}).status_code == 200
    elif note_backend == "mock":
        store.state().notes[UUID(target["id"])].content["items"][0]["value"] = "[TEST] 과거 수정"
    else:
        from app.core.db import transaction
        with transaction() as connection:
            connection.execute(text("UPDATE daily_notes SET content=CAST(:content AS jsonb) WHERE id=:id"),
                               {"content": json.dumps(changed), "id": target["id"]})
    before = next(n for n in note_list(client, teacher).json()["items"] if n["id"] == target["id"])
    assert regenerate(client, teacher, input_id).json()["kept_edited"] == 1
    assert next(n for n in note_list(client, teacher).json()["items"] if n["id"] == target["id"]) == before
    assert sum(e["action"] == "daily_note_drafted" for e in events(note_backend, target["id"])) == 1


@pytest.mark.parametrize("status", ["queued", "running"])
def test_regenerate_reuses_fresh_active_job_without_new_events(client, teacher, note_backend, status):
    input_id = draft(client, teacher).json()["input_id"]
    target = note_list(client, teacher).json()["items"][0]
    before = events(note_backend, target["id"])
    if note_backend == "mock":
        store.state().note_inputs[UUID(input_id)].draft_status = status
    else:
        from app.core.db import transaction
        with transaction() as connection:
            connection.execute(text("UPDATE daily_note_inputs SET draft_status=:status WHERE id=:id"),
                               {"id": input_id, "status": status})
    response = regenerate(client, teacher, input_id)
    assert response.status_code == 202 and response.json() == {
        "input_id": input_id, "draft_status": status, "error": None, "kept_edited": 0}
    assert events(note_backend, target["id"]) == before


def test_noop_patch_check_resolution_and_confirmation_return_do_not_mark_edited(client, teacher, note_backend):
    input_id = draft(client, teacher).json()["input_id"]
    target = next(n for n in note_list(client, teacher).json()["items"] if n["open_checks"])
    path = f"{BASE}/daily-notes/{target['id']}"
    for body in ({}, {"confirm": False}, {"content": target["content"]},
                 {"resolved_checks": [c["id"] for c in target["open_checks"]]}, {"confirm": True}, {"confirm": False}):
        assert client.patch(path, headers=teacher, json=body).status_code == 200
    history = events(note_backend, target["id"])
    assert [e["action"] for e in history] == ["daily_note_drafted", "checked", "daily_note_confirmed", "returned"]
    assert history[1]["from_status"] == "needs_check" and history[1]["to_status"] == "draft"
    assert history[-1]["from_status"] == "ready" and history[-1]["to_status"] == "draft"
    assert str(history[-1]["actor_id"]) == str(seed.TEACHER)
    assert regenerate(client, teacher, input_id).json()["kept_edited"] == 0
    assert events(note_backend, target["id"])[-1]["action"] == "daily_note_drafted"


def test_regenerate_scopes_and_roles(client, teacher, teacher_other, parent, director):
    input_id = draft(client, teacher).json()["input_id"]
    for headers, status, code in (({}, 401, "UNAUTHENTICATED"), (teacher_other, 404, "NOT_FOUND"),
                                  (parent, 403, "FORBIDDEN_ROLE"), (director, 403, "FORBIDDEN_ROLE")):
        err(regenerate(client, headers, input_id), status, code)
    err(regenerate(client, teacher, uuid4()), 404, "NOT_FOUND")
    err(regenerate(client, teacher, "bad"), 422, "VALIDATION_FAILED")


def test_regenerate_blocks_even_one_sent_note_without_changing_batch(client, teacher, note_backend):
    input_id = draft(client, teacher).json()["input_id"]
    target = next(n for n in note_list(client, teacher).json()["items"] if not n["open_checks"])
    confirm_all(client, teacher, [target])
    if note_backend == "mock":
        store.state().notes[UUID(target["id"])].status = "sent"
    else:
        from app.core.db import transaction
        with transaction() as connection:
            connection.execute(text("UPDATE daily_notes SET status='sent' WHERE id=:id"), {"id": target["id"]})
    before = note_list(client, teacher).json()
    err(regenerate(client, teacher, input_id), 409, "INVALID_TRANSITION")
    assert note_list(client, teacher).json() == before


@pytest.fixture
def memory_ids(note_backend):
    rows = [(seed.TEACHER, "tone", "[TEST] 짧은 문장"), (seed.TEACHER, "preference", "[TEST] 선호"),
            (seed.TEACHER, "rejection_reason", "[TEST] 이전 이유"), (seed.TEACHER_OTHER, "tone", "[TEST] 남의 기억")]
    ids = []
    for index, (owner, kind, content) in enumerate(rows):
        at = store.now() - timedelta(days=index)
        if note_backend == "mock":
            mid = store.state().next_int()
            store.state().memories[mid] = Memory(mid, seed.ORG, owner, kind, content, created_at=at)
        else:
            from app.core.db import transaction
            with transaction() as connection:
                mid = connection.scalar(text("""
                    INSERT INTO memories (org_id,owner_id,kind,content,created_at)
                    VALUES (:org,:owner,:kind,:content,:at) RETURNING id
                """), {"org": seed.ORG, "owner": owner, "kind": kind, "content": content, "at": at})
        ids.append(mid)
    other_org, other_user = uuid4(), uuid4()
    if note_backend == "mock":
        mid = store.state().next_int()
        store.state().memories[mid] = Memory(mid, other_org, other_user, "tone", "[TEST] 다른 기관")
    else:
        from app.core.db import transaction
        with transaction() as connection:
            connection.execute(text("INSERT INTO organizations (id,name) VALUES (:id,'[TEST] 다른 기관')"),
                               {"id": other_org})
            connection.execute(text("""
                INSERT INTO users (id,org_id,role,login_id,password_hash,display_name)
                SELECT :id,:org,'teacher',:login,password_hash,'[TEST] 다른 기관 담임' FROM users WHERE id=:source
            """), {"id": other_user, "org": other_org, "login": f"test-{other_user}", "source": seed.TEACHER})
            mid = connection.scalar(text("""
                INSERT INTO memories (org_id,owner_id,kind,content)
                VALUES (:org,:owner,'tone','[TEST] 다른 기관') RETURNING id
            """), {"org": other_org, "owner": other_user})
    ids.append(mid)
    return ids


def test_memories_are_private_filtered_paginated_and_soft_deleted(client, teacher, teacher_other, memory_ids, note_backend):
    response = client.get(BASE + "/memories", headers=teacher).json()
    assert response["total"] == 3 and [m["id"] for m in response["items"]] == memory_ids[:3]
    assert set(response["items"][0]) == {"id", "kind", "reason_code", "content", "structured", "created_at"}
    filtered = client.get(BASE + "/memories", headers=teacher, params={"kind": "tone"}).json()
    assert filtered["total"] == 1 and filtered["items"][0]["id"] == memory_ids[0]
    pages = [client.get(BASE + "/memories", headers=teacher, params={"size": 1, "page": p,
             "sort": "created_at"}).json() for p in range(1, 4)]
    assert [p["items"][0]["id"] for p in pages] == memory_ids[:3][::-1]
    err(client.delete(f"{BASE}/memories/{memory_ids[3]}", headers=teacher), 404, "NOT_FOUND")
    err(client.delete(f"{BASE}/memories/{memory_ids[4]}", headers=teacher), 404, "NOT_FOUND")
    err(client.delete(f"{BASE}/memories/999999", headers=teacher), 404, "NOT_FOUND")
    deleted = client.delete(f"{BASE}/memories/{memory_ids[0]}", headers=teacher)
    assert deleted.status_code == 204 and deleted.content == b""
    assert client.get(BASE + "/memories", headers=teacher, params={"kind": "tone"}).json()["items"] == []
    assert client.get(BASE + "/memories", headers=teacher_other).json()["total"] == 1
    err(client.delete(f"{BASE}/memories/{memory_ids[0]}", headers=teacher), 404, "NOT_FOUND")
    if note_backend == "mock":
        assert store.state().memories[memory_ids[0]].deleted_at is not None
    else:
        from app.core.db import transaction
        with transaction() as connection:
            assert connection.scalar(text("SELECT deleted_at FROM memories WHERE id=:id"),
                                     {"id": memory_ids[0]}) is not None


def test_memory_empty_validation_and_role_permissions(client, teacher, parent, director):
    assert client.get(BASE + "/memories", headers=teacher).json() == {"items": [], "total": 0, "page": 1, "size": 20}
    for params in ({"kind": "unknown"}, {"page": 0}, {"size": 101}, {"sort": "content"}):
        err(client.get(BASE + "/memories", headers=teacher, params=params), 422, "VALIDATION_FAILED")
    err(client.delete(BASE + "/memories/0", headers=teacher), 422, "VALIDATION_FAILED")
    for method, path in (("GET", "/memories"), ("DELETE", "/memories/1")):
        for headers, status, code in (({}, 401, "UNAUTHENTICATED"), (parent, 403, "FORBIDDEN_ROLE"),
                                      (director, 403, "FORBIDDEN_ROLE")):
            err(client.request(method, BASE + path, headers=headers), status, code)


def test_memory_list_huge_page_is_empty(client, teacher, memory_ids):
    for page in (10**17, 10**30):
        response = client.get(BASE + "/memories", headers=teacher, params={"page": page, "size": 100})
        assert response.status_code == 200, response.text
        assert response.json() == {"items": [], "total": 3, "page": page, "size": 100}
