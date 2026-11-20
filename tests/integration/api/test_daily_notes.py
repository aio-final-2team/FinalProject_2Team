"""알림장 공개 계약을 mock·DB 양쪽 HTTP에서 같은 본문으로 검증한다."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
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


def test_inquiry_and_day_survive_draft_edit_confirm_and_send(client, teacher, parent):
    assert draft(client, teacher).status_code == 202
    listed = note_list(client, teacher).json()["items"]
    note = next(n for n in listed if n["child_id"] == str(seed.CHILD))
    lines = {line["key"]: line for line in note["content"]["items"]}
    assert lines["day"]["source"]["type"] == "teacher_input"
    assert lines["inquiry"]["value"] == "기침해요"
    assert lines["inquiry"]["source"]["request_id"] == str(seed.REQUEST_COUGH)
    assert lines["inquiry"]["source"]["type"] == "request"
    lines["inquiry"]["value"] = "[TEST] 보호자 문의를 확인했어요"
    response = client.patch(f"{BASE}/daily-notes/{note['id']}", headers=teacher,
                            json={"content": note["content"]})
    assert response.status_code == 200, response.text
    assert response.json()["note"]["content"] == note["content"]
    confirm_all(client, teacher, listed)
    response = client.post(BASE + "/daily-notes/send", headers=teacher, json=batch())
    assert response.status_code == 200 and response.json()["sent_count"] == 20
    visible = client.get(BASE + "/daily-notes", headers=parent, params={"date": batch()["note_date"]})
    [sent] = visible.json()["items"]
    assert sent["content"] == note["content"] and sent["status"] == "sent"


@pytest.mark.parametrize("source", [{"type": "teacher_input"}, {"type": "request"}])
def test_inquiry_requires_request_source_and_id(client, teacher, source):
    assert draft(client, teacher).status_code == 202
    note = note_list(client, teacher).json()["items"][0]
    response = client.patch(f"{BASE}/daily-notes/{note['id']}", headers=teacher, json={"content": {"items": [
        {"key": "inquiry", "label": "보호자 문의", "value": "[TEST] 문의", "source": source}]}})
    err(response, 422, "VALIDATION_FAILED")
    after = next(n for n in note_list(client, teacher).json()["items"] if n["id"] == note["id"])
    assert after == note


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
            assert child_lines == []
            expected = {str(r["id"]) for r in seed.DEMO_NOTE_REQUESTS
                        if str(r["child_id"]) == note["child_id"] and r["id"] != seed.REQUEST_PICKUP
                        and r.get("created_at", store.now()).date() == store.now().date()}
            assert {line["source"]["request_id"] for line in request_lines} == expected
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
        for classroom, total in ((seed.CLASS_STAR, 1), (seed.CLASS_SUN, 0), (uuid4(), 0)):
            filtered = client.get(BASE + "/daily-notes", headers=headers, params={
                "date": batch()["note_date"], "classroom_id": str(classroom)})
            assert filtered.status_code == 200, filtered.text
            assert filtered.json()["total"] == total
            assert filtered.json()["items"] == (visible["items"] if total else [])
    assert client.get(BASE + "/daily-notes", headers=director, params={"date": batch()["note_date"]}).json()["total"] == 20
    if note_backend == "db":
        from app.core.db import transaction
        with transaction() as connection:
            notifications = connection.execute(text("SELECT * FROM notifications WHERE kind='note_sent'")).mappings().all()
            expected = {guardian for child in seed.CHILDREN if child["classroom_id"] == seed.CLASS_STAR
                        for guardian in child["guardian_ids"]}
            assert len(notifications) == 18 and len({n["dedupe_key"] for n in notifications}) == 18
            assert {n["recipient_id"] for n in notifications} == expected
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
    blocked = client.post(BASE + "/daily-notes/send", headers=teacher, json=batch())
    err(blocked, 409, "NOTE_BATCH_BLOCKED")
    assert blocked.json()["error"]["details"]["blocked"] == []


@pytest.mark.parametrize("status", ["queued", "running"])
def test_unfinished_batch_cannot_send(client, teacher, note_backend, status):
    response = draft(client, teacher, activities="[실패] 아직 초안 없음")
    if note_backend == "db":
        from app.core.db import transaction
        with transaction() as connection:
            connection.execute(text("UPDATE daily_note_inputs SET draft_status=:status"), {"status": status})
    else:
        store.state().note_inputs[next(iter(store.state().note_inputs))].draft_status = status
    blocked = client.post(BASE + "/daily-notes/send", headers=teacher, json=batch())
    err(blocked, 409, "NOTE_BATCH_BLOCKED")
    assert blocked.json()["error"]["details"]["blocked"] == []
    assert response.status_code == 202 and note_list(client, teacher).json()["items"] == []


@pytest.mark.parametrize("sort", ["created_at", "-created_at"])
def test_note_order_and_pages_follow_child_draft_order(client, teacher, sort):
    draft(client, teacher)
    expected = [str(c["id"]) for c in seed.CHILDREN if c["classroom_id"] == seed.CLASS_STAR]
    if sort.startswith("-"):
        expected.reverse()
    pages = [client.get(BASE + "/daily-notes", headers=teacher, params={
        "date": batch()["note_date"], "classroom_id": str(seed.CLASS_STAR), "size": 10, "page": page,
        "sort": sort}).json()["items"] for page in (1, 2)]
    assert [n["child_id"] for page in pages for n in page] == expected


@pytest.mark.parametrize("source_kind", ["other_child", "no_child", "staff", "parents", "all"])
def test_patch_only_uses_same_child_requests_and_parent_visible_documents(
        client, teacher, note_backend, source_kind):
    draft(client, teacher)
    note = next(n for n in note_list(client, teacher).json()["items"] if n["child_id"] == str(seed.CHILD))
    if source_kind in ("other_child", "no_child"):
        request_id = seed.REQUEST_PICKUP
        if source_kind == "no_child":
            if note_backend == "db":
                from app.core.db import transaction
                with transaction() as connection:
                    connection.execute(text("UPDATE requests SET child_id=NULL WHERE id=:id"), {"id": request_id})
            else:
                store.state().requests[request_id].child_id = None
        source = {"type": "request", "request_id": str(request_id)}
    else:
        if note_backend == "db":
            from app.core.db import transaction
            with transaction() as connection:
                connection.execute(text("UPDATE documents SET visibility=:value WHERE id=:id"),
                                   {"id": seed.MENU, "value": source_kind})
        else:
            store.state().documents[seed.MENU].visibility = source_kind
        source = {"type": "document", "document_id": str(seed.MENU), "document_title": "가상 식단표"}
    content = {"items": [{"key": "day", "label": "오늘", "value": "[TEST] 변경", "source": source}]}
    response = client.patch(f"{BASE}/daily-notes/{note['id']}", headers=teacher, json={
        "content": content, "resolved_checks": [c["id"] for c in note["open_checks"]], "confirm": True})
    if source_kind in ("parents", "all"):
        assert response.status_code == 200 and response.json()["note"]["status"] == "ready"
    else:
        err(response, 422, "VALIDATION_FAILED")
        assert next(n for n in note_list(client, teacher).json()["items"] if n["id"] == note["id"]) == note


def test_patch_validates_document_and_request_sources_atomically(client, teacher, teacher_other):
    draft(client, teacher)
    note = next(n for n in note_list(client, teacher).json()["items"] if n["child_id"] == str(seed.CHILD))
    for source in ({"type": "document", "document_id": str(uuid4()), "document_title": "없음"},
                   {"type": "request", "request_id": str(uuid4())}):
        content = {"items": [{"key": "day", "label": "오늘", "value": "변경", "source": source}]}
        err(client.patch(f"{BASE}/daily-notes/{note['id']}", headers=teacher, json={"content": content}), 404, "NOT_FOUND")
        assert next(n for n in note_list(client, teacher).json()["items"] if n["id"] == note["id"]) == note


@pytest.mark.parametrize("day,numbers", [
    (16, [6, 14]), (17, [3, 7, 15, 18]), (18, [1, 4, 8, 12, 13, 17]),
    (19, [5, 9, 11, 16, 20]), (20, [2, 10, 19]),
])
def test_guardian_fixture_requests_reach_only_their_day_and_child(
        client, teacher, note_backend, monkeypatch, day, numbers):
    """GR-11은 19일만, 같은 날 같은 아이의 GR-12·13은 둘 다 입구와 초안에 들어가요."""
    captured = {}
    if note_backend == "db":
        from app.modules.daily_notes import stub_writer
        original = stub_writer.write

        def capture(payload):
            captured.update({str(c["child_id"]): c["requests"] for c in payload["children"]})
            return original(payload)

        monkeypatch.setattr(stub_writer, "write", capture)
    else:
        original = mock_notes.requests_for_child

        def capture(child, note_date):
            requests = original(child, note_date)
            captured[str(child.id)] = requests
            return requests

        monkeypatch.setattr(mock_notes, "requests_for_child", capture)
    note_date = date(2026, 11, day).isoformat()
    response = draft(client, teacher, note_date=note_date)
    assert response.status_code == 202, response.text
    status = client.get(f"{BASE}/daily-notes/drafts/{response.json()['input_id']}", headers=teacher)
    assert status.json()["draft_status"] == "succeeded"
    listing = client.get(BASE + "/daily-notes", headers=teacher,
                         params={"classroom_id": str(seed.CLASS_STAR), "date": note_date})
    assert listing.status_code == 200, listing.text
    notes = listing.json()["items"]
    assert len(notes) == len(captured) == 20
    fixture_ids = {str(seed.demo_id(f"72{n:02d}")) for n in range(1, 21)}
    expected_ids = {str(seed.demo_id(f"72{n:02d}")) for n in numbers}
    expected = {str(r["id"]): r for r in seed.DEMO_NOTE_REQUESTS if str(r["id"]) in expected_ids}
    observed = set()
    for note in notes:
        child_ids = {rid for rid, r in expected.items() if str(r["child_id"]) == note["child_id"]}
        requests = {str(r["request_id"]): r for r in captured[note["child_id"]]
                    if str(r["request_id"]) in fixture_ids}
        lines = {line["source"]["request_id"]: line for line in note["content"]["items"]
                 if line["source"]["type"] == "request" and line["source"]["request_id"] in fixture_ids}
        assert requests.keys() == lines.keys() == child_ids
        for rid in child_ids:
            req = expected[rid]
            assert (requests[rid]["type"], requests[rid]["text"]) == (req["type"], req["body"])
            assert (lines[rid]["key"], lines[rid]["value"]) == (req["type"], req["body"])
        assert all(str(c.get("request_id")) not in fixture_ids for c in note["open_checks"])
        observed.update(lines)
    assert observed == expected_ids


def test_guardian_fixture_accounts_login_and_see_only_their_child(client):
    for number in (1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 18):
        response = client.post(BASE + "/auth/login", json={
            "login_id": f"parent-c4-{number:02d}", "password": seed.DEMO_PASSWORD})
        assert response.status_code == 200, response.text
        headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
        me = client.get(BASE + "/me", headers=headers)
        assert me.status_code == 200, me.text
        body = me.json()
        assert body["user"]["id"] == str(seed.demo_id(f"44{number:02d}"))
        assert body["user"]["role"] == "parent"
        assert [(child["id"], child["classroom_id"]) for child in body["children"]] == [
            (str(seed.demo_id(f"54{number:02d}")), str(seed.CLASS_STAR))]
