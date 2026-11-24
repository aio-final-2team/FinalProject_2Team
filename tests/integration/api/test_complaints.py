"""T31: 반복·고위험 민원과 위험한 문의·상담의 사람 인계를 두 백엔드에서 확인해요."""

from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from app import backend
from app.core.db import transaction
from app.core.schedule import KST
from app.mock import seed, store
from tests.integration.api.helpers import BASE, decision, err
from tests.integration.api.test_consultations import book, choose


@pytest.fixture(autouse=True, params=["mock", "db"])
def complaint_backend(request, monkeypatch):
    if request.param == "db":
        request.getfixturevalue("seeded_db")
        from app.core import users
        from app.modules.cards import cards, card_views
        from app.modules.notifications import notifications
        from app.modules.requests import requests
    else:
        from app.mock import cards, card_views, notifications, request_actions as requests

        users = store
    for name, module in dict(users=users, cards=cards, card_views=card_views,
                             notifications=notifications, request_actions=requests).items():
        monkeypatch.setattr(backend, name, module)
    return request.param


def create(client, parent, *, body="[TEST] 가방이 분실됐어요", child=seed.CHILD, kind="complaint"):
    response = client.post(BASE + "/requests", headers=parent, json={
        "client_request_id": str(uuid4()), "type": kind, "body": body, "child_id": str(child)})
    assert response.status_code == 202, response.text
    return response.json()["request"]["id"]


def cards(client, director, rid):
    response = client.get(BASE + "/cards?size=100", headers=director)
    assert response.status_code == 200, response.text
    return {c["kind"]: c for c in response.json()["items"] if c["request_id"] == rid}


def detail(client, actor, cid):
    response = client.get(f"{BASE}/cards/{cid}", headers=actor)
    assert response.status_code == 200, response.text
    return response.json()


def test_third_complaint_counts_other_guardians_closed_cases_and_only_same_class_topic_window(
    client, parent, parent_other, teacher, director, complaint_backend
):
    old = create(client, parent)
    outside = datetime.now(KST) - timedelta(days=30, seconds=5)
    if complaint_backend == "mock":
        store.state().requests[UUID(old)].created_at = outside
    else:
        with transaction() as connection:
            connection.execute(text("UPDATE requests SET created_at=:at WHERE id=:id"), {"id": old, "at": outside})
    create(client, parent_other, child=seed.CHILD_OTHER)  # 다른 반
    create(client, parent, kind="inquiry")
    create(client, parent, body="[TEST] 연락이 늦어요")  # 다른 주제
    first = create(client, parent)
    first_card = cards(client, director, first)["reply_draft"]
    assert first_card["repeat_count"] == 1 and first_card["risk_level"] == "normal"
    assert decision(client, teacher, first_card["id"]).status_code == 200
    assert client.post(f"{BASE}/requests/{first}/confirm", headers=parent).status_code == 200
    assert decision(client, teacher, first_card["id"], "complete", version=2).status_code == 200
    second = create(client, parent_other, child=seed.demo_id("503"))
    second_cards = cards(client, director, second)
    assert set(second_cards) == {"reply_draft"} and second_cards["reply_draft"]["repeat_count"] == 2
    third = create(client, parent)
    saved = cards(client, director, third)
    assert set(saved) == {"reply_draft", "director_report"}
    assert {c["repeat_count"] for c in saved.values()} == {3}
    assert all(c["risk_level"] == "normal" and not c["is_urgent"] for c in saved.values())
    assert saved["director_report"]["assignee"]["id"] == str(seed.DIRECTOR)
    assert saved["reply_draft"]["assignee"]["id"] == str(seed.TEACHER)
    assert saved["reply_draft"]["due_at"] == saved["director_report"]["due_at"]
    reply = detail(client, teacher, saved["reply_draft"]["id"])
    assert reply["request"]["status"] == "escalated" and reply["card"]["draft"]["text"]
    assert len(client.get(f"{BASE}/requests/{third}", headers=parent).json()["messages"]) == 1
    fourth = cards(client, director, create(client, parent))
    assert set(fourth) == {"reply_draft", "director_report"}
    assert {c["repeat_count"] for c in fourth.values()} == {4}


def test_other_topic_is_not_combined_into_repeated_complaints(client, parent, director):
    for _ in range(3):
        rid = create(client, parent, body="[TEST] 기타 민원이에요")
        rows = cards(client, director, rid)
        assert set(rows) == {"reply_draft"} and rows["reply_draft"]["repeat_count"] is None


@pytest.mark.parametrize("body,risk,category", [
    ("[TEST] 아이가 다쳤어요", "urgent", "child_safety"),
    ("[TEST] 가만두지 않겠어요", "urgent", "staff_attack"),
    ("[TEST] 변호사에게 물었어요", "urgent", "legal_external"),
    ("[TEST] 개인정보가 유출됐어요", "urgent", "privacy_leak"),
    ("[TEST] 판단 필요 민원이에요", "uncertain", None),
])
@pytest.mark.parametrize("kind", ["complaint", "inquiry"])
def test_high_risk_handoff_has_two_cards_no_draft_or_automatic_reply(
    client, parent, teacher, director, body, risk, category, kind
):
    rid = create(client, parent, body=body, kind=kind)
    saved = cards(client, director, rid)
    assert set(saved) == {"reply_draft", "director_report"}
    assert all(c["risk_level"] == risk and c["risk_category"] == category for c in saved.values())
    assert all(c["is_urgent"] == (risk == "urgent") for c in saved.values())
    assert saved["reply_draft"]["assignee"]["id"] == str(seed.TEACHER)
    assert saved["director_report"]["assignee"]["id"] == str(seed.DIRECTOR)
    for row in saved.values():
        item = detail(client, director, row["id"])
        assert "text" not in item["card"]["draft"] and item["card"]["check_result"] is None
        start = datetime.fromisoformat(item["request"]["created_at"])
        assert datetime.fromisoformat(row["due_at"]) == start + timedelta(hours=2)
        assert item["request"]["status"] == "escalated"
    history = detail(client, teacher, saved["reply_draft"]["id"])["timeline"]
    assert [e["to_status"] for e in history if e["to_status"]] == ["received", "classified", "assigned", "escalated"]
    assert not {"approved", "sent"} & {e["action"] for e in history}
    bucket = "uncertain" if risk == "uncertain" else "needs_review"
    listed = client.get(f"{BASE}/cards?filter={bucket}&size=100", headers=director).json()["items"]
    assert {c["id"] for c in saved.values()} <= {c["id"] for c in listed}
    parent_view = client.get(f"{BASE}/requests/{rid}", headers=parent).json()
    assert len(parent_view["messages"]) == 1
    err(decision(client, teacher, saved["reply_draft"]["id"]), 409, "INVALID_TRANSITION")
    if risk == "uncertain":
        cid = saved["reply_draft"]["id"]
        err(decision(client, teacher, cid, "edit_approve", edited_content={"text": "[TEST] 아직 판단 전"}),
            409, "INVALID_TRANSITION")
        result = client.post(f"{BASE}/cards/{cid}/reclassify", headers=teacher, json={
            "version": 1, "risk_level": "normal", "reason": "[TEST] 사람이 확인했어요"})
        assert result.status_code == 200, result.text
        err(decision(client, teacher, cid, version=2), 409, "INVALID_TRANSITION")
        err(decision(client, teacher, cid, "edit_approve", version=2,
                     edited_content={"text": "[TEST] 원장 지시 전"}), 409, "INVALID_TRANSITION")
        report = saved["director_report"]["id"]
        instructed = client.post(f"{BASE}/cards/{report}/instructions", headers=director,
                                 json={"version": 1, "instruction": "[TEST] 원장 확인 후 안내"})
        assert instructed.status_code == 200, instructed.text
        assert decision(client, teacher, cid, "edit_approve", version=2,
                        edited_content={"text": "[TEST] 확인 뒤 직접 안내해요"}).status_code == 200


def risk_titles(client, actor, rid):
    response = client.get(f"{BASE}/notifications?size=100", headers=actor)
    assert response.status_code == 200, response.text
    return {n["kind"]: n["title"] for n in response.json()["items"]
            if n["request_id"] == rid and n["kind"] in ("urgent_complaint", "uncertain_complaint")}


def test_urgent_inquiry_can_be_lowered_by_teacher_and_director(client, parent, teacher, director):
    rid = create(client, parent, body="[TEST] 경찰에 알릴 거예요", kind="inquiry")
    saved = cards(client, director, rid)
    assert saved["reply_draft"]["risk_category"] == "legal_external"
    assert risk_titles(client, director, rid) == risk_titles(client, teacher, rid) == {"urgent_complaint": "긴급 문의"}
    cid, report = saved["reply_draft"]["id"], saved["director_report"]["id"]
    lowered = client.post(f"{BASE}/cards/{cid}/reclassify", headers=teacher, json={
        "version": 1, "risk_level": "normal", "reason": "[TEST] 문의로 확인했어요"})
    assert lowered.status_code == 200, lowered.text
    assert lowered.json()["request"]["risk_level"] == "normal"
    assert lowered.json()["request"]["status"] == "escalated"  # 원장 보고 카드는 원장이 닫아요
    closed = client.post(f"{BASE}/cards/{report}/reclassify", headers=director, json={
        "version": 1, "risk_level": "normal", "reason": "[TEST] 원장도 일반으로 봤어요"})
    assert closed.status_code == 200, closed.text
    assert closed.json()["request"]["status"] == "awaiting_review"
    assert detail(client, director, report)["card"]["status"] == "done"


@pytest.mark.parametrize("body,risk,title", [
    ("[TEST] 아이가 다쳤어요. 상담하고 싶어요", "urgent", "긴급 상담"),
    ("[TEST] 판단 필요 상담이에요", "uncertain", "AI 판단 불확실 상담"),
])
def test_risky_consultation_keeps_slot_flow_and_adds_director_report(
    client, parent, teacher, director, body, risk, title
):
    other = create(client, parent, body="[TEST] 아이가 다쳤어요", kind="inquiry")  # 다른 요청의 보고 카드는 그대로
    rid = create(client, parent, body=body, kind="consultation")
    saved = cards(client, director, rid)
    assert set(saved) == {"consult_slots", "director_report"}
    assert saved["consult_slots"]["assignee"]["id"] == str(seed.TEACHER)
    assert saved["director_report"]["assignee"]["id"] == str(seed.DIRECTOR)
    assert all(c["risk_level"] == risk for c in saved.values())
    start = datetime.fromisoformat(detail(client, director, saved["director_report"]["id"])["request"]["created_at"])
    assert all(datetime.fromisoformat(c["due_at"]) == start + timedelta(hours=2) for c in saved.values())
    kind = "urgent_complaint" if risk == "urgent" else "uncertain_complaint"
    assert risk_titles(client, director, rid) == {kind: title}
    view = client.get(f"{BASE}/requests/{rid}", headers=parent).json()
    assert view["request"]["status"] == "needs_info"
    err(client.post(f"{BASE}/cards/{saved['consult_slots']['id']}/reclassify", headers=teacher, json={
        "version": 1, "risk_level": "normal", "reason": "[TEST] 상담은 재분류 안 함"}), 409, "INVALID_TRANSITION")
    slots = view["consultation"]["slots"]
    assert choose(client, parent, rid, slots[:1]).status_code == 200
    director_notices = client.get(f"{BASE}/notifications?size=100", headers=director).json()["total"]
    booked = book(client, teacher, saved["consult_slots"]["id"], slots[0])
    assert booked.status_code == 200, booked.text
    assert booked.json()["request"]["status"] == "sent_or_booked"
    # 원장 지시는 escalated만 받으므로 예약 확정 때 열린 원장 보고 카드를 같이 닫고, 원장 알림은 더 보내지 않아요.
    assert detail(client, director, saved["director_report"]["id"])["card"]["status"] == "done"
    assert client.get(f"{BASE}/notifications?size=100", headers=director).json()["total"] == director_notices
    assert detail(client, director, cards(client, director, other)["director_report"]["id"])["card"]["status"] == "pending"
