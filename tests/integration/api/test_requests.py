"""요청 만들기·상세(API 설계 문서 3.1·3.2)와 공통 규칙(1.3·1.4)."""

from uuid import uuid4

from app.mock import seed


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
                      json={"client_request_id": "short", "type": "medication", "body": "", "child_id": "x"})
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
