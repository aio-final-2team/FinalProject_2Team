"""알림장 공개 계약을 mock·DB 양쪽 HTTP에서 같은 본문으로 검증한다."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text

from app import backend
from app.mock import notes as mock_notes, seed, store
from tests.integration.api.helpers import BASE, err
from tests.integration.api.test_resources import draft, note_list


@pytest.fixture(autouse=True, params=["mock", "db"])
def note_backend(request, monkeypatch):
    if request.param == "db":
        request.getfixturevalue("seeded_db")
        from app.core import users
        from app.modules.daily_notes import notes
        monkeypatch.setattr(backend, "users", users)
        monkeypatch.setattr(backend, "notes", notes)
    else:
        monkeypatch.setattr(backend, "users", store)
        monkeypatch.setattr(backend, "notes", mock_notes)
    return request.param


def batch():
    return {"classroom_id": str(seed.CLASS_STAR), "note_date": store.now().date().isoformat()}


def confirm_all(client, teacher, notes):
    for note in notes:
        response = client.patch(f"{BASE}/daily-notes/{note['id']}", headers=teacher, json={
            "resolved_checks": [c["id"] for c in note["open_checks"]], "confirm": True})
        assert response.status_code == 200, response.text
        assert response.json()["note"]["status"] == "ready"


def test_draft_preserves_inputs_requests_sources_and_duplicate(client, teacher, note_backend):
    memo = "  ブロックで遊んだ\n함께 놀이  "
    response = draft(client, teacher, child_memos=[{"child_id": str(seed.CHILD), "memo": memo},
                                                  {"child_id": str(seed.demo_id('503')), "memo": " \t "}])
    assert response.status_code == 202, response.text
    assert response.json()["draft_status"] == ("queued" if note_backend == "db" else "succeeded")
    input_id = response.json()["input_id"]
    assert client.get(f"{BASE}/daily-notes/drafts/{input_id}", headers=teacher).json() == {
        "input_id": input_id, "draft_status": "succeeded", "error": None}
    duplicate = draft(client, teacher, activities="바뀐 입력", child_memos=[])
    assert duplicate.status_code == 200 and duplicate.json()["input_id"] == input_id
    notes = note_list(client, teacher).json()["items"]
    assert len(notes) == 20
    for note in notes:
        lines = note["content"]["items"]
        assert next(l["value"] for l in lines if l["key"] == "day") == "블록 놀이와 산책"
        meal = next(l for l in lines if l["key"] == "meal")
        assert meal["source"]["document_id"] == str(seed.MENU) and "카레라이스" in meal["value"]
        child_lines = [l for l in lines if l["key"] == "child"]
        request_lines = [l for l in lines if l["source"]["type"] == "request"]
        missed = [c for c in note["open_checks"] if c["kind"] == "request_missed"]
        if note["child_id"] == str(seed.CHILD):
            assert len(child_lines) == 1 and child_lines[0]["value"] == memo
            assert child_lines[0]["source"]["type"] == "teacher_input"
            assert ("기침해요", str(seed.REQUEST_COUGH)) in [(l["value"], l["source"]["request_id"]) for l in request_lines]
        else:
            assert child_lines == request_lines == []
        if note["child_id"] == str(seed.demo_id("503")):
            assert len(missed) == 1 and missed[0]["request_id"] == str(seed.REQUEST_PICKUP)
        else:
            assert missed == []


def test_batch_atomic_patch_and_parent_visibility(client, teacher, parent, parent_other, director, note_backend):
    assert draft(client, teacher).status_code == 202
    notes = note_list(client, teacher).json()["items"]
    assert client.get(BASE + "/daily-notes", headers=parent, params={"date": batch()["note_date"]}).json()["total"] == 0
    checked = next(n for n in notes if n["open_checks"])
    edited = {"items": [{"key": "day", "label": "오늘", "value": "고친 내용", "source": {"type": "teacher_input"}}]}
    for body in ({"confirm": True, "content": edited}, {"resolved_checks": ["unknown"]}):
        err(client.patch(f"{BASE}/daily-notes/{checked['id']}", headers=teacher, json=body), 409, "INVALID_TRANSITION")
        assert next(n for n in note_list(client, teacher).json()["items"] if n["id"] == checked["id"]) == checked
    confirm_all(client, teacher, [n for n in notes if n["id"] != checked["id"]])
    blocked = client.post(BASE + "/daily-notes/send", headers=teacher, json=batch())
    err(blocked, 409, "NOTE_BATCH_BLOCKED")
    assert [n["note_id"] for n in blocked.json()["error"]["details"]["blocked"]] == [checked["id"]]
    assert all(n["status"] != "sent" for n in note_list(client, teacher).json()["items"])
    confirm_all(client, teacher, [checked])
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: client.post(BASE + "/daily-notes/send", headers=teacher, json=batch()), range(2)))
    assert all(r.status_code == 200 for r in responses)
    assert sorted(r.json()["sent_count"] for r in responses) == [0, 20]
    assert client.post(BASE + "/daily-notes/send", headers=teacher, json=batch()).json() == {"sent_count": 0}
    err(client.patch(f"{BASE}/daily-notes/{checked['id']}", headers=teacher, json={}), 409, "INVALID_TRANSITION")
    for headers, child_id in ((parent, seed.CHILD), (parent_other, seed.demo_id("503"))):
        visible = client.get(BASE + "/daily-notes", headers=headers, params={"date": batch()["note_date"]}).json()
        assert visible["total"] == 1 and visible["items"][0]["child_id"] == str(child_id)
        assert visible["items"][0]["status"] == "sent" and visible["items"][0]["open_checks"] == []
        assert client.get(BASE + "/daily-notes", headers=headers,
                          params={"date": batch()["note_date"], "classroom_id": str(seed.CLASS_SUN)}).json()["items"] == []
    assert client.get(BASE + "/daily-notes", headers=director, params={"date": batch()["note_date"]}).json()["total"] == 20
    if note_backend == "db":
        from app.core.db import transaction
        with transaction() as connection:
            notifications = connection.execute(text("SELECT * FROM notifications WHERE kind='note_sent'")).mappings().all()
            assert len(notifications) == 2 and len({n["dedupe_key"] for n in notifications}) == 2
            assert {n["recipient_id"] for n in notifications} == {seed.PARENT, seed.PARENT_OTHER}
            assert all(n["subject_type"] == "daily_note" and n["request_id"] is None and n["card_id"] is None
                       and n["status"] == "pending" and n["sent_at"] is None for n in notifications)
            assert connection.scalar(text("SELECT count(*) FROM events")) == 0


@pytest.mark.parametrize("bad", ["empty", "too_long", "duplicate", "foreign", "missing"])
def test_memo_validation_does_not_create_input(client, teacher, note_backend, bad):
    memos = [{"child_id": str(seed.CHILD), "memo": "메모"}]
    if bad == "empty":
        memos[0]["memo"] = ""
    elif bad == "too_long":
        memos[0]["memo"] = "가" * 501
    elif bad == "duplicate":
        memos *= 2
    else:
        memos.append({"child_id": str(seed.CHILD_OTHER if bad == "foreign" else uuid4()), "memo": "밖"})
    response = draft(client, teacher, child_memos=memos)
    err(response, 422, "VALIDATION_FAILED")
    if bad in ("foreign", "missing"):
        assert response.json()["error"]["details"]["child_id"] == memos[-1]["child_id"]
    assert note_list(client, teacher).json()["items"] == []
    if note_backend == "db":
        from app.core.db import transaction
        with transaction() as connection:
            assert connection.scalar(text("SELECT count(*) FROM daily_note_inputs")) == 0
            assert connection.scalar(text("SELECT count(*) FROM cards")) == 0
    else:
        assert not store.state().note_inputs


def test_classroom_list_permissions_and_pagination(client, teacher, teacher_other, director, parent):
    path = f"{BASE}/classrooms/{seed.CLASS_STAR}/children"
    listed = client.get(path, headers=teacher)
    assert listed.status_code == 200
    children = listed.json()["items"]
    assert len(children) == 20
    assert [c["display_name"] for c in children] == sorted(c["display_name"] for c in children)
    assert client.get(path, headers=director).json() == listed.json()
    for headers, status, code in (({}, 401, "UNAUTHENTICATED"), (parent, 403, "FORBIDDEN_ROLE"),
                                  (teacher_other, 404, "NOT_FOUND")):
        err(client.get(path, headers=headers), status, code)
    assert draft(client, teacher).status_code == 202
    pages = [client.get(BASE + "/daily-notes", headers=teacher, params={
        "date": batch()["note_date"], "classroom_id": str(seed.CLASS_STAR), "size": 10, "page": page,
        "sort": "created_at"}).json() for page in (1, 2)]
    assert all(p["total"] == 20 and len(p["items"]) == 10 for p in pages)
    assert len({n["id"] for p in pages for n in p["items"]}) == 20


def test_scope_and_roles_on_all_note_operations(client, teacher, teacher_other, parent, director):
    err(draft(client, teacher_other), 404, "NOT_FOUND")
    err(draft(client, director), 403, "FORBIDDEN_ROLE")
    err(draft(client, parent), 403, "FORBIDDEN_ROLE")
    err(draft(client, teacher, note_date=(store.now().date() + timedelta(days=1)).isoformat()), 422, "VALIDATION_FAILED")
    input_id = draft(client, teacher).json()["input_id"]
    note = note_list(client, teacher).json()["items"][0]
    for method, path, payload in (("GET", f"/daily-notes/drafts/{input_id}", None),
                                   ("PATCH", f"/daily-notes/{note['id']}", {}),
                                   ("POST", "/daily-notes/send", batch())):
        for headers, status, code in (({}, 401, "UNAUTHENTICATED"), (teacher_other, 404, "NOT_FOUND"),
                                      (parent, 403, "FORBIDDEN_ROLE"), (director, 403, "FORBIDDEN_ROLE")):
            err(client.request(method, BASE + path, headers=headers, json=payload), status, code)
    err(client.get(BASE + "/daily-notes", headers=teacher, params={"date": batch()["note_date"]}), 422, "VALIDATION_FAILED")


def test_empty_patch_unconfirms_ready_note(client, teacher):
    draft(client, teacher)
    note = next(n for n in note_list(client, teacher).json()["items"] if not n["open_checks"])
    confirm_all(client, teacher, [note])
    response = client.patch(f"{BASE}/daily-notes/{note['id']}", headers=teacher, json={})
    assert response.status_code == 200
    assert response.json()["note"]["status"] == "draft" and response.json()["note"]["confirmed_at"] is None


def test_failed_writer_job_is_queryable_without_partial_notes(client, teacher, note_backend):
    response = draft(client, teacher, activities="[실패] 작업")
    assert response.status_code == 202
    assert response.json()["draft_status"] == ("queued" if note_backend == "db" else "failed")
    status = client.get(f"{BASE}/daily-notes/drafts/{response.json()['input_id']}", headers=teacher)
    assert status.json()["draft_status"] == "failed" and status.json()["error"]["code"] == "UPSTREAM_UNAVAILABLE"
    assert note_list(client, teacher).json()["items"] == []


def test_patch_validates_document_and_request_sources_atomically(client, teacher, teacher_other):
    draft(client, teacher)
    note = next(n for n in note_list(client, teacher).json()["items"] if n["child_id"] == str(seed.CHILD))
    for source in ({"type": "document", "document_id": str(uuid4()), "document_title": "없음"},
                   {"type": "request", "request_id": str(uuid4())}):
        content = {"items": [{"key": "day", "label": "오늘", "value": "변경", "source": source}]}
        err(client.patch(f"{BASE}/daily-notes/{note['id']}", headers=teacher, json={"content": content}), 404, "NOT_FOUND")
        assert next(n for n in note_list(client, teacher).json()["items"] if n["id"] == note["id"]) == note
