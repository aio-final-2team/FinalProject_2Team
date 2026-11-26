"""요청 만들기·상세(API 설계 문서 3.1·3.2)와 공통 규칙(1.3·1.4)."""

from uuid import UUID, uuid4
import json

import pytest
from sqlalchemy import text

from app import backend
from app.core.db import transaction
from app.mock import request_actions, store

from app.mock import seed
from tests.integration.api.helpers import decision, err



@pytest.fixture(autouse=True, params=["mock", "db"])
def request_backend(request, monkeypatch):
    if request.param == "db":
        request.getfixturevalue("seeded_db")
        from app.core import users
        from app.modules.requests import requests
        from app.modules.cards import cards, card_views
        from app.modules.notifications import notifications
        modules = users, requests
    else:
        from app.mock import cards, card_views, notifications
        modules = store, request_actions
    monkeypatch.setattr(backend, "users", modules[0])
    monkeypatch.setattr(backend, "request_actions", modules[1])
    for name, module in dict(cards=cards, card_views=card_views, notifications=notifications).items():
        monkeypatch.setattr(backend, name, module)
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


@pytest.mark.parametrize("kind,status,assignee,expected", [
    ("inquiry", "received", None, "접수됨"),
    ("inquiry", "classified", None, "접수됨"),
    ("inquiry", "classified", seed.TEACHER, "접수됨"),
    ("inquiry", "assigned", seed.TEACHER, "선생님께 전달됨"),
    ("inquiry", "assigned", None, "담당 선생님 배정 중"),
    ("complaint", "awaiting_review", None, "담당 선생님 배정 중"),
    ("complaint", "awaiting_review", seed.TEACHER, "선생님 확인 중"),
    ("consultation", "on_hold", None, "담당 선생님 배정 중"),
    ("consultation", "on_hold", seed.TEACHER, "확인이 늦어지고 있어요"),
    ("consultation", "needs_info", None, "시간을 골라 주세요"),
    ("consultation", "sent_or_booked", seed.TEACHER, "예약 확정"),
    ("medication", "received", None, "선생님 확인 대기"),
    ("pickup", "assigned", seed.TEACHER, "선생님 확인 완료"),
    ("medication", "completed", seed.TEACHER, "투약 완료"),
    ("pickup", "completed", seed.TEACHER, "인계 완료"),
])
def test_parent_labels_follow_assignment_and_keep_type_branches(kind, status, assignee, expected):
    from app.api.labels import parent_label

    assert parent_label(status, kind, assignee) == expected


def test_unassigned_request_label_changes_after_director_reassign(client, parent, director, request_backend, monkeypatch):
    if request_backend == "mock":
        from app.mock import cards
        store.state().classroom_staff[:] = [s for s in store.state().classroom_staff if s.classroom_id != seed.CLASS_STAR]
    else:
        from app.modules.cards import cards
        with transaction() as connection:
            connection.execute(text("DELETE FROM classroom_staff WHERE classroom_id=:id"), {"id": seed.CLASS_STAR})
    monkeypatch.setattr(backend, "cards", cards)
    rid = _create(client, parent, type="inquiry", body="[TEST] 버스 문의").json()["request"]["id"]
    card = reply_card(request_backend, rid)
    assert card["status"] == "unassigned" and card["assignee_id"] is None

    def check_label(expected):
        detail = client.get(f"/api/v1/requests/{rid}", headers=parent).json()
        assert detail["request"]["status_label"] == expected
        assert detail["timeline"][-1]["label"] == expected
        listing = client.get("/api/v1/requests", headers=parent).json()["items"]
        assert next(r for r in listing if r["id"] == rid)["status_label"] == expected

    check_label("담당 선생님 배정 중")
    response = client.post(f"/api/v1/cards/{card['id']}/reassign", headers=director,
                           json={"assignee_id": str(seed.TEACHER), "reason": "[TEST] 담당 배정"})
    assert response.status_code == 200, response.text
    check_label("선생님 확인 중")


def test_received_request_label_before_agent_runs(client, parent, request_backend, monkeypatch):
    if request_backend == "mock":
        monkeypatch.setattr(store, "_run_mock_ai", lambda *args: None)
    else:
        from app.modules.requests import requests
        monkeypatch.setattr(requests, "dispatch", lambda *args: None)
    created = _create(client, parent, type="inquiry")
    assert created.status_code == 202 and created.json()["request"]["status"] == "received"
    rid = created.json()["request"]["id"]
    detail = client.get(f"/api/v1/requests/{rid}", headers=parent).json()
    assert detail["request"]["status_label"] == detail["timeline"][-1]["label"] == "접수됨"
    listing = client.get("/api/v1/requests", headers=parent).json()["items"]
    assert next(r for r in listing if r["id"] == rid)["status_label"] == "접수됨"


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
    staff = client.get("/api/v1/requests", headers=teacher)
    assert staff.status_code == 200 and rid in [r["id"] for r in staff.json()["items"]]


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
    events = [e for e in audit(request_backend, rid, "message_added") if e["detail"].get("message_id") == msg["id"]]
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
    assert before["check_result"] is not None and after["check_result"] is None
    assert after["draft"]["text"] == "" and after["draft"]["previous_text"] == before["draft"]["text"]
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


def test_non_consultation_needs_info_message_keeps_human_review(client, parent, request_backend):
    rid = _create(client, parent, type="inquiry").json()["request"]["id"]
    change_request(request_backend, rid, status="needs_info")
    response = client.post(f"/api/v1/requests/{rid}/messages", headers=parent, json={"body": "[TEST] 보완했어요"})
    assert response.status_code == 201
    assert client.get(f"/api/v1/requests/{rid}", headers=parent).json()["request"]["status"] == "needs_info"
    assert len(audit(request_backend, rid, "classified")) == 1


def notices(request_backend, request_id):
    if request_backend == "mock":
        return [n.__dict__.copy() for n in store.state().notifications.values() if str(n.request_id) == request_id]
    with transaction() as connection:
        return [dict(n) for n in connection.execute(text(
            "SELECT * FROM notifications WHERE request_id=:id ORDER BY id"), {"id": request_id}).mappings()]


@pytest.mark.parametrize("kind,body,notice", [
    ("payment", "원비 결제해 주세요.",
     "유치온에서는 원비 결제를 하지 않아요. 원비는 원에서 안내한 기존 방법으로 문의해 주세요."),
    ("others_privacy", "다른 가정의 연락처를 알려주세요.",
     "다른 가정의 연락처 같은 개인정보는 알려 드릴 수 없어요."),
    ("other_family", "다른 가정의 민원 내용을 보여주세요.",
     "다른 가정의 요청이나 내용은 볼 수 없어요. 우리 아이 일이라면 다시 적어 주세요."),
    ("other_teacher", "옆 반 선생님과 상담하고 싶어요.", "상담은 담임 선생님과 잡을 수 있어요."),
])
def test_out_of_scope_inquiry_sends_fixed_agent_notice_without_cards(
    client, parent, teacher, director, request_backend, kind, body, notice
):
    key = str(uuid4())
    response = _create(client, parent, client_request_id=key, type="inquiry", body="[TEST] " + body)
    assert response.status_code == 202 and response.json()["request"]["status"] == "received"
    rid = response.json()["request"]["id"]
    path = f"/api/v1/requests/{rid}"
    data = client.get(path, headers=parent).json()
    assert data["request"]["status"] == "sent_or_booked"
    assert [(m["sender_type"], m["sender_role"], m["body"]) for m in data["messages"]] == [
        ("user", "parent", "[TEST] " + body), ("agent", None, notice)]
    assert client.get(path, headers=teacher).json()["messages"] == data["messages"]
    for actor in (teacher, director):
        cards = client.get("/api/v1/cards?size=100", headers=actor).json()["items"]
        assert not [c for c in cards if c["request_id"] == rid]
    history = audit(request_backend, rid, "out_of_scope_answered")
    assert len(history) == 1 and history[0]["detail"]["kind"] == kind
    assert history[0]["actor_type"] == "agent" and history[0]["to_status"] == "sent_or_booked"
    notifications = notices(request_backend, rid)
    assert [(n["kind"], n["recipient_id"], n["card_id"]) for n in notifications] == [
        ("sent_or_booked", seed.PARENT, None)]
    again = _create(client, parent, client_request_id=key, type="inquiry", body="[TEST] " + body)
    assert again.status_code == 200 and again.json()["request"]["status"] == "sent_or_booked"
    assert client.get(path, headers=parent).json() == data
    assert notices(request_backend, rid) == notifications


@pytest.mark.parametrize("body,topic", [
    ("다른 아이랑 다퉜다는데 무슨 일인지 알려주세요.", "peer_conflict"),
    ("다른 아이와 친구 관계 내용을 알려주세요.", "peer_conflict"),
    ("다른 아이 안전 수칙 내용을 알려주세요.", "safety"),
    ("다른 아이 감기 위생 내용을 알려주세요.", "health_hygiene"),
    ("우리 아이 반을 옮기려고 다른 반 내용을 알려주세요.", "other"),
    ("우리 애 반을 옮기려고 다른 반 내용을 알려주세요.", "other"),
    ("저희 아이 반을 옮기려고 다른 반 내용을 알려주세요.", "other"),
])
def test_out_of_scope_child_topics_and_own_child_still_go_to_teacher(
    client, parent, request_backend, body, topic
):
    rid = _create(client, parent, type="inquiry", body="[TEST] " + body).json()["request"]["id"]
    data = client.get(f"/api/v1/requests/{rid}", headers=parent).json()
    assert data["request"]["status"] == "awaiting_review" and len(data["messages"]) == 1
    card = reply_card(request_backend, rid)
    assert card["assignee_id"] == seed.TEACHER and card["status"] == "pending"
    assert audit(request_backend, rid, "out_of_scope_answered") == []
    if request_backend == "mock":
        req = store.get_request(UUID(rid)).__dict__
    else:
        with transaction() as connection:
            req = connection.execute(text("SELECT * FROM requests WHERE id=:id"), {"id": rid}).mappings().one()
    assert (req["topic_key"], req["risk_level"]) == (topic, "normal")
    assert [(n["kind"], n["recipient_id"]) for n in notices(request_backend, rid)] == [("new_card", seed.TEACHER)]


@pytest.mark.parametrize("body,risk,notice_kind", [
    ("원비 결제해 주세요. 아이가 다쳤어요.", "urgent", "urgent_complaint"),
    ("원비 결제해 주세요. 판단 필요해요.", "uncertain", "uncertain_complaint"),
])
def test_out_of_scope_inquiry_prioritizes_risk(client, parent, teacher, director, request_backend, body, risk, notice_kind):
    rid = _create(client, parent, type="inquiry", body="[TEST] " + body).json()["request"]["id"]
    data = client.get(f"/api/v1/requests/{rid}", headers=parent).json()
    assert data["request"]["status"] == "escalated" and len(data["messages"]) == 1
    card = reply_card(request_backend, rid)
    assert not card["draft"].get("text") and card["check_result"] is None
    reports = client.get("/api/v1/cards?size=100", headers=director).json()["items"]
    assert any(c["request_id"] == rid and c["kind"] == "director_report" for c in reports)
    detail = client.get(f"/api/v1/cards/{card['id']}", headers=teacher).json()
    assert detail["request"]["risk_level"] == risk
    assert audit(request_backend, rid, "out_of_scope_answered") == []
    assert {(n["kind"], n["recipient_id"]) for n in notices(request_backend, rid)} == {
        (notice_kind, seed.TEACHER), (notice_kind, seed.DIRECTOR)}


def test_out_of_scope_consultation_other_teacher_keeps_homeroom_slot_flow(client, parent, teacher, request_backend):
    rid = _create(client, parent, type="consultation", body="[TEST] 옆 반 선생님과 상담하고 싶어요.").json()["request"]["id"]
    path = f"/api/v1/requests/{rid}"
    data = client.get(path, headers=parent).json()
    assert data["request"]["status"] == "needs_info" and len(data["consultation"]["slots"]) == 3
    assert [(m["sender_type"], m["sender_role"]) for m in data["messages"]] == [("user", "parent"), ("agent", None)]
    assert data["messages"][-1]["body"] == "상담은 담임 선생님과 잡을 수 있어요."
    cards = client.get("/api/v1/cards?size=100", headers=teacher).json()["items"]
    cards = [c for c in cards if c["request_id"] == rid]
    assert len(cards) == 1 and cards[0]["kind"] == "consult_slots" and cards[0]["assignee"]["id"] == str(seed.TEACHER)
    slot = data["consultation"]["slots"][0]["id"]
    assert client.post(path + "/slot-choices", headers=parent, json={"slot_ids": [slot]}).status_code == 200
    booked = client.post(f"/api/v1/cards/{cards[0]['id']}/bookings", headers=teacher, json={"version": 1, "slot_id": slot})
    assert booked.status_code == 200, booked.text
    assert len(client.get(path, headers=parent).json()["messages"]) == 2
    assert [n["kind"] for n in notices(request_backend, rid)] == ["needs_info", "new_card", "consultation_booked"]


@pytest.mark.parametrize("kind", ["complaint", "consultation"])
def test_out_of_scope_payment_keeps_complaint_and_consultation_flow(client, parent, teacher, request_backend, kind):
    rid = _create(client, parent, type=kind, body="[TEST] 원비 결제해 주세요.").json()["request"]["id"]
    data = client.get(f"/api/v1/requests/{rid}", headers=parent).json()
    assert data["request"]["status"] == ("awaiting_review" if kind == "complaint" else "needs_info")
    assert len(data["messages"]) == 1 and audit(request_backend, rid, "out_of_scope_answered") == []
    cards = client.get("/api/v1/cards?size=100", headers=teacher).json()["items"]
    assert [c["kind"] for c in cards if c["request_id"] == rid] == ["reply_draft" if kind == "complaint" else "consult_slots"]


@pytest.mark.parametrize("kind,status,notified", [
    ("inquiry", "received", False), ("inquiry", "classified", False), ("inquiry", "assigned", False),
    ("inquiry", "awaiting_review", True), ("inquiry", "on_hold", True), ("inquiry", "needs_info", True),
    ("consultation", "needs_info", True), ("consultation", "awaiting_review", True),
    ("consultation", "on_hold", True), ("consultation", "sent_or_booked", True),
])
def test_parent_message_status_routes_without_rerunning_ai(client, parent, teacher, request_backend, kind, status, notified):
    rid = _create(client, parent, type=kind, body="[TEST] 준비물 문의").json()["request"]["id"]
    change_request(request_backend, rid, status=status)
    cards_before = client.get("/api/v1/cards?size=100", headers=teacher).json()["total"]
    before = notices(request_backend, rid)
    response = client.post(f"/api/v1/requests/{rid}/messages", headers=parent, json={"body": "[TEST] 자세한 설명"})
    assert response.status_code == 201, response.text
    new = [n for n in notices(request_backend, rid) if n["id"] not in {n["id"] for n in before}]
    assert [(n["kind"], n["recipient_id"], n["title"]) for n in new] == (
        [("parent_message", seed.TEACHER, "학부모가 글을 더 남겼어요")] if notified else [])
    assert client.get(f"/api/v1/requests/{rid}", headers=parent).json()["request"]["status"] == status
    assert client.get("/api/v1/cards?size=100", headers=teacher).json()["total"] == cards_before
    assert len(audit(request_backend, rid, "message_added")) == 1
    assert len(audit(request_backend, rid, "classified")) == 1


def test_escalated_parent_message_reaches_both_open_card_owners_once(client, parent, teacher, director, request_backend):
    rid = _create(client, parent, body="[TEST] 아이가 다쳤어요").json()["request"]["id"]
    for number in range(2):
        response = client.post(f"/api/v1/requests/{rid}/messages", headers=parent,
                               json={"body": f"[TEST] 추가 상황 {number}"})
        assert response.status_code == 201, response.text
    new = [n for n in notices(request_backend, rid) if n["kind"] == "parent_message"]
    assert sorted(str(n["recipient_id"]) for n in new) == sorted([str(seed.TEACHER), str(seed.DIRECTOR)] * 2)
    assert len({n["dedupe_key"] for n in new}) == 4
    for actor in (teacher, director):
        card = next(c for c in client.get("/api/v1/cards?assignee=me&size=100", headers=actor).json()["items"]
                    if c["request_id"] == rid)
        conversation = client.get(f"/api/v1/cards/{card['id']}", headers=actor).json()["messages"]
        assert len(conversation) == 3 and conversation[-1]["body"] == "[TEST] 추가 상황 1"
    assert client.get(f"/api/v1/requests/{rid}", headers=parent).json()["request"]["status"] == "escalated"


def test_booked_consultation_followup_preserves_booking_and_closed_card(client, parent, teacher, request_backend):
    rid = _create(client, parent, type="consultation", body="[TEST] 상담을 부탁드려요").json()["request"]["id"]
    path = f"/api/v1/requests/{rid}"
    slot = client.get(path, headers=parent).json()["consultation"]["slots"][0]["id"]
    assert client.post(path + "/slot-choices", headers=parent, json={"slot_ids": [slot]}).status_code == 200
    card = next(c for c in client.get("/api/v1/cards?size=100", headers=teacher).json()["items"]
                if c["request_id"] == rid and c["kind"] == "consult_slots")
    booked = client.post(f"/api/v1/cards/{card['id']}/bookings", headers=teacher, json={"version": 1, "slot_id": slot})
    assert booked.status_code == 200, booked.text
    before = client.get(f"/api/v1/cards/{card['id']}", headers=teacher).json()["card"]
    count = len(notices(request_backend, rid))
    response = client.post(path + "/messages", headers=parent, json={"body": "[TEST] 상담에 참고해 주세요"})
    assert response.status_code == 201, response.text
    after = client.get(path, headers=parent).json()
    assert after["request"]["status"] == "sent_or_booked"
    assert after["consultation"]["booking"] == booked.json()["booking"]
    assert client.get(f"/api/v1/cards/{card['id']}", headers=teacher).json()["card"] == before
    assert len(notices(request_backend, rid)) == count + 1
    note = notices(request_backend, rid)[-1]
    assert (note["kind"], note["recipient_id"]) == ("parent_message", seed.TEACHER)


@pytest.mark.parametrize("owner", [seed.TEACHER_OTHER, None, "closed"])
def test_parent_message_uses_open_card_owner_or_director(client, parent, request_backend, owner):
    rid = _create(client, parent, type="inquiry", body="[TEST] 준비물 문의").json()["request"]["id"]
    card = reply_card(request_backend, rid)
    status, assignee = ("done", seed.TEACHER) if owner == "closed" else ("pending" if owner else "unassigned", owner)
    if request_backend == "mock":
        target = store.state().cards[card["id"]]
        target.status, target.assignee_id = status, assignee
    else:
        with transaction() as connection:
            connection.execute(text("UPDATE cards SET status=:status,assignee_id=:owner WHERE id=:id"),
                               {"id": card["id"], "status": status, "owner": assignee})
    response = client.post(f"/api/v1/requests/{rid}/messages", headers=parent, json={"body": "[TEST] 더 적어요"})
    assert response.status_code == 201, response.text
    new = [n for n in notices(request_backend, rid) if n["kind"] == "parent_message"]
    assert [n["recipient_id"] for n in new] == [seed.TEACHER_OTHER if owner == seed.TEACHER_OTHER else seed.DIRECTOR]


@pytest.mark.parametrize("kind", ["inquiry", "complaint"])
def test_sent_reply_reopens_latest_card_without_resending_previous_text(client, parent, teacher, request_backend, kind):
    rid = _create(client, parent, type=kind, body="[TEST] 준비물 문의").json()["request"]["id"]
    old = reply_card(request_backend, rid)
    rejected = decision(client, teacher, old["id"], "reject", reason_code="tone")
    assert rejected.status_code == 200, rejected.text
    cid = rejected.json()["next_card_id"]
    assert decision(client, teacher, cid, "edit_approve", edited_content={"text": "[TEST] 지난번 회신"}).status_code == 200
    before = reply_card(request_backend, rid)
    count = len(notices(request_backend, rid))
    response = client.post(f"/api/v1/requests/{rid}/messages", headers=parent, json={"body": "[TEST] 아직 궁금해요"})
    assert response.status_code == 201, response.text
    data = client.get(f"/api/v1/cards/{cid}", headers=teacher).json()
    assert data["request"]["status"] == "awaiting_review"
    assert data["card"]["status"] == "pending" and data["card"]["version"] == before["version"] + 1
    assert data["card"]["draft"] == {"previous_text": "[TEST] 지난번 회신", "text": ""}
    assert data["card"]["check_result"] is None and "check_unavailable" in data["warnings"]
    assert client.get(f"/api/v1/cards/{old['id']}", headers=teacher).json()["card"]["status"] == "rejected"
    assert data["messages"] == client.get(f"/api/v1/requests/{rid}", headers=parent).json()["messages"]
    assert [(m["sender_type"], m["sender_role"]) for m in data["messages"]] == [
        ("user", "parent"), ("user", "teacher"), ("user", "parent")]
    assert len(notices(request_backend, rid)) == count + 1
    latest = notices(request_backend, rid)[-1]
    assert (latest["kind"], latest["recipient_id"], str(latest["card_id"])) == ("new_card", seed.TEACHER, cid)
    err(decision(client, teacher, cid, version=data["card"]["version"]), 409, "INVALID_TRANSITION")
    assert client.get(f"/api/v1/cards/{cid}", headers=teacher).json() == data
    sent = decision(client, teacher, cid, "edit_approve", version=data["card"]["version"],
                    edited_content={"text": "[TEST] 새로 쓴 회신"})
    assert sent.status_code == 200, sent.text
    messages = client.get(f"/api/v1/requests/{rid}", headers=parent).json()["messages"]
    assert [m["body"] for m in messages if m["sender_role"] == "teacher"] == ["[TEST] 지난번 회신", "[TEST] 새로 쓴 회신"]


@pytest.mark.parametrize("has_teacher", [True, False])
def test_followup_to_cardless_answer_creates_empty_reply(client, parent, teacher, director, request_backend, has_teacher):
    rid = _create(client, parent, type="inquiry", body="[TEST] 원비 결제해 주세요.").json()["request"]["id"]
    assert client.get(f"/api/v1/requests/{rid}", headers=parent).json()["request"]["status"] == "sent_or_booked"
    before = len(notices(request_backend, rid))
    if request_backend == "mock":
        if not has_teacher:
            store.state().classroom_staff[:] = [s for s in store.state().classroom_staff if s.classroom_id != seed.CLASS_STAR]
    else:
        with transaction() as connection:
            if not has_teacher:
                connection.execute(text("DELETE FROM classroom_staff WHERE classroom_id=:id"), {"id": seed.CLASS_STAR})
    response = client.post(f"/api/v1/requests/{rid}/messages", headers=parent, json={"body": "[TEST] 우리 아이 일도 물어요"})
    assert response.status_code == 201, response.text
    card = reply_card(request_backend, rid)
    assert card["status"] == ("pending" if has_teacher else "unassigned")
    assert card["assignee_id"] == (seed.TEACHER if has_teacher else None)
    assert not card["draft"].get("text") and card["check_result"] is None
    data = client.get(f"/api/v1/cards/{card['id']}", headers=teacher if has_teacher else director).json()
    assert data["request"]["status"] == "awaiting_review"
    assert [(m["sender_type"], m["sender_role"]) for m in data["messages"]] == [
        ("user", "parent"), ("agent", None), ("user", "parent")]
    assert len(notices(request_backend, rid)) == before + 1
    note = notices(request_backend, rid)[-1]
    assert (note["kind"], note["recipient_id"]) == ("new_card", seed.TEACHER if has_teacher else seed.DIRECTOR)


def test_staff_request_list_agent_scope_and_names(client, parent, parent_other, teacher, teacher_other, director):
    ids = [_create(client, actor, type="inquiry", body="[TEST] 원비 결제해 주세요.", child_id=str(child)).json()["request"]["id"]
           for actor, child in ((parent, seed.CHILD), (parent_other, seed.CHILD_OTHER))]
    def listed(actor):
        response = client.get("/api/v1/requests?answered_by=agent&size=100", headers=actor)
        assert response.status_code == 200, response.text
        return response.json()["items"]
    [own] = listed(teacher)
    assert own["id"] == ids[0] and own["classroom_id"] == str(seed.CLASS_STAR)
    assert (own["child_id"], own["child_name"], own["requester_name"]) == (str(seed.CHILD), "하늘", "하늘이 보호자")
    assert own["answered_by"] == "agent" and own["status_label"] == "발송됨" and own["next_action"] is None
    assert [r["id"] for r in listed(teacher_other)] == [ids[1]]
    assert {r["id"] for r in listed(director)} == set(ids)


def test_staff_request_list_answer_filters_and_all_types(client, parent, teacher, request_backend):
    baseline = {r["id"] for r in client.get("/api/v1/requests?answered_by=staff&size=100", headers=teacher).json()["items"]}
    pending = _create(client, parent, type="inquiry").json()["request"]["id"]
    sent = _create(client, parent).json()["request"]["id"]
    change_request(request_backend, sent, status="sent_or_booked")
    finished = _create(client, parent, type="pickup").json()["request"]["id"]
    change_request(request_backend, finished, status="completed")
    _create(client, parent, type="medication")
    _create(client, parent, type="consultation")
    rows = client.get("/api/v1/requests?size=100", headers=teacher).json()["items"]
    assert {r["type"] for r in rows} == {"inquiry", "complaint", "consultation", "medication", "pickup"}
    assert next(r for r in rows if r["id"] == pending)["answered_by"] is None
    assert next(r for r in rows if r["type"] == "medication")["next_action"] == "confirm"
    answered = client.get("/api/v1/requests?answered_by=staff&size=100", headers=teacher).json()["items"]
    assert {r["id"] for r in answered} == baseline | {sent, finished}
    assert all(r["answered_by"] == "staff" for r in answered)
    assert client.get("/api/v1/requests?answered_by=agent", headers=teacher).json()["total"] == 0


def test_staff_request_list_combines_filters_and_pagination(client, parent, teacher, request_backend):
    ids = [_create(client, parent, type="inquiry").json()["request"]["id"] for _ in range(3)]
    for rid in ids:
        change_request(request_backend, rid, status="sent_or_booked")
    query = {"classroom_id": str(seed.CLASS_STAR), "type": "inquiry", "status": "sent_or_booked",
             "answered_by": "staff", "sort": "created_at", "size": 1}
    pages = [client.get("/api/v1/requests", headers=teacher, params={**query, "page": p}).json() for p in range(1, 5)]
    assert all(p["total"] == 3 and p["size"] == 1 for p in pages)
    assert [p["items"][0]["id"] for p in pages[:3]] == ids and pages[3]["items"] == []
    query.update(sort="-created_at", size=100)
    assert [r["id"] for r in client.get("/api/v1/requests", headers=teacher, params=query).json()["items"]] == ids[::-1]
    query["classroom_id"] = str(seed.CLASS_SUN)
    err(client.get("/api/v1/requests", headers=teacher, params=query), 404, "NOT_FOUND")


@pytest.mark.parametrize("period", ["expired", "future", "today"])
def test_staff_request_list_checks_assignment_dates(client, parent, teacher, director, request_backend, period):
    from datetime import timedelta
    today = store.now().date()
    start, end = {"expired": (None, today-timedelta(days=1)),
                  "future": (today+timedelta(days=1), None), "today": (today, today)}[period]
    rid = _create(client, parent, type="inquiry", body="[TEST] 원비 결제해 주세요.").json()["request"]["id"]
    if request_backend == "mock":
        assignment = next(s for s in store.state().classroom_staff if s.user_id == seed.TEACHER)
        assignment.valid_from, assignment.valid_to = start, end
    else:
        with transaction() as connection:
            connection.execute(text("UPDATE classroom_staff SET valid_from=:start,valid_to=:end WHERE user_id=:user"),
                               {"start": start, "end": end, "user": seed.TEACHER})
    listed = client.get("/api/v1/requests?answered_by=agent", headers=teacher).json()["items"]
    assert (rid in [r["id"] for r in listed]) == (period == "today")
    assert rid in [r["id"] for r in client.get("/api/v1/requests?answered_by=agent", headers=director).json()["items"]]


def test_staff_request_list_preserves_parent_bytes_and_validates_queries(client, parent, teacher):
    _create(client, parent)
    original = client.get("/api/v1/requests", headers=parent)
    filtered = client.get("/api/v1/requests", headers=parent,
                          params={"answered_by": "agent", "classroom_id": str(seed.CLASS_SUN), "type": "pickup"})
    assert filtered.content == original.content
    assert set(original.json()["items"][0]) == {"id", "type", "title", "status", "updated_at", "status_label", "next_action", "hold_until"}
    for query in ({"answered_by": "unknown"}, {"classroom_id": "bad"}, {"type": "unknown"}):
        for actor in (parent, teacher):
            err(client.get("/api/v1/requests", headers=actor, params=query), 422, "VALIDATION_FAILED")


def test_staff_request_list_keeps_answer_history_when_reopened(client, parent, teacher):
    agent = _create(client, parent, type="inquiry", body="[TEST] 원비 결제해 주세요.").json()["request"]["id"]
    staff = _create(client, parent, type="inquiry").json()["request"]["id"]
    card = next(c for c in client.get("/api/v1/cards?size=100", headers=teacher).json()["items"] if c["request_id"] == staff)
    assert decision(client, teacher, card["id"]).status_code == 200
    for rid in (agent, staff):
        assert client.post(f"/api/v1/requests/{rid}/messages", headers=parent, json={"body": "[TEST] 추가 질문"}).status_code == 201
    for answer, rid in (("agent", agent), ("staff", staff)):
        listed = client.get(f"/api/v1/requests?answered_by={answer}&status=awaiting_review", headers=teacher).json()["items"]
        assert [(r["id"], r["status"]) for r in listed] == [(rid, "awaiting_review")]
