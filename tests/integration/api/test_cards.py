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
from tests import fake_supervisor
from tests.integration.api.helpers import BASE, decision, err
from tests.integration.api.test_requests import notices


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
    # 학부모 글과 담임이 승인해 나간 답은 둘 다 user지만, 역할로 말풍선을 나눌 수 있어요.
    assert [(m["sender_type"], m["sender_role"]) for m in sent["messages"]] == [("user", "parent"), ("user", "teacher")]
    assert client.get(f"{BASE}/requests/{rid}", headers=teacher).json()["messages"] == sent["messages"]
    confirmed = client.post(f"{BASE}/requests/{rid}/confirm", headers=parent)
    assert confirmed.status_code == 200
    assert client.post(f"{BASE}/requests/{rid}/confirm", headers=parent).json() == confirmed.json()
    confirmed_view = client.get(f"{BASE}/requests/{rid}", headers=parent).json()
    label = "확인함 · 선생님이 마무리하고 있어요"
    assert confirmed_view["request"]["status_label"] == label
    assert confirmed_view["timeline"][-1]["label"] == label
    listed = client.get(BASE + "/requests?size=100", headers=parent).json()["items"]
    assert next(row for row in listed if row["id"] == rid)["status_label"] == label
    assert client.get(f"{BASE}/requests/{rid}", headers=teacher).json()["request"]["status_label"] == "발송됨"
    assert cid in [
        row["id"] for row in client.get(BASE + "/cards?filter=needs_review", headers=teacher).json()["items"]
    ]
    assert decision(client, teacher, cid, "complete", version=2).status_code == 200
    assert client.get(f"{BASE}/requests/{rid}", headers=parent).json()["request"]["status_label"] == "완료"
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
    assert decision(client, teacher, next_id, "edit_approve", edited_content={"text": "[TEST] 다시 쓴 답"}).status_code == 200
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


def test_escalation_instruction_reassignment_then_edit_approval(client, parent, teacher, teacher_other, director, card_backend):
    rid, cid = create(client, parent, teacher)
    report = decision(client, teacher, cid, "escalate")
    assert report.status_code == 200, report.text
    report_id = report.json()["next_card_id"]
    events = detail(client, director, report_id)["timeline"]
    assert [e["detail"]["reason"] for e in events if e["action"] == "escalated"] == ["manual"]
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
    reassigned = [n for n in notices(card_backend, rid) if n["kind"] == "reassigned"]
    assert len(reassigned) == 1
    assert (str(reassigned[0]["recipient_id"]), str(reassigned[0]["card_id"]), reassigned[0]["title"]) == (
        str(seed.TEACHER_OTHER), cid, "요청이 배정됐어요")
    assert detail(client, teacher_other, cid)["request"]["id"] == rid
    assert client.get(f"{BASE}/requests/{rid}", headers=teacher_other).status_code == 200
    # 재배정받은 다른 반 요청은 교직원 요청 목록에도 나온다(기획서 2.4). 원래 담임 목록에도 그대로 남는다.
    for actor in (teacher_other, teacher):
        assert rid in [r["id"] for r in client.get(BASE + "/requests?size=100", headers=actor).json()["items"]]
    assert cid in [c["id"] for c in client.get(BASE + "/cards?assignee=me", headers=teacher_other).json()["items"]]
    reassignment = client.get(BASE + "/overview", headers=director).json()["reassignments"][-1]
    assert (reassignment["from"], reassignment["to"]) == (str(seed.TEACHER), str(seed.TEACHER_OTHER))
    result = decision(
        client, teacher_other, cid, "edit_approve", version=3, edited_content={"text": "[TEST] 직접 쓴 회신"}
    )
    assert result.status_code == 200, result.text
    assert client.get(f"{BASE}/requests/{rid}", headers=parent).json()["messages"][-1]["body"] == "[TEST] 직접 쓴 회신"


@pytest.mark.parametrize("code,label,reason", [
    ("wrong_fact", "사실이 틀림", None), ("tone", "말투", None),
    ("missing_info", "근거·정보 부족", None), ("privacy", "개인정보", None),
    ("policy", "원 방침과 다름", "[TEST] 원에서 별도로 안내해요"),
    ("slot_unavailable", "상담 시간 안 됨", None), ("room_unavailable", "상담실 없음", None),
    ("other", "기타", "[TEST] 업무 범위 밖이에요"),
])
def test_dismiss_notification_uses_reason_label_and_text(client, parent, teacher, card_backend, code, label, reason):
    rid, cid = create(client, parent, teacher, type="inquiry", body="[TEST] 반려 사유 표시")
    extra = {"reason_text": reason} if reason else {}
    response = decision(client, teacher, cid, "dismiss", reason_code=code, **extra)
    assert response.status_code == 200, response.text
    rejected = [n for n in notices(card_backend, rid) if n["kind"] == "rejected"]
    assert len(rejected) == 1
    assert str(rejected[0]["recipient_id"]) == str(seed.PARENT)
    assert rejected[0]["body"] == (f"{label} · {reason}" if reason else label)


@pytest.mark.parametrize("body", ["[TEST] 일반 문의", "[TEST] 아이가 다쳤어요", "[TEST] 판단 필요 문의"])
def test_escalated_reply_waits_in_progress_until_director_instruction(client, parent, teacher, director, monkeypatch, body):
    fake_supervisor.install(monkeypatch)  # 판단 필요는 가짜 감독 AI가 정해요
    rid, cid = create(client, parent, teacher, type="inquiry", body=body)
    if detail(client, teacher, cid)["request"]["status"] != "escalated":
        response = decision(client, teacher, cid, "escalate")
        assert response.status_code == 200, response.text
    progress = client.get(BASE + "/cards?filter=in_progress&size=100", headers=teacher).json()["items"]
    assert next(c for c in progress if c["id"] == cid)["status_label"] == "원장 확인 중"
    assert detail(client, teacher, cid)["request"]["status_label"] == "원장 확인 중"
    for bucket in ("needs_review", "uncertain"):
        rows = client.get(f"{BASE}/cards?filter={bucket}&size=100", headers=teacher).json()["items"]
        assert cid not in {c["id"] for c in rows}
    report = next(c for c in client.get(BASE + "/cards?kind=director_report&size=100", headers=director).json()["items"]
                  if c["request_id"] == rid)
    report_bucket = "uncertain" if report["risk_level"] == "uncertain" else "needs_review"
    rows = client.get(f"{BASE}/cards?filter={report_bucket}&size=100", headers=director).json()["items"]
    assert report["id"] in {c["id"] for c in rows}
    response = client.post(f"{BASE}/cards/{report['id']}/instructions", headers=director,
                           json={"version": 1, "instruction": "[TEST] 확인 후 안내해요"})
    assert response.status_code == 200, response.text
    reply_bucket = "uncertain" if report["risk_level"] == "uncertain" else "needs_review"
    rows = client.get(f"{BASE}/cards?filter={reply_bucket}&size=100", headers=teacher).json()["items"]
    assert next(c for c in rows if c["id"] == cid)["status_label"] == "확인 필요"


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


@pytest.mark.parametrize("target_report", [False, True])
def test_urgent_reclassification_clears_reply_and_check_before_fresh_approval(
    client, parent, teacher, director, target_report
):
    rid, cid = create(client, parent, teacher)
    before = detail(client, teacher, cid)["card"]
    assert before["draft"]["text"] and before["check_result"]["passed"]
    target, version = cid, 1
    if target_report:
        raised = decision(client, teacher, cid, "escalate")
        assert raised.status_code == 200, raised.text
        target, version = raised.json()["next_card_id"], 2
    response = client.post(f"{BASE}/cards/{target}/reclassify", headers=director, json={
        "version": 1, "risk_level": "urgent", "risk_category": "child_safety", "reason": "[TEST] 긴급 재분류"})
    assert response.status_code == 200, response.text
    saved = detail(client, director, cid)
    assert saved["card"]["draft"]["text"] == "" and saved["card"]["check_result"] is None
    assert saved["card"]["version"] == version + 1
    assert saved["card"]["draft"]["summary"] == before["draft"]["summary"]
    reports = [c for c in client.get(BASE+"/cards?size=100", headers=director).json()["items"]
               if c["request_id"] == rid and c["kind"] == "director_report"]
    assert len(reports) == 1
    report = detail(client, director, reports[0]["id"])
    assert [e["detail"]["reason"] for e in report["timeline"] if e["action"] == "escalated"][-1] == "manual"
    response = client.post(f"{BASE}/cards/{report['card']['id']}/instructions", headers=director, json={
        "version": report["card"]["version"], "instruction": "[TEST] 새 답변을 직접 작성해 주세요"})
    assert response.status_code == 200, response.text
    assert response.json()["next_action"] is None
    err(decision(client, teacher, cid, version=version), 409, "CARD_VERSION_CONFLICT")
    err(decision(client, teacher, cid, version=version+1), 409, "INVALID_TRANSITION")
    assert decision(client, teacher, cid, "edit_approve", version=version+1,
                    edited_content={"text": "[TEST] 사람이 확인한 새 회신"}).status_code == 200


def test_unassigned_high_risk_complaint_accepts_instruction_then_reassignment(
    client, parent, teacher_other, director, card_backend
):
    from uuid import UUID
    if card_backend == "mock":
        store.state().classroom_staff[:] = [s for s in store.state().classroom_staff if s.classroom_id != seed.CLASS_STAR]
    else:
        with transaction() as connection:
            connection.execute(text("DELETE FROM classroom_staff WHERE classroom_id=:id"), {"id": seed.CLASS_STAR})
    response = client.post(BASE+"/requests", headers=parent, json={
        "client_request_id": str(uuid4()), "child_id": str(seed.CHILD),
        "type": "complaint", "body": "[TEST] 아이가 다쳤어요"})
    assert response.status_code == 202, response.text
    rid = response.json()["request"]["id"]
    cards = {c["kind"]: c for c in client.get(BASE+"/cards?size=100", headers=director).json()["items"]
             if c["request_id"] == rid}
    cid, report = cards["reply_draft"]["id"], cards["director_report"]["id"]
    response = client.post(f"{BASE}/cards/{report}/instructions", headers=director, json={
        "version": 1, "instruction": "[TEST] 상황 확인 후 직접 안내해 주세요"})
    assert response.status_code == 200, response.text
    assert response.json()["next_action"] == "reassign"
    assert "재배정" in response.json()["message"]
    assert response.json()["request"]["status"] == "awaiting_review"
    reply = detail(client, director, cid)
    assert reply["card"]["status"] == "unassigned" and reply["card"]["version"] == 1
    assert reply["director_instruction"]["text"] == "[TEST] 상황 확인 후 직접 안내해 주세요"
    if card_backend == "mock":
        assert store.state().cards[UUID(cid)].assignee_id is None
    else:
        with transaction() as connection:
            assert connection.scalar(text("SELECT assignee_id FROM cards WHERE id=:id"), {"id": cid}) is None
    err(client.post(f"{BASE}/cards/{report}/instructions", headers=director, json={
        "version": 1, "instruction": "[TEST] 중복 지시"}), 409, "ALREADY_DECIDED")
    response = client.post(f"{BASE}/cards/{cid}/reassign", headers=director, json={
        "assignee_id": str(seed.TEACHER_OTHER), "reason": "[TEST] 새 담당"})
    assert response.status_code == 200, response.text
    assert decision(client, teacher_other, cid, "edit_approve", version=2,
                    edited_content={"text": "[TEST] 지시 확인 후 답변"}).status_code == 200


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


@pytest.mark.parametrize("uncertain", [True, False])
def test_teacher_reclassification_keeps_report_until_director_instruction(
    client, parent, teacher, director, monkeypatch, uncertain
):
    fake_supervisor.install(monkeypatch)
    rid, cid = create(client, parent, teacher, body="[TEST] 판단 필요 민원" if uncertain else "[TEST] 버스 문의")
    version = 1
    if not uncertain:
        assert decision(client, teacher, cid, "escalate").status_code == 200
        version += 1
    reports = client.get(BASE + "/cards?kind=director_report&size=100", headers=director).json()["items"]
    report = next(c for c in reports if c["request_id"] == rid)
    response = client.post(f"{BASE}/cards/{cid}/reclassify", headers=teacher, json={
        "version": version, "risk_level": "normal", "reason": "[TEST] 위험 등급만 변경"})
    assert response.status_code == 200, response.text
    assert response.json()["request"]["status"] == "escalated"
    assert response.json()["request"]["risk_level"] == "normal"
    err(decision(client, teacher, cid, "edit_approve", version=version + 1,
                 edited_content={"text": "[TEST] 원장 지시 전 회신"}), 409, "INVALID_TRANSITION")
    saved = detail(client, teacher, cid)
    assert saved["timeline"][-1]["from_status"] == saved["timeline"][-1]["to_status"] == "escalated"
    assert detail(client, director, report["id"])["card"]["status"] == "pending"
    response = client.post(f"{BASE}/cards/{report['id']}/instructions", headers=director,
                           json={"version": 1, "instruction": "[TEST] 확인 후 회신"})
    assert response.status_code == 200, response.text
    assert decision(client, teacher, cid, "edit_approve", version=version + 1,
                    edited_content={"text": "[TEST] 지시 확인 후 회신"}).status_code == 200


@pytest.mark.parametrize("target_report", [False, True])
def test_director_normal_closes_report_and_notifies_returned_reply_once(
    client, parent, teacher, director, card_backend, monkeypatch, target_report
):
    fake_supervisor.install(monkeypatch)
    baseline = client.get(BASE + "/overview", headers=director).json()["waiting"]
    rid, cid = create(client, parent, teacher, body="[TEST] 판단 필요 민원")
    report = next(c for c in client.get(BASE + "/cards?kind=director_report", headers=director).json()["items"]
                  if c["request_id"] == rid)
    assert client.get(BASE + "/overview", headers=director).json()["waiting"] == baseline + 2
    target = report["id"] if target_report else cid
    response = client.post(f"{BASE}/cards/{target}/reclassify", headers=director, json={
        "version": 1, "risk_level": "normal", "reason": "[TEST] 원장 일반 분류"})
    assert response.status_code == 200, response.text
    assert response.json()["request"]["status"] == "awaiting_review"
    closed = detail(client, director, report["id"])
    assert (closed["card"]["status"], closed["card"]["version"]) == ("done", 2)
    assert any(e["action"] == "risk_reclassified" and e["card_id"] == report["id"]
               and e["detail"]["reason"] == "[TEST] 원장 일반 분류" for e in closed["timeline"])
    reports = client.get(BASE + "/cards?kind=director_report", headers=director).json()["items"]
    assert not any(c["request_id"] == rid for c in reports)
    assert client.get(BASE + "/overview", headers=director).json()["waiting"] == baseline + 1
    if card_backend == "mock":
        notifications = [(n.kind, str(n.recipient_id), str(n.card_id))
                         for n in store.state().notifications.values() if str(n.request_id) == rid]
    else:
        with transaction() as connection:
            notifications = [(n.kind, str(n.recipient_id), str(n.card_id)) for n in connection.execute(
                text("SELECT kind,recipient_id,card_id FROM notifications WHERE request_id=:id"), {"id": rid})]
            saved = connection.execute(text("SELECT closed_at,version FROM cards WHERE id=:id"), {"id": report["id"]}).one()
            assert saved.closed_at is not None and saved.version == 2
    assert sorted(n[0] for n in notifications) == ["new_card", "uncertain_complaint", "uncertain_complaint"]
    assert [n for n in notifications if n[0] == "new_card"] == [("new_card", str(seed.TEACHER), cid)]
    err(client.post(f"{BASE}/cards/{target}/reclassify", headers=director, json={
        "version": 1, "risk_level": "normal", "reason": "[TEST] 같은 판 재시도"}), 409, "CARD_VERSION_CONFLICT")
    # 이미 담임 단계인 요청의 일반 재분류는 알림을 더 만들지 않아요.
    response = client.post(f"{BASE}/cards/{cid}/reclassify", headers=director, json={
        "version": 1 if target_report else 2, "risk_level": "normal", "reason": "[TEST] 일반 유지"})
    assert response.status_code == 200, response.text
    if card_backend == "mock":
        assert len([n for n in store.state().notifications.values() if str(n.request_id) == rid]) == 3
    else:
        with transaction() as connection:
            assert connection.scalar(text("SELECT count(*) FROM notifications WHERE request_id=:id"), {"id": rid}) == 3
    assert decision(client, teacher, cid, "edit_approve", version=2 if target_report else 3,
                    edited_content={"text": "[TEST] 원장 분류 후 안내"}).status_code == 200
    assert client.get(BASE + "/overview", headers=director).json()["waiting"] == baseline


def test_reject_redraft_has_no_text_and_needs_teacher_text(client, parent, teacher):
    """거절 뒤 재초안은 초안 없는 카드(API 5.7, T47 결정 4). 앞 카드의 검사 통과를 물려받아 일반 승인으로 나가면 안 된다."""
    rid, cid = create(client, parent, teacher, type="inquiry", body="[TEST] 준비물 문의")
    assert detail(client, teacher, cid)["card"]["check_result"]["passed"] is True
    next_id = decision(client, teacher, cid, "reject", reason_code="tone").json()["next_card_id"]
    redraft = detail(client, teacher, next_id)
    assert redraft["card"]["draft"]["text"] == "" and redraft["card"]["check_result"] is None
    assert "check_unavailable" in redraft["warnings"]
    err(decision(client, teacher, next_id), 409, "INVALID_TRANSITION")
    sent = decision(client, teacher, next_id, "edit_approve", edited_content={"text": "[TEST] 담임이 다시 쓴 답"})
    assert sent.status_code == 200, sent.text
    messages = client.get(f"{BASE}/requests/{rid}", headers=parent).text
    assert "[TEST] 담임이 다시 쓴 답" in messages and "재초안" not in messages


def test_rejected_reply_cannot_complete_newer_sent_reply(client, parent, teacher):
    rid, old = create(client, parent, teacher)
    rejected = decision(client, teacher, old, "reject", reason_code="tone")
    assert rejected.status_code == 200, rejected.text
    current = rejected.json()["next_card_id"]
    assert decision(client, teacher, current, "edit_approve", edited_content={"text": "[TEST] 다시 쓴 답"}).status_code == 200
    before = detail(client, teacher, old)
    err(decision(client, teacher, old, "complete", version=2, reason_text="[TEST] 옛 카드 완료"),
        409, "INVALID_TRANSITION")
    assert detail(client, teacher, old) == before
    assert client.get(f"{BASE}/requests/{rid}", headers=parent).json()["request"]["status"] == "sent_or_booked"
    assert decision(client, teacher, current, "complete", version=2, reason_text="[TEST] 현재 회신 완료").status_code == 200


def test_rule_without_classroom_does_not_break_director_inbox(client, parent, teacher, director, card_backend):
    from app.mock.records import Rule

    _, reply = create(client, parent, teacher)
    rule_id, card_id = uuid4(), uuid4()
    if card_backend == "mock":
        store.state().rules[rule_id] = Rule(rule_id, seed.ORG, seed.DIRECTOR, "tone", "[TEST] 규칙", {})
        store.state().cards[card_id] = store.Card(card_id, seed.ORG, None, "rule_proposal", assignee_id=seed.DIRECTOR,
                                                subject_type="memory_rule", subject_id=rule_id)
    else:
        with transaction() as connection:
            values = {"org": seed.ORG, "owner": seed.DIRECTOR, "rule": rule_id, "card": card_id}
            connection.execute(text("""INSERT INTO memory_rules (id,org_id,owner_id,reason_code,rule_text,rule_json)
                VALUES (:rule,:org,:owner,'tone','[TEST] 규칙','{}')"""), values)
            connection.execute(text("""INSERT INTO cards (id,org_id,kind,assignee_id,subject_type,subject_id)
                VALUES (:card,:org,'rule_proposal',:owner,'memory_rule',:rule)"""), values)
    response = client.get(BASE + "/cards?size=100", headers=director)
    assert response.status_code == 200, response.text
    rows = {c["id"]: c for c in response.json()["items"]}
    assert rows[str(card_id)]["classroom"] is None
    assert rows[reply]["classroom"]["id"] == str(seed.CLASS_STAR)
    assert detail(client, director, str(card_id))["messages"] == []
    assert detail(client, director, card_id)["rule"]["id"] == str(rule_id)
    assert str(card_id) not in {c["id"] for c in client.get(BASE + "/cards?size=100", headers=teacher).json()["items"]}


def test_card_requester_names_in_list_detail_and_reclassify(client, parent, teacher):
    rid, cid = create(client, parent, teacher, type="inquiry", body="[TEST] 준비물을 알려 주세요")
    expected = {"child_id": str(seed.CHILD), "child_name": "하늘", "requester_name": "하늘이 보호자"}
    listed = next(c for c in client.get(BASE + "/cards?size=100", headers=teacher).json()["items"] if c["id"] == cid)
    request = detail(client, teacher, cid)["request"]
    response = client.post(f"{BASE}/cards/{cid}/reclassify", headers=teacher,
                           json={"version": 1, "risk_level": "normal", "reason": "[TEST] 이름 확인"})
    assert response.status_code == 200, response.text
    assert request["id"] == rid
    for row in (listed, request, response.json()["request"]):
        assert {k: row[k] for k in expected} == expected


def test_card_requester_without_child_and_bulk_list_query(client, parent, teacher, director, card_backend):
    from tests.integration.api.test_requests import change_request
    rid, cid = create(client, parent, teacher, type="inquiry", body="[TEST] 준비물 문의")
    create(client, parent, teacher, type="inquiry", body="[TEST] 급식 문의")
    change_request(card_backend, rid, child_id=None)
    statements = []
    if card_backend == "db":
        from sqlalchemy import event
        from app.core.db import get_engine
        def capture(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)
        event.listen(get_engine(), "before_cursor_execute", capture)
    try:
        response = client.get(BASE + "/cards?size=100", headers=teacher)
        assert response.status_code == 200, response.text
    finally:
        if card_backend == "db":
            event.remove(get_engine(), "before_cursor_execute", capture)
    listed = next(c for c in response.json()["items"] if c["id"] == cid)
    for row in (listed, detail(client, teacher, cid)["request"]):
        assert row["child_id"] is row["child_name"] is None and row["requester_name"] == "하늘이 보호자"
    if card_backend == "db":
        assert len([s for s in statements if "AS requester_name" in s]) == 2
        assert not any("FROM users u LEFT JOIN children" in s for s in statements)
    change_request(card_backend, rid, classroom_id=None)
    response = client.get(BASE + "/requests?size=100", headers=director)
    assert response.status_code == 200, response.text
    assert next(r for r in response.json()["items"] if r["id"] == rid)["classroom_id"] is None
