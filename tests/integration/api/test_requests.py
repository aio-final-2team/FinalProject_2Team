"""요청 만들기·상세(API 설계 문서 3.1·3.2)와 공통 규칙(1.3·1.4)."""

from uuid import UUID, uuid4
import json

import pytest
from sqlalchemy import text

from app import backend
from app.core.db import transaction
from app.mock import request_actions, store

from app.mock import seed



@pytest.fixture(autouse=True, params=["mock", "db"])
def request_backend(request, monkeypatch):
    if request.param == "db":
        request.getfixturevalue("seeded_db")
        from app.core import users
        from app.modules.requests import requests
        modules = users, requests
    else:
        modules = store, request_actions
    monkeypatch.setattr(backend, "users", modules[0])
    monkeypatch.setattr(backend, "request_actions", modules[1])
    return request.param


def change_request(request_backend, request_id, **values):
    if request_backend == "mock":
        req = store.state().requests[UUID(str(request_id))]
        for name, value in values.items():
            setattr(req, name, value)
    else:
        with transaction() as connection:
            assignments = ", ".join(f"{name}=:{name}" for name in values)
            connection.execute(text(f"UPDATE requests SET {assignments} WHERE id=:id"),
                               {"id": request_id, **values})


def reply_card(request_backend, request_id):
    if request_backend == "mock":
        return next(c.__dict__.copy() for c in reversed(store.cards_of(UUID(request_id))) if c.kind == "reply_draft")
    with transaction() as connection:
        return dict(connection.execute(text("""
            SELECT * FROM cards WHERE request_id=:id AND kind='reply_draft' ORDER BY created_at DESC,id DESC LIMIT 1
        """), {"id": request_id}).mappings().one())


def audit(request_backend, request_id, action):
    if request_backend == "mock":
        return [e.__dict__ for e in store.events_of(UUID(request_id)) if e.action == action]
    with transaction() as connection:
        return [dict(e) for e in connection.execute(text("""
            SELECT * FROM events WHERE request_id=:id AND action=:action ORDER BY id
        """), {"id": request_id, "action": action}).mappings()]


def _create(client, headers, **over):
    body = {"client_request_id": str(uuid4()), "type": "complaint",
            "body": "등원 버스가 이번 주에만 세 번 20분씩 늦었어요.", "child_id": str(seed.CHILD)}
    body.update(over)
    return client.post("/api/v1/requests", json=body, headers=headers)


def test_create_returns_202_and_same_key_returns_200(client, parent):
    first = _create(client, parent, client_request_id="same-key-0001")
    assert first.status_code == 202
    assert first.json()["request"]["status"] == "received"
    again = _create(client, parent, client_request_id="same-key-0001")
    assert again.status_code == 200
    assert again.json()["request"]["id"] == first.json()["request"]["id"]


def test_complaint_goes_to_teacher_review_with_topic(client, parent, teacher):
    rid = _create(client, parent).json()["request"]["id"]
    detail = client.get(f"/api/v1/requests/{rid}", headers=parent).json()
    assert detail["request"]["status"] == "awaiting_review"
    assert detail["request"]["status_label"] == "선생님 확인 중"
    assert "risk_level" not in detail["request"]            # 학부모에게 위험 등급을 주지 않음
    assert client.get(f"/api/v1/requests/{rid}", headers=teacher).json()["request"]["status_label"] == "확인 필요"


def test_consultation_asks_parent_to_choose_time(client, parent):
    rid = _create(client, parent, type="consultation", body="아이 친구 관계로 상담하고 싶어요.").json()["request"]["id"]
    detail = client.get(f"/api/v1/requests/{rid}", headers=parent).json()
    assert detail["request"]["status"] == "needs_info"
    assert detail["request"]["status_label"] == "시간을 골라 주세요"
    assert len(detail["consultation"]["slots"]) == 3


def test_teacher_cannot_create_request(client, teacher):
    res = _create(client, teacher)
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "FORBIDDEN_ROLE"


def test_other_child_is_not_found(client, parent):
    res = _create(client, parent, child_id=str(seed.CHILD_OTHER))
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "NOT_FOUND"


def test_other_parent_and_other_class_teacher_get_404(client, parent, parent_other, teacher_other):
    rid = _create(client, parent).json()["request"]["id"]
    assert client.get(f"/api/v1/requests/{rid}", headers=parent_other).status_code == 404
    assert client.get(f"/api/v1/requests/{rid}", headers=teacher_other).status_code == 404


def test_validation_error_shape_and_trace_id(client, parent):
    res = client.post("/api/v1/requests", headers={**parent, "X-Request-ID": "trace-test-1"},
                      json={"client_request_id": "short", "type": "unknown", "body": "", "child_id": "x"})
    assert res.status_code == 422
    err = res.json()["error"]
    assert err["code"] == "VALIDATION_FAILED"
    assert err["trace_id"] == "trace-test-1"
    assert {f["field"] for f in err["details"]["fields"]} >= {"client_request_id", "type", "body", "child_id"}
    assert res.headers["X-Request-ID"] == "trace-test-1"


def test_missing_token_is_401(client):
    res = client.get("/api/v1/me")
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "UNAUTHENTICATED"


def test_me_gives_teacher_classrooms_and_parent_children(client, teacher, parent):
    assert client.get("/api/v1/me", headers=teacher).json()["user"]["classroom_ids"] == [str(seed.CLASS_STAR)]
    assert [c["id"] for c in client.get("/api/v1/me", headers=parent).json()["children"]] == [str(seed.CHILD)]


def test_duplicate_keeps_original_input_and_reports_current_status(client, parent):
    first = _create(client, parent, client_request_id="same-original-key", body="[TEST] 첫 질문", type="inquiry")
    rid = first.json()["request"]["id"]
    current = client.get(f"/api/v1/requests/{rid}", headers=parent).json()["request"]["status"]
    second = _create(client, parent, client_request_id="same-original-key", body="[TEST] 다른 질문",
                     child_id=str(seed.CHILD_OTHER), type="complaint")
    assert second.status_code == 200 and second.json()["request"]["status"] == current
    assert second.json()["request"]["id"] == rid
    assert client.get(f"/api/v1/requests/{rid}", headers=parent).json()["messages"][0]["body"] == "[TEST] 첫 질문"


def test_parent_stream_only_exposes_stages_and_done(client, parent, teacher, parent_other):
    rid = _create(client, parent, type="inquiry").json()["request"]["id"]
    url = f"/api/v1/requests/{rid}/stream"
    response = client.get(url, headers=parent)
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    frames = [part.splitlines() for part in response.text.strip().split("\n\n")]
    events = [(lines[0].removeprefix("event: "), json.loads(lines[1].removeprefix("data: "))) for lines in frames]
    assert {name for name, _ in events} == {"stage", "done"}
    assert [data["stage"] for name, data in events if name == "stage"] == ["classifying", "searching", "drafting", "checking"]
    assert events[-1] == ("done", {"request_status": "awaiting_review"})
    assert all(set(data) == {"stage", "at"} for name, data in events if name == "stage")
    assert "모의 초안" not in response.text and "card_id" not in response.text
    assert client.get(url, headers=teacher).status_code == 403
    assert client.get(url, headers=parent_other).status_code == 404
    assert client.get(url).status_code == 401


@pytest.mark.parametrize("sort", ["created_at", "-created_at", "updated_at", "-updated_at"])
def test_own_list_filters_paginates_and_sorts(client, parent, parent_other, teacher, request_backend, sort):
    rid = _create(client, parent, type="inquiry", body="[TEST] 내 요청").json()["request"]["id"]
    from datetime import datetime, timedelta
    from app.core.schedule import KST
    change_request(request_backend, rid, created_at=datetime.now(KST)+timedelta(days=1),
                   updated_at=datetime.now(KST)+timedelta(days=1))
    response = client.get("/api/v1/requests", headers=parent, params={"sort": sort, "size": 1})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total"] >= 2 and len(data["items"]) == 1
    pages = [client.get("/api/v1/requests", headers=parent,
                        params={"sort": sort, "size": 1, "page": i}).json() for i in range(1, data["total"]+1)]
    ids = [page["items"][0]["id"] for page in pages]
    assert len(set(ids)) == data["total"]
    assert ids[0 if sort.startswith("-") else -1] == rid
    other = client.get("/api/v1/requests", headers=parent_other).json()
    assert rid not in [req["id"] for req in other["items"]]
    filtered = client.get("/api/v1/requests?status=awaiting_review", headers=parent).json()
    assert rid in [req["id"] for req in filtered["items"]]
    assert all(req["status"] == "awaiting_review" for req in filtered["items"])
    for page in (10**17, 10**30):
        last = client.get("/api/v1/requests", headers=parent, params={"page": page, "size": 100})
        assert last.status_code == 200 and last.json()["items"] == [] and last.json()["total"] == data["total"]
    assert client.get("/api/v1/requests", headers=teacher).status_code == 403


@pytest.mark.parametrize("query", [{"status": "unknown"}, {"page": 0}, {"size": 101}, {"sort": "body"}])
def test_request_list_validates_query(client, parent, query):
    response = client.get("/api/v1/requests", headers=parent, params=query)
    assert response.status_code == 422 and response.json()["error"]["code"] == "VALIDATION_FAILED"


def test_additional_message_is_stored_with_trace_without_leaking_draft(client, parent, request_backend):
    rid = _create(client, parent, type="inquiry").json()["request"]["id"]
    response = client.post(f"/api/v1/requests/{rid}/messages",
                           headers={**parent, "X-Request-ID": "message-trace"}, json={"body": "[TEST] 추가 대화"})
    assert response.status_code == 201
    msg = response.json()["message"]
    assert set(msg) == {"id", "sender_type", "sender_role", "body", "created_at"}
    assert (msg["sender_type"], msg["sender_role"]) == ("user", "parent")
    data = client.get(f"/api/v1/requests/{rid}", headers=parent).json()
    assert data["messages"][-1] == msg
    assert set(data["timeline"][-1]) == {"label", "at"}
    assert data["timeline"][-1]["label"] == "선생님 확인 중"
    assert "모의 초안" not in json.dumps(data, ensure_ascii=False)
    events = [e for e in audit(request_backend, rid, "created") if e["detail"].get("message_id") == msg["id"]]
    assert len(events) == 1 and events[0]["detail"]["trace_id"] == "message-trace"


@pytest.mark.parametrize("state", ["completed", "rejected"])
def test_closed_request_rejects_message_but_can_link_new_request(client, parent, parent_other, request_backend, state):
    rid = _create(client, parent).json()["request"]["id"]
    change_request(request_backend, rid, status=state)
    response = client.post(f"/api/v1/requests/{rid}/messages", headers=parent, json={"body": "[TEST] 추가"})
    assert response.status_code == 409 and response.json()["error"]["code"] == "INVALID_TRANSITION"
    reopened = _create(client, parent, previous_request_id=rid)
    assert reopened.status_code == 202
    assert _create(client, parent_other, previous_request_id=rid, child_id=str(seed.CHILD_OTHER)).status_code == 404


def test_live_previous_request_cannot_be_reopened(client, parent):
    rid = _create(client, parent).json()["request"]["id"]
    response = _create(client, parent, previous_request_id=rid)
    assert response.status_code == 409 and response.json()["error"]["code"] == "INVALID_TRANSITION"


def test_complaint_confirm_is_idempotent_and_message_reopens_card(client, parent, request_backend):
    rid = _create(client, parent).json()["request"]["id"]
    change_request(request_backend, rid, status="sent_or_booked", assignee_id=seed.TEACHER)
    before = reply_card(request_backend, rid)
    path = f"/api/v1/requests/{rid}"
    listing = client.get("/api/v1/requests", headers=parent).json()
    assert next(row for row in listing["items"] if row["id"] == rid)["next_action"] == "답변을 확인해 주세요"
    first = client.post(path+"/confirm", headers=parent)
    assert first.status_code == 200 and first.json()["request"]["parent_confirmed_at"].endswith("+09:00")
    assert client.post(path+"/confirm", headers=parent).json() == first.json()
    assert len(audit(request_backend, rid, "parent_confirmed")) == 1
    response = client.post(path+"/messages", headers=parent, json={"body": "[TEST] 아직 궁금해요"})
    assert response.status_code == 201
    data = client.get(path, headers=parent).json()["request"]
    assert data["status"] == "awaiting_review" and data["parent_confirmed_at"] is None
    after = reply_card(request_backend, rid)
    assert after["version"] == before["version"]+1 and after["status"] == "pending" and after["closed_at"] is None
    assert len(audit(request_backend, rid, "returned")) == 1


@pytest.mark.parametrize("kind,state", [("inquiry", "sent_or_booked"), ("complaint", "awaiting_review")])
def test_confirm_requires_sent_complaint(client, parent, request_backend, kind, state):
    rid = _create(client, parent, type=kind).json()["request"]["id"]
    change_request(request_backend, rid, status=state)
    response = client.post(f"/api/v1/requests/{rid}/confirm", headers=parent)
    assert response.status_code == 409 and response.json()["error"]["code"] == "INVALID_TRANSITION"


@pytest.mark.parametrize("method,suffix,body", [("POST", "/messages", {"body": "[TEST] 추가"}),
                                                ("POST", "/confirm", None), ("GET", "/stream", None)])
def test_parent_request_actions_check_owner_role_and_uuid(client, parent, parent_other, teacher, method, suffix, body):
    rid = _create(client, parent).json()["request"]["id"]
    kwargs = {"json": body} if body else {}
    path = f"/api/v1/requests/{rid}{suffix}"
    assert client.request(method, path, headers=parent_other, **kwargs).status_code == 404
    assert client.request(method, path, headers=teacher, **kwargs).status_code == 403
    assert client.request(method, path, **kwargs).status_code == 401
    assert client.request(method, f"/api/v1/requests/not-a-uuid{suffix}", headers=parent, **kwargs).status_code == 422


def test_non_consultation_needs_info_message_reruns_stub(client, parent, request_backend):
    rid = _create(client, parent, type="inquiry").json()["request"]["id"]
    change_request(request_backend, rid, status="needs_info")
    response = client.post(f"/api/v1/requests/{rid}/messages", headers=parent, json={"body": "[TEST] 보완했어요"})
    assert response.status_code == 201
    assert client.get(f"/api/v1/requests/{rid}", headers=parent).json()["request"]["status"] == "awaiting_review"
