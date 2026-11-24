"""상담·민원·받은함·알림의 정상 흐름과 경계."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import UUID, uuid4

import pytest

from app.mock import seed, store, notifications
from app.core.auth import CurrentUser
from app.core.schedule import KST

from tests.integration.api.helpers import BASE, create, decision, err


def test_consultation_complete_booking_flow(client, parent, teacher, director):
    rid, cid = create(client, parent, "consultation", "친구 관계 상담")
    detail = client.get(f"{BASE}/requests/{rid}", headers=parent).json()
    slot_ids = [s["id"] for s in detail["consultation"]["slots"]]
    chosen = client.post(f"{BASE}/requests/{rid}/slot-choices", headers=parent, json={"slot_ids": slot_ids[:2]})
    assert chosen.status_code == 200 and chosen.json()["request"]["status"] == "awaiting_review"
    card = client.get(f"{BASE}/cards/{cid}", headers=teacher).json()
    assert len(card["parent_choices"]) == 2
    assert card["parent_choices"][0]["hold_expires_at"] > card["parent_choices"][0]["chosen_at"]
    err(client.post(f"{BASE}/cards/{cid}/bookings", headers=director, json={"version": 1, "slot_id": slot_ids[0]}), 403, "FORBIDDEN_ROLE")
    err(client.post(f"{BASE}/cards/{cid}/bookings", headers=teacher, json={"version": 2, "slot_id": slot_ids[0]}), 409, "CARD_VERSION_CONFLICT")
    err(client.post(f"{BASE}/cards/{cid}/bookings", headers=teacher, json={"version": 1, "slot_id": slot_ids[2]}), 409, "SLOT_NOT_CHOSEN")
    booked = client.post(f"{BASE}/cards/{cid}/bookings", headers=teacher, json={"version": 1, "slot_id": slot_ids[0]})
    assert booked.status_code == 200, booked.text
    detail = client.get(f"{BASE}/requests/{rid}", headers=parent).json()
    assert detail["request"]["status"] == "sent_or_booked"
    assert detail["request"]["status_label"] == "예약 확정"
    assert detail["consultation"]["booking"] == booked.json()["booking"]
    assert len(detail["consultation"]["slots"]) == 1
    assert [e.to_status for e in store.events_of(UUID(rid))][-2:] == ["approved", "sent_or_booked"]


def test_complaint_approval_confirmation_completion(client, parent, teacher):
    rid, cid = create(client, parent)
    before = client.get(f"{BASE}/requests/{rid}", headers=parent).json()
    assert before["sources"] == []
    response = decision(client, teacher, cid)
    assert response.status_code == 200, response.text
    assert response.json()["card"]["version"] == 2
    assert client.get(f"{BASE}/requests/{rid}", headers=parent).json()["sources"]
    progress = client.get(BASE + "/cards?filter=in_progress", headers=teacher).json()
    assert cid in [c["id"] for c in progress["items"]]
    confirmed = client.post(f"{BASE}/requests/{rid}/confirm", headers=parent)
    assert confirmed.status_code == 200
    assert client.post(f"{BASE}/requests/{rid}/confirm", headers=parent).json() == confirmed.json()
    assert len([n for n in store.state().notifications.values() if n.request_id == UUID(rid) and n.kind == "parent_confirmed"]) == 1
    review = client.get(BASE + "/cards?filter=needs_review", headers=teacher).json()
    assert cid in [c["id"] for c in review["items"]]
    completed = decision(client, teacher, cid, "complete", version=2)
    assert completed.status_code == 200 and completed.json()["request"]["status"] == "completed"
    err(client.post(f"{BASE}/requests/{rid}/messages", headers=parent, json={"body": "추가 글"}), 409, "INVALID_TRANSITION")


def test_unconfirmed_complete_needs_reason_and_overview_counts(client, parent, teacher, director):
    rid, cid = create(client, parent)
    err(decision(client, teacher, cid, "complete"), 409, "INVALID_TRANSITION")
    assert decision(client, teacher, cid).status_code == 200
    err(decision(client, teacher, cid, "complete", version=2), 409, "REASON_REQUIRED")
    assert not any(a.decision == "complete" for a in store.state().approvals)
    assert decision(client, teacher, cid, "complete", version=2, reason_text="전화로 설명드리고 마무리함").status_code == 200
    overview = client.get(BASE + "/overview", headers=director)
    assert overview.status_code == 200 and overview.json()["completed_unconfirmed"] == 1
    assert overview.json()["eval"] == []
    err(client.get(BASE + "/overview", headers=teacher), 403, "FORBIDDEN_ROLE")



def test_director_cannot_approve_or_complete_complaint_reply(client, parent, teacher, director):
    rid, cid = create(client, parent)
    err(decision(client, director, cid), 403, "FORBIDDEN_ROLE")
    err(decision(client, director, cid, "edit_approve", edited_content={"text": "원장이 쓴 답"}), 403, "FORBIDDEN_ROLE")
    assert decision(client, teacher, cid).status_code == 200
    err(decision(client, director, cid, "complete", version=2, reason_text="원장 마무리"), 403, "FORBIDDEN_ROLE")
    assert decision(client, teacher, cid, "complete", version=2, reason_text="전화로 마무리함").status_code == 200

def test_notify_failed_warning_keeps_urgent_card_visible(client, parent, teacher):
    _, cid = create(client, parent, body="아이가 다쳤어요")
    assert "notify_failed" not in client.get(f"{BASE}/cards/{cid}", headers=teacher).json()["warnings"]
    store.state().cards[UUID(cid)].draft["notify_failed"] = True
    detail = client.get(f"{BASE}/cards/{cid}", headers=teacher).json()
    assert {"notify_failed", "no_evidence", "check_unavailable"}.issubset(detail["warnings"])
    assert cid in [c["id"] for c in client.get(BASE + "/cards", headers=teacher).json()["items"]]

def test_version_conflict_and_duplicate_decision(client, parent, teacher):
    _, cid = create(client, parent)
    conflict = decision(client, teacher, cid, version=9)
    err(conflict, 409, "CARD_VERSION_CONFLICT")
    assert conflict.json()["error"]["details"]["current_version"] == 1
    assert decision(client, teacher, cid).status_code == 200
    err(decision(client, teacher, cid), 409, "ALREADY_DECIDED")
    assert len([a for a in store.state().approvals if a.card_id == UUID(cid)]) == 1


def test_concurrent_decisions_only_one_succeeds(client, parent, teacher):
    _, cid = create(client, parent)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: decision(client, teacher, cid), range(2)))
    assert sorted(r.status_code for r in results) == [200, 409]
    assert len([a for a in store.state().approvals if a.card_id == UUID(cid)]) == 1


def test_slot_collision_is_atomic_and_nonoverlap_is_allowed(client, parent, teacher):
    pairs = [create(client, parent, "consultation", "시간 상담") for _ in range(2)]
    for index, (rid, cid) in enumerate(pairs):
        slots = client.get(f"{BASE}/requests/{rid}", headers=parent).json()["consultation"]["slots"]
        assert client.post(f"{BASE}/requests/{rid}/slot-choices", headers=parent, json={"slot_ids": [s["id"] for s in slots[index:index+1]]}).status_code == 200
    first = store.slots_of_request(UUID(pairs[0][0]))
    second = store.slots_of_request(UUID(pairs[1][0]))
    second[1].period = dict(first[0].period)  # 이전 중복 체크를 가정해 최종 제약도 확인해요.
    assert client.post(f"{BASE}/cards/{pairs[0][1]}/bookings", headers=teacher, json={"version": 1, "slot_id": first[0].id}).status_code == 200
    err(client.post(f"{BASE}/cards/{pairs[1][1]}/bookings", headers=teacher, json={"version": 1, "slot_id": second[1].id}), 409, "SLOT_TAKEN")
    assert store.state().cards[UUID(pairs[1][1])].version == 1
    assert second[1].status == "chosen_by_parent"
    second[1].period = dict(first[1].period)
    assert client.post(f"{BASE}/cards/{pairs[1][1]}/bookings", headers=teacher, json={"version": 1, "slot_id": second[1].id}).status_code == 200


def test_none_fit_regenerates_and_hold_expires_once(client, parent, teacher):
    rid, cid = create(client, parent, "consultation")
    before = store.slots_of_request(UUID(rid))
    retry = client.post(f"{BASE}/requests/{rid}/slot-choices", headers=parent,
                        json={"none_fit": True, "preferred_times": "다음 주 오후"})
    assert retry.status_code == 200 and retry.json()["request"]["status"] == "needs_info"
    assert all(s.status == "discarded" for s in before)
    after = [s for s in store.slots_of_request(UUID(rid)) if s.round == 2]
    assert len(after) == 3 and after[0].period["start"] > before[0].period["start"]
    assert any(e.detail.get("preferred_times") == "다음 주 오후" for e in store.events_of(UUID(rid)))
    assert client.post(f"{BASE}/requests/{rid}/slot-choices", headers=parent, json={"slot_ids": [after[0].id]}).status_code == 200
    after[0].chosen_at = store.now() - timedelta(hours=25)
    detail = client.get(f"{BASE}/cards/{cid}", headers=teacher).json()
    assert detail["parent_choices"] == [] and after[0].status == "proposed"
    assert client.get(f"{BASE}/requests/{rid}", headers=parent).json()["request"]["status"] == "needs_info"
    assert len([e for e in store.events_of(UUID(rid)) if e.action == "slot_hold_expired"]) == 1
    assert len([n for n in store.state().notifications.values() if n.request_id == UUID(rid) and n.kind == "slot_hold_expired"]) == 1


def test_manual_and_automatic_hold_resume_hide_private_reason(client, parent, teacher):
    rid, cid = create(client, parent)
    until = (store.now().date() + timedelta(days=2)).isoformat()
    held = decision(client, teacher, cid, "hold", reason_text="담당자와 내부 확인 중", hold_until=until)
    assert held.status_code == 200, held.text
    detail = client.get(f"{BASE}/requests/{rid}", headers=parent)
    assert "담당자와 내부" not in detail.text and detail.json()["request"]["hold_until"] == until
    messages = client.get(BASE + "/notifications", headers=parent)
    assert "담당자와 내부" not in messages.text
    assert decision(client, teacher, cid, "resume", version=2).status_code == 200
    assert decision(client, teacher, cid, "hold", version=3, reason_text="확인 중", hold_until=until).status_code == 200
    card = store.state().cards[UUID(cid)]
    card.hold_until = store.now().date()
    assert client.get(f"{BASE}/requests/{rid}", headers=parent).json()["request"]["status"] == "awaiting_review"
    assert card.version == 5
    client.get(f"{BASE}/cards/{cid}", headers=teacher)
    automatic = [e for e in store.events_of(UUID(rid)) if e.action == "resumed" and e.detail.get("automatic")]
    assert len(automatic) == 1 and automatic[0].actor_type == "system"
    assert len([a for a in store.state().approvals if a.card_id == card.id]) == 3
    assert any(n.kind == "hold_resumed" and n.request_id == UUID(rid) for n in store.state().notifications.values())


def test_dismiss_reason_and_redraft(client, parent, teacher):
    rid, cid = create(client, parent)
    rejected = decision(client, teacher, cid, "reject", reason_code="tone")
    assert rejected.status_code == 200 and rejected.json()["next_card_id"] != cid
    assert rejected.json()["request"]["status"] == "awaiting_review"
    next_card = rejected.json()["next_card_id"]
    dismissed = decision(client, teacher, next_card, "dismiss", reason_code="other", reason_text="원 업무 범위를 벗어나요")
    assert dismissed.status_code == 200
    detail = client.get(f"{BASE}/requests/{rid}", headers=parent).json()
    assert detail["rejection"] == {"reason_code": "other", "reason_text": "원 업무 범위를 벗어나요"}
    assert detail["request"]["status"] == "rejected"
    assert client.post(BASE + "/requests", headers=parent, json={"client_request_id": str(uuid4()), "child_id": str(seed.CHILD),
                       "type": "inquiry", "body": "다시 문의", "previous_request_id": rid}).status_code == 202


def test_director_report_permission_instructions_reassign(client, parent, teacher, teacher_other, director):
    rid, cid = create(client, parent, body="아이가 다쳤어요")
    report = next(c for c in store.cards_of(UUID(rid)) if c.kind == "director_report")
    err(decision(client, teacher, str(report.id)), 403, "FORBIDDEN_ROLE")
    err(client.post(f"{BASE}/cards/{report.id}/instructions", headers=teacher, json={"version": 1, "instruction": "확인"}), 403, "FORBIDDEN_ROLE")
    instruction = client.post(f"{BASE}/cards/{report.id}/instructions", headers=director,
                              json={"version": 1, "instruction": "안전 상황을 확인한 뒤 보호자에게 연락해 주세요"})
    assert instruction.status_code == 200, instruction.text
    assert instruction.json()["card"]["status"] == "done"
    detail = client.get(f"{BASE}/cards/{cid}", headers=teacher).json()
    assert detail["director_instruction"]["by"]["id"] == str(seed.DIRECTOR)
    assert "안전 상황" in detail["director_instruction"]["text"]
    assert any(a.decision == "instruct" for a in store.state().approvals)
    reassigned = client.post(f"{BASE}/cards/{cid}/reassign", headers=director,
                            json={"assignee_id": str(seed.TEACHER_OTHER), "reason": "담당자 부재"})
    assert reassigned.status_code == 200
    assert client.get(f"{BASE}/cards/{cid}", headers=teacher_other).status_code == 200
    assert client.get(f"{BASE}/requests/{rid}", headers=teacher_other).status_code == 200
    assert cid in [c["id"] for c in client.get(BASE + "/cards?assignee=me", headers=teacher_other).json()["items"]]
    overview = client.get(BASE + "/overview", headers=director).json()
    assert overview["reassignments"][-1]["from"] == str(seed.TEACHER)
    assert overview["reassignments"][-1]["to"] == str(seed.TEACHER_OTHER)
    err(client.post(f"{BASE}/cards/{cid}/bookings", headers=teacher_other, json={"version": 2, "slot_id": 1}), 403, "FORBIDDEN_ROLE")


def test_reclassify_uncertain_and_escalate(client, teacher, director):
    req = store.state().requests[seed.demo_id("704")]
    card = next(c for c in store.cards_of(req.id) if c.kind == "reply_draft")
    result = client.post(f"{BASE}/cards/{card.id}/reclassify", headers=teacher, json={"version": 1, "risk_level": "normal", "reason": "일반 문의 수준"})
    assert result.status_code == 200 and result.json()["request"]["risk_level"] == "normal"
    review = client.get(BASE + "/cards?filter=needs_review", headers=teacher).json()
    assert str(card.id) in [c["id"] for c in review["items"]]
    result = client.post(f"{BASE}/cards/{card.id}/reclassify", headers=teacher,
                         json={"version": 2, "risk_level": "urgent", "risk_category": "child_safety", "reason": "추가 확인"})
    assert result.status_code == 200 and req.status == "escalated"
    assert any(e.action == "risk_reclassified" for e in store.events_of(req.id))
    assert len([c for c in store.cards_of(req.id) if c.kind == "director_report"]) == 1


def test_explicit_escalation_and_edit_approval(client, parent, teacher, director):
    rid, cid = create(client, parent)
    assert decision(client, teacher, cid, "escalate").status_code == 200
    report = next(c for c in store.cards_of(UUID(rid)) if c.kind == "director_report")
    assert client.post(f"{BASE}/cards/{report.id}/instructions", headers=director, json={"version": 1, "instruction": "확인 후 안내"}).status_code == 200
    approved = decision(client, teacher, cid, "edit_approve", version=2, edited_content={"text": "확인한 내용으로 안내드려요"})
    assert approved.status_code == 200, approved.text
    assert client.get(f"{BASE}/requests/{rid}", headers=parent).json()["messages"][-1]["body"] == "확인한 내용으로 안내드려요"


def test_lists_filters_counts_sorting_and_repeat_scope(client, teacher, director, parent):
    result = client.get(BASE + "/cards", headers=teacher)
    assert result.status_code == 200, result.text
    data = result.json()
    assert set(data["counts"]) == {"unassigned", "needs_review", "uncertain", "on_hold", "in_progress", "done"}
    assert data["items"][0]["is_urgent"] is True
    assert all(c["classroom"]["name"] for c in data["items"])
    assert all(c["due_at"] for c in data["items"] if c["kind"] != "rule_proposal")
    partition = []
    for value in data["counts"]:
        response = client.get(BASE + f"/cards?filter={value}", headers=teacher).json()
        assert response["total"] == data["counts"][value]
        partition += [c["id"] for c in response["items"]]
    assert len(partition) == len(set(partition))
    only_urgent = client.get(BASE + "/cards?risk_level=urgent&size=1", headers=teacher).json()
    assert all(c["risk_level"] == "urgent" for c in only_urgent["items"])
    assert sum(only_urgent["counts"].values()) == only_urgent["total"]
    requests = client.get(BASE + "/requests?status=needs_info&size=1", headers=parent).json()
    assert requests["items"][0]["next_action"] == "시간을 골라 주세요"
    assert requests["page"] == 1 and requests["size"] == 1
    _, cid = create(client, parent, body="버스 추가 문의")
    assert client.get(f"{BASE}/cards/{cid}", headers=teacher).json()["request"]["repeat_count"] == 2
    _, cid = create(client, parent, body="버스 세 번째 문의")
    assert client.get(f"{BASE}/cards/{cid}", headers=teacher).json()["request"]["status"] == "escalated"
    assert store.repeat_count(store.Request(uuid4(), seed.ORG, seed.CLASS_STAR, seed.CHILD, seed.PARENT, "other", "complaint", "기타", topic_key="other")) is None


def test_request_and_card_stream_audiences_and_messages(client, parent, teacher):
    rid, cid = create(client, parent)
    response = client.get(f"{BASE}/requests/{rid}/stream", headers=parent)
    assert response.status_code == 200 and response.headers["Content-Type"].startswith("text/event-stream")
    assert [line for line in response.text.splitlines() if line.startswith("event:")] == ["event: stage"] * 4 + ["event: done"]
    assert all(step in response.text for step in ("classifying", "searching", "drafting", "checking"))
    staff = client.get(f"{BASE}/cards/{cid}/stream", headers=teacher)
    assert staff.status_code == 200 and "event: token" in staff.text and "event: card" in staff.text
    err(client.get(f"{BASE}/cards/{cid}/stream", headers=parent), 403, "FORBIDDEN_ROLE")
    err(client.get(f"{BASE}/requests/{rid}/stream", headers=teacher), 403, "FORBIDDEN_ROLE")
    message = client.post(f"{BASE}/requests/{rid}/messages", headers={**parent, "X-Request-ID": "message-trace"}, json={"body": "추가 설명"})
    assert message.status_code == 201 and message.json()["message"]["sender_type"] == "user"
    assert decision(client, teacher, cid).status_code == 200
    assert client.post(f"{BASE}/requests/{rid}/messages", headers=parent, json={"body": "회신에 추가 문의"}).status_code == 201
    assert store.state().requests[UUID(rid)].status == "awaiting_review"


def test_notifications_dedupe_delay_and_read_scope(client, parent, parent_other, teacher, monkeypatch):
    from datetime import datetime
    fixed = datetime(2026, 12, 4, 20, tzinfo=KST)
    monkeypatch.setattr(store, "now", lambda: fixed)
    rid, _ = create(client, parent)
    event = next(e for e in store.events_of(UUID(rid)) if e.to_status == "awaiting_review")
    before = len(store.state().notifications)
    notifications.notify_event(event, store.state().requests[UUID(rid)], store.state().cards[event.card_id])
    assert len(store.state().notifications) == before
    generated = [n for n in store.state().notifications.values() if n.request_id == UUID(rid)]
    assert generated and generated[0].dedupe_key == f"event:{event.id}:{seed.TEACHER}"
    assert generated[0].deliver_after.weekday() == 0 and generated[0].deliver_after.hour == 9
    assert not any(n["request_id"] == rid for n in client.get(BASE + "/notifications", headers=teacher).json()["items"])
    monkeypatch.setattr(store, "now", lambda: fixed + timedelta(days=3))
    items = client.get(BASE + "/notifications?size=100", headers=teacher).json()["items"]
    notification = next(n for n in items if n["request_id"] == rid)
    read = client.post(f"{BASE}/notifications/{notification['id']}/read", headers=teacher)
    assert read.status_code == 200 and read.json()["notification"]["read_at"]
    assert client.post(f"{BASE}/notifications/{notification['id']}/read", headers=teacher).json() == read.json()
    err(client.post(f"{BASE}/notifications/{notification['id']}/read", headers=parent_other), 404, "NOT_FOUND")


def test_rule_owner_only_and_decision(client, teacher, teacher_other, director, parent):
    card = client.get(f"{BASE}/cards/{seed.demo_id('809')}", headers=teacher).json()
    assert card["rule"]["id"] == str(seed.RULE)
    for headers in (teacher_other, director, parent):
        err(client.post(f"{BASE}/memory-rules/{seed.RULE}/decision", headers=headers, json={"decision": "activate"}), 404, "NOT_FOUND")
    response = client.post(f"{BASE}/memory-rules/{seed.RULE}/decision", headers=teacher, json={"decision": "activate"})
    assert response.status_code == 200 and response.json()["rule"]["status"] == "active"


@pytest.mark.parametrize("path", ["/cards", "/cards/00000000-0000-4000-8000-000000000802", "/overview", "/documents"])
def test_parent_cannot_read_staff_routes(client, parent, path):
    err(client.get(BASE + path, headers=parent), 403, "FORBIDDEN_ROLE")


@pytest.mark.parametrize("body", [
    {"decision": "reject"}, {"decision": "dismiss", "reason_code": "wrong"},
    {"decision": "dismiss", "reason_code": "other"}, {"decision": "hold"},
    {"decision": "hold", "reason_text": "확인", "hold_until": "2000-01-01"},
    {"decision": "edit_approve"}, {"decision": "complete", "reason_text": "   "},
])
def test_decision_input_validation(client, teacher, body):
    err(client.post(f"{BASE}/cards/{seed.CARD_COMPLAINT}/decisions", headers=teacher, json={"version": 1, **body}), 422, "VALIDATION_FAILED")


@pytest.mark.parametrize("body", [{"slot_ids": []}, {"slot_ids": [1, 2, 3, 4]}, {"slot_ids": [1, 1]},
                                   {"none_fit": True}, {"none_fit": True, "preferred_times": "   "}])
def test_slot_input_validation(client, parent, body):
    err(client.post(f"{BASE}/requests/{seed.REQUEST_CONSULT}/slot-choices", headers=parent, json=body), 422, "VALIDATION_FAILED")


def test_foreign_scope_paths_and_required_parameters(client, parent, parent_other, teacher_other, teacher):
    rid, cid = create(client, parent)
    for headers in (teacher_other, parent_other):
        err(client.get(f"{BASE}/requests/{rid}", headers=headers), 404, "NOT_FOUND")
    err(client.get(f"{BASE}/cards/{cid}", headers=teacher_other), 404, "NOT_FOUND")
    err(decision(client, teacher_other, cid), 404, "NOT_FOUND")
    err(client.post(f"{BASE}/requests/{rid}/confirm", headers=parent_other), 404, "NOT_FOUND")
    err(client.get(BASE + "/cards?filter=invalid", headers=teacher), 422, "VALIDATION_FAILED")
    err(client.get(BASE + "/requests?size=101", headers=parent), 422, "VALIDATION_FAILED")
    err(client.get(BASE + "/requests/not-a-uuid", headers=parent), 422, "VALIDATION_FAILED")
    err(client.post(f"{BASE}/cards/{cid}/reclassify", headers=teacher, json={"version": 1, "risk_level": "urgent", "reason": "확인"}), 422, "VALIDATION_FAILED")
    err(client.post(f"{BASE}/requests/{seed.REQUEST_CONSULT}/confirm", headers=parent), 409, "INVALID_TRANSITION")


def test_request_notification_kinds_and_trace_audit(client, parent, teacher):
    from app.mock.notifications import TITLES
    from app.core.consultation_alerts import KINDS
    store.reset()
    rid, cid = create(client, parent)
    until = (store.now().date() + timedelta(days=1)).isoformat()
    held = decision(client, {**teacher, "X-Request-ID": "hold-trace"}, cid, "hold", hold_until=until, reason_text="추가 확인")
    assert held.status_code == 200
    assert next(e for e in reversed(store.events_of(UUID(rid))) if e.action == "held").detail["trace_id"] == "hold-trace"
    store.state().cards[UUID(cid)].hold_until = store.now().date()
    assert client.get(f"{BASE}/cards/{cid}", headers=teacher).status_code == 200
    assert decision(client, teacher, cid, version=3).status_code == 200
    assert client.post(f"{BASE}/requests/{rid}/confirm", headers=parent).status_code == 200
    assert decision(client, teacher, cid, "complete", version=4).status_code == 200
    rid, cid = create(client, parent, body="별도 사항")
    assert decision(client, teacher, cid, "escalate").status_code == 200
    rid, cid = create(client, parent, body="추가 사항")
    assert decision(client, teacher, cid, "dismiss", reason_code="policy").status_code == 200
    slot = store.slots_of_request(seed.REQUEST_CONSULT)[0]
    assert client.post(f"{BASE}/requests/{seed.REQUEST_CONSULT}/slot-choices", headers=parent, json={"slot_ids": [slot.id]}).status_code == 200
    slot.chosen_at = store.now() - timedelta(hours=25)
    assert client.get(f"{BASE}/requests/{seed.REQUEST_CONSULT}", headers=parent).status_code == 200
    body = {"classroom_id": str(seed.CLASS_STAR), "note_date": store.now().date().isoformat(), "activities": "산책", "supplies": "실내화"}
    assert client.post(BASE + "/daily-notes/drafts", headers=teacher, json=body).status_code == 202
    for note in store.state().notes.values():
        assert client.patch(f"{BASE}/daily-notes/{note.id}", headers=teacher,
                            json={"confirm": True, "resolved_checks": [c["id"] for c in note.open_checks]}).status_code == 200
    assert client.post(BASE + "/daily-notes/send", headers=teacher,
                       json={k: body[k] for k in ("classroom_id", "note_date")}).status_code == 200
    listed = client.get(BASE + "/daily-notes", headers=teacher,
                        params={"classroom_id": str(seed.CLASS_STAR), "date": body["note_date"]}).json()["items"]
    note = next(n for n in listed if n["child_id"] == str(seed.CHILD))
    assert client.post(f"{BASE}/daily-notes/{note['id']}/correct", headers=teacher, json={
        "version": note["version"], "content": note["content"], "reason_text": "[TEST] 알림장 기록 정정"}).status_code == 200
    care = client.post(BASE + "/requests", headers=parent, json={
        "client_request_id": "care-notification-test", "type": "medication", "child_id": str(seed.CHILD),
        "body": "[TEST] 보호자 원문"})
    assert care.status_code == 202, care.text
    care_id = care.json()["request"]["id"]
    for action in ("confirm", "complete"):
        assert client.post(f"{BASE}/requests/{care_id}/care-decisions", headers=teacher,
                           json={"decision": action, "version": 1}).status_code == 200
    # 시간·지연 기록으로 만드는 두 종류는 test_consultation_reminders에서 양쪽 저장소로 검사해요.
    assert {n.kind for n in store.state().notifications.values()} == set(TITLES) - set(KINDS)


def test_permission_denial_is_audited_without_parent_leak(client, parent_other, parent, teacher):
    rid, cid = create(client, parent)
    before = len(store.state().events)
    err(client.get(f"{BASE}/requests/{rid}", headers={**parent_other, "X-Request-ID": "scope-trace"}), 404, "NOT_FOUND")
    event = store.state().events[-1]
    assert len(store.state().events) == before + 1
    assert event.action == "permission_denied" and event.detail["trace_id"] == "scope-trace"
    assert event.actor_id == seed.PARENT_OTHER and event.request_id == UUID(rid)
    assert "permission_denied" not in client.get(f"{BASE}/requests/{rid}", headers=parent).text
    assert any(e["action"] == "permission_denied" for e in client.get(f"{BASE}/cards/{cid}", headers=teacher).json()["timeline"])


def test_rejected_old_draft_stays_done_after_replacement_is_sent(client, parent, teacher):
    rid, cid = create(client, parent)
    replacement = decision(client, teacher, cid, "reject", reason_code="tone").json()["next_card_id"]
    assert decision(client, teacher, replacement, "edit_approve", edited_content={"text": "[TEST] 다시 쓴 답"}).status_code == 200
    assert cid in [c["id"] for c in client.get(BASE + "/cards?filter=done", headers=teacher).json()["items"]]
    active = client.get(BASE + "/cards?filter=in_progress", headers=teacher).json()["items"]
    assert replacement in [c["id"] for c in active] and cid not in [c["id"] for c in active]


def test_inbox_type_counts_cross_status_filters_and_all_alias(client, teacher):
    implicit = client.get(BASE + "/cards", headers=teacher)
    explicit = client.get(BASE + "/cards?request_type=all", headers=teacher)
    assert implicit.status_code == explicit.status_code == 200
    assert implicit.json() == explicit.json()
    review = client.get(BASE + "/cards?filter=needs_review", headers=teacher).json()
    narrowed = client.get(BASE + "/cards?filter=needs_review&request_type=complaint", headers=teacher).json()
    assert set(narrowed["type_counts"]) == {"all", "complaint", "consultation", "inquiry"}
    assert narrowed["type_counts"] == review["type_counts"]
    assert review["type_counts"]["all"] == review["total"]
    assert narrowed["type_counts"]["complaint"] == narrowed["total"]
    assert all(c["request_type"] == "complaint" for c in narrowed["items"])
    urgent = client.get(BASE + "/cards?request_type=all&risk_level=urgent", headers=teacher).json()
    assert urgent["type_counts"]["all"] == urgent["total"]
