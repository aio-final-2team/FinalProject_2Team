"""T27-b의 HTTP 계약을 모의 저장소와 PostgreSQL에서 함께 확인해요."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text

from app import backend
from app.core.db import transaction
from app.core.schedule import KST
from app.mock import seed, store
from tests.integration.api.helpers import BASE, decision, err


@pytest.fixture(autouse=True, params=["mock", "db"])
def card_backend(request, monkeypatch):
    if request.param == "db":
        request.getfixturevalue("seeded_db")
        from app.core import users
        from app.modules.cards import cards, card_views
        from app.modules.notifications import notifications
        from app.modules.requests import requests
    else:
        from app.mock import cards, card_views, notifications, request_actions as requests

        users = store
    for name, module in dict(
        users=users, cards=cards, card_views=card_views, notifications=notifications, request_actions=requests
    ).items():
        monkeypatch.setattr(backend, name, module)
    return request.param


def create(client, parent, teacher, type="complaint", body="[TEST] 버스가 늦었어요"):
    response = client.post(
        BASE + "/requests",
        headers=parent,
        json={"client_request_id": str(uuid4()), "child_id": str(seed.CHILD), "type": type, "body": body},
    )
    assert response.status_code == 202, response.text
    rid = response.json()["request"]["id"]
    data = client.get(BASE + "/cards", headers=teacher, params={"size": 100}).json()
    cid = next(row["id"] for row in data["items"] if row["request_id"] == rid and row["kind"] != "director_report")
    return rid, cid


def detail(client, teacher, cid):
    response = client.get(f"{BASE}/cards/{cid}", headers=teacher)
    assert response.status_code == 200, response.text
    return response.json()


def test_reply_approval_confirmation_completion_and_event_order(client, parent, teacher, director):
    rid, cid = create(client, parent, teacher)
    assert "모의 초안" not in client.get(f"{BASE}/requests/{rid}", headers=parent).text
    result = decision(client, teacher, cid)
    assert result.status_code == 200, result.text
    assert result.json()["card"]["version"] == 2
    events = detail(client, teacher, cid)["timeline"]
    assert [ev["action"] for ev in events][-2:] == ["approved", "sent"]
    assert [(ev["from_status"], ev["to_status"]) for ev in events[-2:]] == [
        ("awaiting_review", "approved"),
        ("approved", "sent_or_booked"),
    ]
    assert events[-1]["id"] > events[-2]["id"]
    assert cid in [row["id"] for row in client.get(BASE + "/cards?filter=in_progress", headers=teacher).json()["items"]]
    sent = client.get(f"{BASE}/requests/{rid}", headers=parent).json()
    assert sent["messages"][-1]["body"] == detail(client, teacher, cid)["card"]["draft"]["text"]
    confirmed = client.post(f"{BASE}/requests/{rid}/confirm", headers=parent)
    assert confirmed.status_code == 200
    assert client.post(f"{BASE}/requests/{rid}/confirm", headers=parent).json() == confirmed.json()
    assert cid in [
        row["id"] for row in client.get(BASE + "/cards?filter=needs_review", headers=teacher).json()["items"]
    ]
    assert decision(client, teacher, cid, "complete", version=2).status_code == 200
    assert [ev["action"] for ev in detail(client, teacher, cid)["timeline"]][-2:] == ["parent_confirmed", "completed"]
    assert client.get(BASE + "/overview", headers=director).json()["completed_unconfirmed"] == 0


def test_unconfirmed_completion_requires_reason_and_counts_once(client, parent, teacher, director):
    rid, cid = create(client, parent, teacher)
    err(decision(client, teacher, cid, "complete"), 409, "INVALID_TRANSITION")
    assert decision(client, teacher, cid).status_code == 200
    before = detail(client, teacher, cid)
    err(decision(client, teacher, cid, "complete", version=2), 409, "REASON_REQUIRED")
    assert detail(client, teacher, cid) == before
    result = decision(client, teacher, cid, "complete", version=2, reason_text="[TEST] 전화로 설명함")
    assert result.status_code == 200, result.text
    overview = client.get(BASE + "/overview", headers=director).json()
    assert overview["completed_unconfirmed"] == 1 and overview["done_today"] >= 1
    err(decision(client, teacher, cid, "complete", version=2, reason_text="[TEST] 재시도"), 409, "ALREADY_DECIDED")
    assert client.get(BASE + "/overview", headers=director).json()["completed_unconfirmed"] == 1
    err(client.get(BASE + "/overview", headers=teacher), 403, "FORBIDDEN_ROLE")


@pytest.mark.parametrize(
    "choice,extra",
    [
        ("approve", {}),
        ("edit_approve", {"edited_content": {"text": "[TEST] 답"}}),
        ("complete", {"reason_text": "[TEST] 완료"}),
    ],
)
def test_director_cannot_decide_complaint_reply(client, parent, teacher, director, choice, extra):
    _, cid = create(client, parent, teacher)
    err(decision(client, director, cid, choice, **extra), 403, "FORBIDDEN_ROLE")


def test_version_and_concurrent_approval_only_sends_once(client, parent, teacher):
    _, cid = create(client, parent, teacher)
    result = decision(client, teacher, cid, version=9)
    err(result, 409, "CARD_VERSION_CONFLICT")
    assert result.json()["error"]["details"] == {"current_version": 1}
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: decision(client, teacher, cid), range(2)))
    assert sorted(r.status_code for r in responses) == [200, 409]
    assert next(r for r in responses if r.status_code == 409).json()["error"]["code"] == "ALREADY_DECIDED"
    saved = detail(client, teacher, cid)
    assert len([e for e in saved["timeline"] if e["action"] == "sent"]) == 1
    assert len([e for e in saved["timeline"] if e["action"] == "approved"]) == 1


def test_hold_resume_and_private_reason(client, parent, teacher):
    rid, cid = create(client, parent, teacher)
    until = (datetime.now(KST).date() + timedelta(days=2)).isoformat()
    result = decision(client, teacher, cid, "hold", reason_text="[TEST] 내부 확인 비공개", hold_until=until)
    assert result.status_code == 200, result.text
    assert result.json()["card"]["status"] == "on_hold"
    saved = client.get(f"{BASE}/requests/{rid}", headers=parent)
    assert saved.json()["request"]["hold_until"] == until and "내부 확인 비공개" not in saved.text
    assert "내부 확인 비공개" not in client.get(BASE + "/notifications", headers=parent).text
    assert cid in [row["id"] for row in client.get(BASE + "/cards?filter=on_hold", headers=teacher).json()["items"]]
    assert decision(client, teacher, cid, "resume", version=2).status_code == 200
    assert detail(client, teacher, cid)["card"]["version"] == 3
    assert decision(client, teacher, cid, version=3).status_code == 200


def test_reject_then_dismiss_keeps_old_card_done(client, parent, teacher):
    rid, cid = create(client, parent, teacher)
    rejected = decision(client, teacher, cid, "reject", reason_code="tone")
    assert rejected.status_code == 200, rejected.text
    next_id = rejected.json()["next_card_id"]
    assert next_id and next_id != cid
    assert detail(client, teacher, next_id)["request"]["status"] == "awaiting_review"
    assert decision(client, teacher, next_id).status_code == 200
    done = client.get(BASE + "/cards?filter=done&size=100", headers=teacher).json()["items"]
    progress = client.get(BASE + "/cards?filter=in_progress&size=100", headers=teacher).json()["items"]
    assert cid in [c["id"] for c in done] and next_id in [c["id"] for c in progress]
    rid, cid = create(client, parent, teacher, body="[TEST] 별도 민원")
    result = decision(client, teacher, cid, "dismiss", reason_code="other", reason_text="[TEST] 업무 범위 밖")
    assert result.status_code == 200, result.text
    assert client.get(f"{BASE}/requests/{rid}", headers=parent).json()["rejection"] == {
        "reason_code": "other",
        "reason_text": "[TEST] 업무 범위 밖",
    }


def test_escalation_instruction_reassignment_then_edit_approval(client, parent, teacher, teacher_other, director):
    rid, cid = create(client, parent, teacher)
    report = decision(client, teacher, cid, "escalate")
    assert report.status_code == 200, report.text
    report_id = report.json()["next_card_id"]
    err(decision(client, teacher, report_id), 403, "FORBIDDEN_ROLE")
    err(
        client.post(
            f"{BASE}/cards/{report_id}/instructions", headers=teacher, json={"version": 1, "instruction": "[TEST] 지시"}
        ),
        403,
        "FORBIDDEN_ROLE",
    )
    result = client.post(
        f"{BASE}/cards/{report_id}/instructions",
        headers=director,
        json={"version": 1, "instruction": "[TEST] 확인 뒤 안내"},
    )
    assert result.status_code == 200, result.text
    assert result.json()["card"]["status"] == "done"
    saved = detail(client, teacher, cid)
    assert saved["director_instruction"]["by"]["id"] == str(seed.DIRECTOR)
    assert saved["director_instruction"]["text"] == "[TEST] 확인 뒤 안내"
    assert saved["card"]["version"] == 2
    result = client.post(
        f"{BASE}/cards/{cid}/reassign",
        headers=director,
        json={"assignee_id": str(seed.TEACHER_OTHER), "reason": "[TEST] 담당 부재"},
    )
    assert result.status_code == 200, result.text
    assert result.json()["card"]["version"] == 3
    assert detail(client, teacher_other, cid)["request"]["id"] == rid
    assert client.get(f"{BASE}/requests/{rid}", headers=teacher_other).status_code == 200
    assert cid in [c["id"] for c in client.get(BASE + "/cards?assignee=me", headers=teacher_other).json()["items"]]
    reassignment = client.get(BASE + "/overview", headers=director).json()["reassignments"][-1]
    assert (reassignment["from"], reassignment["to"]) == (str(seed.TEACHER), str(seed.TEACHER_OTHER))
    result = decision(
        client, teacher_other, cid, "edit_approve", version=3, edited_content={"text": "[TEST] 직접 쓴 회신"}
    )
    assert result.status_code == 200, result.text
    assert client.get(f"{BASE}/requests/{rid}", headers=parent).json()["messages"][-1]["body"] == "[TEST] 직접 쓴 회신"


def test_reclassification_updates_deadlines_without_duplicate_report(client, parent, teacher, director):
    rid, cid = create(client, parent, teacher, body="[TEST] 아이가 다쳤어요")
    for version, risk, category in ((1, "normal", None), (2, "urgent", "child_safety"), (3, "urgent", "privacy_leak")):
        result = client.post(
            f"{BASE}/cards/{cid}/reclassify",
            headers=teacher,
            json={"version": version, "risk_level": risk, "risk_category": category, "reason": "[TEST] 사람이 확인"},
        )
        assert result.status_code == 200, result.text
        assert result.json()["request"]["risk_level"] == risk
    cards = client.get(BASE + "/cards?size=100", headers=director).json()["items"]
    reports = [c for c in cards if c["request_id"] == rid and c["kind"] == "director_report"]
    assert len(reports) == 1
    assert next(c for c in cards if c["id"] == cid)["due_at"] == reports[0]["due_at"]
    events = detail(client, teacher, cid)["timeline"]
    assert len([ev for ev in events if ev["action"] == "risk_reclassified"]) == 3


def test_inbox_filters_counts_sort_and_large_page(client, parent, teacher):
    create(client, parent, teacher, body="[TEST] 아이가 다쳤어요")
    response = client.get(BASE + "/cards", headers=teacher, params={"size": 100})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["items"][0]["is_urgent"]
    assert set(data["counts"]) == {"unassigned", "needs_review", "uncertain", "on_hold", "in_progress", "done"}
    assert data == client.get(BASE + "/cards?request_type=all&size=100", headers=teacher).json()
    partition = []
    for key, count in data["counts"].items():
        page = client.get(BASE + "/cards", headers=teacher, params={"filter": key, "size": 100}).json()
        assert page["total"] == count
        partition += [c["id"] for c in page["items"]]
    assert len(partition) == len(set(partition))
    review = client.get(BASE + "/cards?filter=needs_review&size=100", headers=teacher).json()
    limited = client.get(BASE + "/cards?filter=needs_review&request_type=complaint", headers=teacher).json()
    assert review["type_counts"] == limited["type_counts"]
    assert limited["total"] == limited["type_counts"]["complaint"]
    huge = client.get(BASE + "/cards", headers=teacher, params={"page": 10**30, "size": 100}).json()
    assert huge["items"] == [] and huge["total"] == data["total"]


def test_card_stream_scope_and_replay(client, parent, parent_other, teacher, teacher_other):
    rid, cid = create(client, parent, teacher, type="inquiry")
    response = client.get(f"{BASE}/cards/{cid}/stream", headers=teacher)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    frames = [
        (part.splitlines()[0][7:], json.loads(part.splitlines()[1][6:])) for part in response.text.strip().split("\n\n")
    ]
    assert [d["stage"] for ev, d in frames if ev == "stage"] == ["classifying", "searching", "drafting", "checking"]
    assert (
        "".join(d["text"] for ev, d in frames if ev == "token") == detail(client, teacher, cid)["card"]["draft"]["text"]
    )
    assert frames[-1] == ("done", {"request_status": "awaiting_review"})
    assert frames[-2][0] == "card" and frames[-2][1]["id"] == cid
    for actor, status, code in ((parent, 403, "FORBIDDEN_ROLE"), (teacher_other, 404, "NOT_FOUND")):
        err(client.get(f"{BASE}/cards/{cid}", headers=actor), status, code)
        err(client.get(f"{BASE}/cards/{cid}/stream", headers=actor), status, code)
    err(client.get(f"{BASE}/cards/{uuid4()}", headers=teacher), 404, "NOT_FOUND")
    assert "모의 초안" not in client.get(f"{BASE}/requests/{rid}/stream", headers=parent).text


def test_notifications_reserved_owner_sort_page_and_idempotent_read(
    client, parent, parent_other, teacher, card_backend
):
    rid, cid = create(client, parent, teacher, type="inquiry")
    assert decision(client, teacher, cid).status_code == 200
    response = client.get(BASE + "/notifications?size=100", headers=parent)
    assert response.status_code == 200, response.text
    rows = response.json()["items"]
    note = next(n for n in rows if n["request_id"] == rid and n["kind"] == "sent_or_booked")
    nid = note["id"]
    first = client.post(f"{BASE}/notifications/{nid}/read", headers=parent)
    assert first.status_code == 200 and first.json()["notification"]["read_at"].endswith("+09:00")
    assert client.post(f"{BASE}/notifications/{nid}/read", headers=parent).json() == first.json()
    err(client.post(f"{BASE}/notifications/{nid}/read", headers=parent_other), 404, "NOT_FOUND")
    if card_backend == "mock":
        store.state().notifications[nid].deliver_after = datetime.now(KST) + timedelta(days=1)
    else:
        with transaction() as connection:
            connection.execute(
                text("UPDATE notifications SET deliver_after=now()+interval '1 day' WHERE id=:id"), {"id": nid}
            )
    assert nid not in [n["id"] for n in client.get(BASE + "/notifications?size=100", headers=parent).json()["items"]]
    err(client.post(f"{BASE}/notifications/{nid}/read", headers=parent), 404, "NOT_FOUND")
    for sort in ("created_at", "-created_at"):
        data = client.get(
            BASE + "/notifications", headers=parent, params={"sort": sort, "size": 1, "page": 10**30}
        ).json()
        assert data["items"] == []


@pytest.mark.parametrize(
    "query",
    [{"filter": "bad"}, {"risk_level": "normal"}, {"kind": "bad"}, {"assignee": "other"}, {"size": 101}, {"page": 0}],
)
def test_inbox_query_validation(client, teacher, query):
    err(client.get(BASE + "/cards", headers=teacher, params=query), 422, "VALIDATION_FAILED")


@pytest.mark.parametrize(
    "choice,extra",
    [("reject", {}), ("dismiss", {}), ("hold", {"reason_text": "[TEST] 보류"}), ("edit_approve", {}), ("unknown", {})],
)
def test_decision_body_validation(client, parent, teacher, choice, extra):
    _, cid = create(client, parent, teacher)
    err(decision(client, teacher, cid, choice, **extra), 422, "VALIDATION_FAILED")


def test_no_text_draft_cannot_be_approved(client, parent, teacher, director):
    _, cid = create(client, parent, teacher, body="[TEST] 아이가 다쳤어요")
    reports = client.get(BASE + "/cards?kind=director_report&size=100", headers=director).json()["items"]
    rid = detail(client, teacher, cid)["request"]["id"]
    report = next(c for c in reports if c["request_id"] == rid)
    assert (
        client.post(
            f"{BASE}/cards/{report['id']}/instructions",
            headers=director,
            json={"version": 1, "instruction": "[TEST] 확인해 줘요"},
        ).status_code
        == 200
    )
    err(decision(client, teacher, cid), 409, "INVALID_TRANSITION")
    assert detail(client, teacher, cid)["card"]["version"] == 1
