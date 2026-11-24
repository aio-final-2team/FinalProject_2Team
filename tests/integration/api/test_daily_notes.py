"""알림장 공개 계약을 mock·DB 양쪽 HTTP에서 같은 본문으로 검증한다."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import date, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from app import backend
from app.core.constants import LATE_NOTE_REQUEST_NOTICE
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


@pytest.fixture
def note_flow_backend(note_backend, monkeypatch):
    if note_backend == "db":
        from app.modules.cards import card_views
        from app.modules.notifications import notifications
        from app.modules.requests import requests as request_actions
    else:
        from app.mock import card_views, notifications, request_actions
    for name, module in dict(card_views=card_views, notifications=notifications, request_actions=request_actions).items():
        monkeypatch.setattr(backend, name, module)
    return note_backend


def batch_card(client, teacher, *, done=False):
    response = client.get(BASE + "/cards", headers=teacher,
                          params={"kind": "daily_note", "filter": "done" if done else "needs_review"})
    assert response.status_code == 200, response.text
    return response.json()["items"][0]


def correction_body(note):
    content = deepcopy(note["content"])
    content["items"][0]["value"] = "[TEST] 산책 대신 실내에서 블록 놀이를 했어요."
    return {"version": note["version"], "content": content, "reason_text": "[TEST] 활동 기록 오기 정정"}


def sent_child_note(client, teacher):
    assert draft(client, teacher, activities="[TEST] 정정 전 활동").status_code == 202
    confirm_all(client, teacher, note_list(client, teacher).json()["items"])
    assert client.post(BASE + "/daily-notes/send", headers=teacher, json=batch()).json()["sent_count"] == 20
    return next(n for n in note_list(client, teacher).json()["items"] if n["child_id"] == str(seed.CHILD))


@pytest.mark.parametrize("actor", ["teacher", "director"])
def test_sent_note_correction_notifies_parent_once_and_preserves_send_and_original(
        client, teacher, director, parent, parent_other, note_flow_backend, actor):
    from tests.integration.api.test_note_v05 import events, saved_content, stored

    note = sent_child_note(client, teacher)
    assert note["version"] == 1 and note["corrected_at"] is None
    before = stored(note_flow_backend, note["id"])
    body = correction_body(note)
    path = f"{BASE}/daily-notes/{note['id']}/correct"
    response = client.post(path, headers=teacher if actor == "teacher" else director, json=body)
    assert response.status_code == 200, response.text
    corrected = response.json()["note"]
    assert corrected["status"] == "sent" and corrected["version"] == 2 and corrected["corrected_at"]
    assert corrected["sent_at"] == note["sent_at"] and corrected["confirmed_at"] == note["confirmed_at"]
    assert corrected["open_checks"] == []
    assert saved_content(corrected["content"]) == saved_content(body["content"])
    assert stored(note_flow_backend, note["id"]) == {
        "content": saved_content(body["content"]), "ai_original": before["ai_original"]}
    history = [e for e in events(note_flow_backend, note["id"]) if e["action"] == "daily_note_corrected"]
    assert len(history) == 1
    event = history[0]
    assert event["actor_type"] == "user" and event["actor_id"] == (seed.TEACHER if actor == "teacher" else seed.DIRECTOR)
    assert event["from_status"] == event["to_status"] == "sent"
    assert event["detail"]["reason_text"] == body["reason_text"] and event["detail"]["version"] == 2
    assert "content" not in event["detail"] and "ai_original" not in event["detail"]
    public = client.get(BASE + "/daily-notes", headers=parent, params={"date": batch()["note_date"]}).json()
    assert public["total"] == 1 and public["items"][0] == corrected
    notices = client.get(BASE + "/notifications", headers=parent).json()["items"]
    corrections = [n for n in notices if n["kind"] == "note_corrected"]
    assert len(corrections) == 1 and corrections[0]["title"] == "알림장이 고쳐졌어요"
    assert corrections[0]["subject_type"] == "daily_note" and corrections[0]["subject_id"] == note["id"]
    assert corrections[0]["body"] is None and corrections[0]["request_id"] is None
    assert not any(n["kind"] == "note_corrected" for n in client.get(
        BASE + "/notifications", headers=parent_other).json()["items"])
    err(client.patch(f"{BASE}/daily-notes/{note['id']}", headers=teacher, json={"content": body["content"]}),
        409, "INVALID_TRANSITION")
    stale = client.post(path, headers=teacher, json=body)
    err(stale, 409, "CARD_VERSION_CONFLICT")
    assert stale.json()["error"]["details"]["current_version"] == 2
    assert len([e for e in events(note_flow_backend, note["id"]) if e["action"] == "daily_note_corrected"]) == 1
    assert len([n for n in client.get(BASE + "/notifications", headers=parent).json()["items"]
                if n["kind"] == "note_corrected"]) == 1
    second = client.post(path, headers=teacher, json={**body, "version": 2, "reason_text": "[TEST] 추가 정정"})
    assert second.status_code == 200 and second.json()["note"]["version"] == 3
    assert len([n for n in client.get(BASE + "/notifications", headers=parent).json()["items"]
                if n["kind"] == "note_corrected"]) == 2


@pytest.mark.parametrize("status", ["draft", "needs_check", "ready"])
def test_note_correction_rejects_unsent_status_without_side_effects(client, teacher, note_flow_backend, status):
    from tests.integration.api.test_note_v05 import events

    assert draft(client, teacher, activities="[TEST] 미발송 정정 거부").status_code == 202
    note = next(n for n in note_list(client, teacher).json()["items"] if n["child_id"] == str(seed.CHILD))
    if status != "needs_check":
        changed = client.patch(f"{BASE}/daily-notes/{note['id']}", headers=teacher, json={
            "resolved_checks": [c["id"] for c in note["open_checks"]], "confirm": status == "ready"})
        assert changed.status_code == 200
        note = changed.json()["note"]
    assert note["status"] == status
    before = events(note_flow_backend, note["id"])
    err(client.post(f"{BASE}/daily-notes/{note['id']}/correct", headers=teacher, json=correction_body(note)),
        409, "INVALID_TRANSITION")
    assert next(n for n in note_list(client, teacher).json()["items"] if n["id"] == note["id"]) == note
    assert events(note_flow_backend, note["id"]) == before


def test_note_correction_rejects_parent_and_other_classroom(client, teacher, teacher_other, parent, note_flow_backend):
    note = sent_child_note(client, teacher)
    path = f"{BASE}/daily-notes/{note['id']}/correct"
    err(client.post(path, headers=parent, json=correction_body(note)), 403, "FORBIDDEN_ROLE")
    err(client.post(path, headers=teacher_other, json=correction_body(note)), 404, "NOT_FOUND")
    assert next(n for n in note_list(client, teacher).json()["items"] if n["id"] == note["id"]) == note


@pytest.mark.parametrize("change", ["missing_reason", "blank_reason", "long_reason", "missing_content", "null_content",
                                   "missing_version", "zero_version", "wrong_child_source", "staff_document_source"])
def test_note_correction_validates_required_fields_and_existing_source_scope(
        client, teacher, note_flow_backend, change):
    from tests.integration.api.test_note_v05 import events

    note = sent_child_note(client, teacher)
    body = correction_body(note)
    if change.startswith("missing_"):
        body.pop({"missing_reason": "reason_text", "missing_content": "content", "missing_version": "version"}[change])
    elif change == "blank_reason":
        body["reason_text"] = " \n\t "
    elif change == "long_reason":
        body["reason_text"] = "[TEST]" + "x" * 500
    elif change == "null_content":
        body["content"] = None
    elif change == "zero_version":
        body["version"] = 0
    elif change == "wrong_child_source":
        body["content"]["items"] = [{"key": "pickup", "label": "[TEST] 귀가", "value": "[TEST] 다른 아이",
                                      "source": {"type": "request", "request_id": str(seed.REQUEST_PICKUP)}}]
    else:
        if note_flow_backend == "mock":
            store.state().documents[seed.NOTICE].visibility = "staff"
        else:
            from app.core.db import transaction
            with transaction() as connection:
                connection.execute(text("UPDATE documents SET visibility='staff' WHERE id=:id"), {"id": seed.NOTICE})
        body["content"]["items"] = [{"key": "day", "label": "[TEST] 활동", "value": "[TEST] 교직원 자료",
                                      "source": {"type": "document", "document_id": str(seed.NOTICE),
                                                 "document_title": "[TEST] 방침"}}]
    before = events(note_flow_backend, note["id"])
    err(client.post(f"{BASE}/daily-notes/{note['id']}/correct", headers=teacher, json=body), 422, "VALIDATION_FAILED")
    assert next(n for n in note_list(client, teacher).json()["items"] if n["id"] == note["id"]) == note
    assert events(note_flow_backend, note["id"]) == before


def test_note_correction_concurrent_same_version_accepts_only_one(client, teacher, parent, note_flow_backend):
    from tests.integration.api.test_note_v05 import events

    note = sent_child_note(client, teacher)

    def correct(index):
        return client.post(f"{BASE}/daily-notes/{note['id']}/correct", headers=teacher,
                           json={**correction_body(note), "reason_text": f"[TEST] 경합 {index}"})

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(correct, range(2)))
    assert sorted(r.status_code for r in responses) == [200, 409]
    err(next(r for r in responses if r.status_code == 409), 409, "CARD_VERSION_CONFLICT")
    assert len([e for e in events(note_flow_backend, note["id"]) if e["action"] == "daily_note_corrected"]) == 1
    assert len([n for n in client.get(BASE + "/notifications", headers=parent).json()["items"]
                if n["kind"] == "note_corrected"]) == 1


@pytest.mark.parametrize("request_type", ["medication", "pickup", "inquiry"])
@pytest.mark.parametrize("status", ["draft", "needs_check", "ready", "sent"])
def test_late_request_reopens_unsent_note_and_notifies_batch_owner_once(
        client, teacher, parent, note_flow_backend, request_type, status):
    assert draft(client, teacher, activities="[TEST] 늦은 요청 전 활동").status_code == 202
    listed = note_list(client, teacher).json()["items"]
    target = next(n for n in listed if n["child_id"] == str(seed.CHILD))
    if status != "needs_check":
        response = client.patch(f"{BASE}/daily-notes/{target['id']}", headers=teacher, json={
            "resolved_checks": [c["id"] for c in target["open_checks"]], "confirm": status in ("ready", "sent")})
        assert response.status_code == 200
    if status == "sent":
        confirm_all(client, teacher, note_list(client, teacher).json()["items"])
        assert client.post(BASE + "/daily-notes/send", headers=teacher, json=batch()).json()["sent_count"] == 20
    before = {n["id"]: n for n in note_list(client, teacher).json()["items"]}
    card = batch_card(client, teacher, done=status == "sent")
    payload = {"client_request_id": str(uuid4()), "type": request_type,
               "child_id": str(seed.CHILD), "body": "[TEST] 초안 뒤에 접수한 보호자 요청"}
    created = client.post(BASE + "/requests", headers=parent, json=payload)
    assert created.status_code == 202, created.text
    rid = created.json()["request"]["id"]
    after = {n["id"]: n for n in note_list(client, teacher).json()["items"]}
    assert all(after[nid] == row for nid, row in before.items() if nid != target["id"])
    current = after[target["id"]]
    assert current["content"] == before[target["id"]]["content"]
    missed = [c for c in current["open_checks"] if c["request_id"] == rid]
    if status == "sent":
        assert current == before[target["id"]] and missed == []
    else:
        assert current["status"] == "needs_check" and current["confirmed_at"] is None
        assert len(missed) == 1 and missed[0]["kind"] == "request_missed"
        assert missed[0]["item_key"] == request_type and missed[0]["sentence"] is None
        assert current["open_checks"][:-1] == before[target["id"]]["open_checks"]
        err(client.patch(f"{BASE}/daily-notes/{target['id']}", headers=teacher, json={"confirm": True}),
            409, "INVALID_TRANSITION")
        confirm_all(client, teacher, [n for n in after.values() if n["id"] != target["id"]])
        err(client.post(BASE + "/daily-notes/send", headers=teacher, json=batch()), 409, "NOTE_BATCH_BLOCKED")
        confirm_all(client, teacher, [current])
    # 재전송은 이미 해결한 확인을 다시 열거나 알림을 늘리지 않는다.
    stable = note_list(client, teacher).json()
    assert client.post(BASE + "/requests", headers=parent, json=payload).status_code == 200
    assert note_list(client, teacher).json() == stable
    notices = client.get(BASE + "/notifications", headers=teacher, params={"size": 100}).json()["items"]
    notices = [n for n in notices if n["body"] == LATE_NOTE_REQUEST_NOTICE and n["request_id"] == rid]
    assert len(notices) == 1 and notices[0]["kind"] == "new_card"
    assert notices[0]["subject_type"] == "daily_note" and notices[0]["subject_id"] == target["id"]
    assert "아이 알림장을 확인" in notices[0]["body"]
    if note_flow_backend == "mock":
        assert str(store.state().notifications[notices[0]["id"]].card_id) == card["id"]
    else:
        from app.core.db import transaction
        with transaction() as connection:
            assert str(connection.scalar(text("SELECT card_id FROM notifications WHERE id=:id"),
                                         {"id": notices[0]["id"]})) == card["id"]
    if status == "sent":
        assert batch_card(client, teacher, done=True)["status"] == "done"


@pytest.mark.parametrize("excluded", ["past_date", "other_class", "consultation", "complaint"])
def test_late_request_does_not_change_other_date_class_or_unrelated_type(
        client, teacher, parent, parent_other, note_flow_backend, excluded):
    day = store.now().date() - timedelta(days=1) if excluded == "past_date" else store.now().date()
    assert draft(client, teacher, activities="[TEST] 범위 검사", note_date=day.isoformat()).status_code == 202
    params = {"date": day.isoformat(), "classroom_id": str(seed.CLASS_STAR)}
    before = client.get(BASE + "/daily-notes", headers=teacher, params=params).json()
    payload = {"client_request_id": str(uuid4()), "body": "[TEST] 다른 범위 요청",
               "type": excluded if excluded in ("consultation", "complaint") else "inquiry",
               "child_id": str(seed.CHILD_OTHER if excluded == "other_class" else seed.CHILD)}
    result = client.post(BASE + "/requests", headers=parent_other if excluded == "other_class" else parent, json=payload)
    assert result.status_code == 202, result.text
    assert client.get(BASE + "/daily-notes", headers=teacher, params=params).json() == before
    notices = client.get(BASE + "/notifications", headers=teacher, params={"size": 100}).json()["items"]
    assert not any(n["body"] == LATE_NOTE_REQUEST_NOTICE and n["request_id"] == result.json()["request"]["id"] for n in notices)


def test_batch_card_shows_missing_child_and_regenerate_only_creates_unprotected_child(
        client, teacher, parent, note_flow_backend):
    input_id = draft(client, teacher, activities="[TEST] 전입 전 활동").json()["input_id"]
    confirm_all(client, teacher, note_list(client, teacher).json()["items"])
    before = {n["id"]: n for n in note_list(client, teacher).json()["items"]}
    child_id = uuid4()
    if note_flow_backend == "mock":
        store.state().children[child_id] = store.Child(child_id, seed.ORG, seed.CLASS_STAR, "[TEST] 전입 아이", [])
    else:
        from app.core.db import transaction
        with transaction() as connection:
            connection.execute(text("""
                INSERT INTO children (id,org_id,classroom_id,display_name) VALUES (:id,:org,:class,'[TEST] 전입 아이')
            """), {"id": child_id, "org": seed.ORG, "class": seed.CLASS_STAR})
    card = batch_card(client, teacher)
    detail = client.get(f"{BASE}/cards/{card['id']}", headers=teacher).json()["card"]
    assert detail["note_batch"] == card["note_batch"]
    assert card["note_batch"]["input_id"] == input_id and card["note_batch"]["draft_status"] == "succeeded"
    missing = [c for c in card["note_batch"]["children"] if c["status"] == "missing"]
    assert missing == [{"child_id": str(child_id), "display_name": "[TEST] 전입 아이", "note_id": None, "status": "missing"}]
    err(client.get(f"{BASE}/cards/{card['id']}", headers=parent), 403, "FORBIDDEN_ROLE")
    blocked = client.post(BASE + "/daily-notes/send", headers=teacher, json=batch())
    err(blocked, 409, "NOTE_BATCH_BLOCKED")
    assert blocked.json()["error"]["details"]["blocked"] == [
        {"note_id": None, "child_id": str(child_id), "status": "missing", "open_checks": []}]
    assert client.post(f"{BASE}/daily-notes/drafts/{input_id}/regenerate", headers=teacher).status_code == 202
    listing = client.get(BASE + "/daily-notes", headers=teacher, params={
        "date": batch()["note_date"], "classroom_id": str(seed.CLASS_STAR), "size": 100})
    assert listing.status_code == 200 and listing.json()["total"] == 21
    after = {n["id"]: n for n in listing.json()["items"]}
    assert len(after) == 21 and all(after[nid] == row for nid, row in before.items())
    new_note = next(n for n in after.values() if n["child_id"] == str(child_id))
    confirm_all(client, teacher, [new_note])
    assert client.post(BASE + "/daily-notes/send", headers=teacher, json=batch()).json()["sent_count"] == 21
    done = batch_card(client, teacher, done=True)
    assert done["status"] == "done" and done["status_label"] == "완료"
    assert {c["status"] for c in done["note_batch"]["children"]} == {"sent"}
    assert client.post(BASE + "/daily-notes/send", headers=teacher, json=batch()).json()["sent_count"] == 0
    assert batch_card(client, teacher, done=True)["version"] == done["version"]


@pytest.mark.parametrize("status,label", [("queued", "만드는 중"), ("running", "만드는 중"),
                                         ("failed", "만들기 실패 · 다시 만들기"), ("succeeded", "확인 필요")])
def test_batch_card_reports_job_status_in_list_and_detail(client, teacher, note_flow_backend, status, label):
    input_id = draft(client, teacher, activities="[TEST] 상태 표시").json()["input_id"]
    if note_flow_backend == "mock":
        store.state().note_inputs[UUID(input_id)].draft_status = status
    else:
        from app.core.db import transaction
        with transaction() as connection:
            connection.execute(text("UPDATE daily_note_inputs SET draft_status=:status WHERE id=:id"),
                               {"status": status, "id": input_id})
    card = batch_card(client, teacher)
    detail = client.get(f"{BASE}/cards/{card['id']}", headers=teacher).json()["card"]
    for row in (card, detail):
        assert row["status_label"] == label
        assert row["note_batch"]["draft_status"] == status


def test_batch_card_metadata_requires_matching_input_organization(client, teacher, note_flow_backend):
    input_id = draft(client, teacher, activities="[TEST] 기관 경계").json()["input_id"]
    if note_flow_backend == "mock":
        assert mock_notes.batch_view(UUID(input_id), uuid4()) is None
        assert mock_notes.batch_view(uuid4(), seed.ORG) is None
    else:
        from app.core.db import transaction
        from app.modules.daily_notes import notes
        with transaction() as connection:
            assert notes.batch_view(connection, input_id, uuid4()) is None
            assert notes.batch_view(connection, uuid4(), seed.ORG) is None


def test_return_limit_check_blocks_confirmation_and_send_until_all_resolved(
        client, teacher, note_backend, monkeypatch):
    check = {"id": "return-limit", "item_key": "child", "kind": "return_limit",
             "problem": "AI가 두 번 고쳐도 남은 문제가 있어요. 직접 확인해 주세요", "sentence": None}
    if note_backend == "db":
        from app.modules.daily_notes import stub_writer
        original = stub_writer.write_child

        def write_child(payload, child, index):
            row = original(payload, child, index)
            if child["child_id"] == str(seed.CHILD):
                row["open_checks"].append(dict(check))
            return row

        monkeypatch.setattr(stub_writer, "write_child", write_child)
    else:
        # 모의 모드는 외부 writer가 없어, 생성 결과에 같은 확인 항목을 붙인다.
        original = mock_notes._generate

        def generate(entry, children, **kwargs):
            original(entry, children, **kwargs)
            target = next(n for n in store.state().notes.values() if n.child_id == seed.CHILD)
            target.open_checks.append(dict(check))

        monkeypatch.setattr(mock_notes, "_generate", generate)
    assert draft(client, teacher).status_code == 202
    listed = note_list(client, teacher).json()["items"]
    target = next(n for n in listed if n["child_id"] == str(seed.CHILD))
    assert target["status"] == "needs_check"
    limit = next(c for c in target["open_checks"] if c["kind"] == "return_limit")
    assert limit["problem"] == check["problem"] and limit["sentence"] is None
    path = f"{BASE}/daily-notes/{target['id']}"
    err(client.patch(path, headers=teacher, json={"confirm": True}), 409, "INVALID_TRANSITION")
    # 한도 초과만 풀어도 기존 날짜 확인이 남아 있으면 아직 확인할 수 없다.
    err(client.patch(path, headers=teacher, json={"resolved_checks": [limit["id"]], "confirm": True}),
        409, "INVALID_TRANSITION")
    confirm_all(client, teacher, [n for n in listed if n["id"] != target["id"]])
    err(client.post(BASE + "/daily-notes/send", headers=teacher, json=batch()), 409, "NOTE_BATCH_BLOCKED")
    confirm_all(client, teacher, [target])
    sent = client.post(BASE + "/daily-notes/send", headers=teacher, json=batch())
    assert sent.status_code == 200 and sent.json()["sent_count"] == 20


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
    assert all(sent[key].endswith("+09:00") for key in ("confirmed_at", "sent_at"))


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
            assert connection.scalar(text("SELECT count(*) FROM events WHERE action='daily_note_sent'")) == 20


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


def test_note_list_huge_page_is_empty(client, teacher):
    for total in (0, 20):
        if total:
            assert draft(client, teacher).status_code == 202
        for page in (10**17, 10**30):
            response = client.get(BASE + "/daily-notes", headers=teacher, params={
                "date": batch()["note_date"], "classroom_id": str(seed.CLASS_STAR), "page": page, "size": 100})
            assert response.status_code == 200, response.text
            assert response.json() == {"items": [], "total": total, "page": page, "size": 100}


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
