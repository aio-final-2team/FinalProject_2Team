"""알림장에 그날 보호자 요청을 잇고 누락을 확인·해결해요."""

from datetime import UTC, datetime, time, timedelta
from uuid import UUID, uuid4

import pytest

from app.core.schedule import KST
from app.mock import notes as mock_notes, seed, store
from tests.integration.api.helpers import BASE, err
from tests.integration.api.test_resources import draft, note_list


def test_seed_requests_are_readable_and_scoped(client, teacher, parent, parent_other, teacher_other):
    for request_id, child_id, requester_id, request_type, text, owner, other in (
        (seed.REQUEST_COUGH, seed.CHILD, seed.PARENT, "inquiry", "기침해요", parent, parent_other),
        (seed.REQUEST_PICKUP, seed.demo_id("503"), seed.PARENT_OTHER, "pickup",
         "오늘 할머니가 데리러 가요", parent_other, parent),
    ):
        req = store.state().requests[request_id]
        assert (req.child_id, req.requester_id, req.classroom_id) == (child_id, requester_id, seed.CLASS_STAR)
        assert (req.type, req.body, req.status) == (request_type, text, "received")
        for headers in (owner, teacher):
            response = client.get(f"{BASE}/requests/{request_id}", headers=headers)
            assert response.status_code == 200, response.text
            assert response.json()["request"]["type"] == request_type
            assert response.json()["messages"][0]["body"] == text
        listing = client.get(BASE + "/requests", headers=owner)
        assert listing.status_code == 200, listing.text
        assert str(request_id) in {req["id"] for req in listing.json()["items"]}
        for headers in (other, teacher_other):
            err(client.get(f"{BASE}/requests/{request_id}", headers=headers), 404, "NOT_FOUND")


@pytest.mark.parametrize("request_type", ["medication", "pickup"])
def test_note_link_does_not_enable_t46_registration(client, parent, request_type):
    before = set(store.state().requests)
    response = client.post(BASE + "/requests", headers=parent, json={
        "client_request_id": "not-open-yet", "child_id": str(seed.CHILD), "type": request_type, "body": "요청"})
    err(response, 422, "VALIDATION_FAILED")
    assert set(store.state().requests) == before


def test_child_requests_input_and_demo_omission(client, teacher):
    child = store.state().children[seed.CHILD]
    requests = mock_notes.requests_for_child(child, store.now().date())
    assert {"request_id": seed.REQUEST_COUGH, "type": "inquiry", "text": "기침해요"} in requests
    assert all(set(req) == {"request_id", "type", "text"} for req in requests)
    assert draft(client, teacher).status_code == 202
    notes = note_list(client, teacher).json()["items"]
    for note in notes:
        lines = [line for line in note["content"]["items"] if line["source"]["type"] == "request"]
        missed = [check for check in note["open_checks"] if check["kind"] == "request_missed"]
        if note["child_id"] == str(seed.CHILD):
            assert {line["source"]["request_id"] for line in lines} == {str(req["request_id"]) for req in requests}
            cough = next(line for line in lines if line["source"]["request_id"] == str(seed.REQUEST_COUGH))
            assert (cough["key"], cough["value"]) == ("day", "기침해요")
            assert missed == []
        elif note["child_id"] == str(seed.demo_id("503")):
            assert lines == [] and note["status"] == "needs_check"
            assert missed == [{"id": f"request-{seed.REQUEST_PICKUP}", "item_key": "pickup",
                               "kind": "request_missed", "problem": "보호자 요청을 초안에 반영해 주세요",
                               "sentence": None, "request_id": str(seed.REQUEST_PICKUP)}]
        else:
            assert lines == missed == []


@pytest.mark.parametrize("request_type,key", [("inquiry", "day"), ("medication", "medication"), ("pickup", "pickup")])
def test_non_demo_requests_are_included_verbatim(client, teacher, request_type, key):
    req = store.Request(uuid4(), seed.ORG, seed.CLASS_STAR, seed.demo_id("503"), seed.PARENT_OTHER,
                        "new-note-request", request_type, "  보호자 원문\n그대로  ")
    store.state().requests[req.id] = req
    assert draft(client, teacher).status_code == 202
    note = next(n for n in note_list(client, teacher).json()["items"] if n["child_id"] == str(req.child_id))
    lines = [line for line in note["content"]["items"] if line["source"]["request_id"] == str(req.id)]
    assert len(lines) == 1 and (lines[0]["key"], lines[0]["value"]) == (key, req.body)
    assert all(check["request_id"] != str(req.id) for check in note["open_checks"])


@pytest.mark.parametrize("mismatch", ["org", "classroom", "child", "guardian", "date", "consultation", "complaint"])
def test_outside_or_unrelated_requests_do_not_enter_notes(client, teacher, mismatch):
    req = store.state().requests[seed.REQUEST_COUGH]
    if mismatch == "org":
        req.org_id = uuid4()
    elif mismatch == "classroom":
        req.classroom_id = seed.CLASS_SUN
    elif mismatch == "child":
        req.child_id = seed.CHILD_OTHER
    elif mismatch == "guardian":
        req.requester_id = seed.TEACHER
    elif mismatch == "date":
        req.created_at -= timedelta(days=1)
    else:
        req.type = mismatch
    assert draft(client, teacher).status_code == 202
    for note in note_list(client, teacher).json()["items"]:
        assert all(line["source"]["request_id"] != str(req.id) for line in note["content"]["items"])
        assert all(check["request_id"] != str(req.id) for check in note["open_checks"])


@pytest.mark.parametrize("seconds,included", [(-1, False), (0, True), (86399, True), (86400, False)])
def test_request_date_uses_kst_boundaries(client, teacher, seconds, included):
    req = store.state().requests[seed.REQUEST_COUGH]
    req.created_at = (datetime.combine(store.now().date(), time.min, KST) + timedelta(seconds=seconds)).astimezone(UTC)
    assert draft(client, teacher).status_code == 202
    ids = {line["source"]["request_id"] for note in note_list(client, teacher).json()["items"]
           for line in note["content"]["items"]}
    assert (str(req.id) in ids) is included


def test_request_missed_blocks_until_teacher_resolves_then_sends(client, teacher, parent, parent_other):
    assert draft(client, teacher).status_code == 202
    notes = note_list(client, teacher).json()["items"]
    missed_note = next(n for n in notes if n["child_id"] == str(seed.demo_id("503")))
    check = missed_note["open_checks"][0]
    err(client.patch(f"{BASE}/daily-notes/{missed_note['id']}", headers=teacher, json={"confirm": True}),
        409, "INVALID_TRANSITION")
    for note in notes:
        if note == missed_note:
            continue
        assert client.patch(f"{BASE}/daily-notes/{note['id']}", headers=teacher, json={
            "confirm": True, "resolved_checks": [c["id"] for c in note["open_checks"]]}).status_code == 200
    batch = {"classroom_id": str(seed.CLASS_STAR), "note_date": store.now().date().isoformat()}
    blocked = client.post(BASE + "/daily-notes/send", headers=teacher, json=batch)
    err(blocked, 409, "NOTE_BATCH_BLOCKED")
    assert [n["note_id"] for n in blocked.json()["error"]["details"]["blocked"]] == [missed_note["id"]]
    assert not any(n.status == "sent" for n in store.state().notes.values())
    missed_note["content"]["items"].append({"key": "pickup", "label": "귀가", "value": "오늘 할머니가 데리러 가요",
                                           "source": {"type": "request", "request_id": str(seed.REQUEST_PICKUP)}})
    resolved = client.patch(f"{BASE}/daily-notes/{missed_note['id']}", headers=teacher, json={
        "content": missed_note["content"], "resolved_checks": [check["id"]], "confirm": True})
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["note"]["status"] == "ready" and resolved.json()["note"]["open_checks"] == []
    assert client.post(BASE + "/daily-notes/send", headers=teacher, json=batch).json()["sent_count"] == 20
    for headers, child_id, request_id in ((parent, seed.CHILD, seed.REQUEST_COUGH),
                                         (parent_other, seed.demo_id("503"), seed.REQUEST_PICKUP)):
        visible = client.get(BASE + "/daily-notes", headers=headers, params={"date": batch["note_date"]}).json()
        assert visible["total"] == 1 and visible["items"][0]["child_id"] == str(child_id)
        assert visible["items"][0]["open_checks"] == []
        assert request_id in {UUID(line["source"]["request_id"]) for line in visible["items"][0]["content"]["items"]
                              if line["source"]["type"] == "request"}
