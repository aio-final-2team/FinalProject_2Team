"""T35의 시간 선택·담임 확정 계약을 모의·DB 두 모드에서 확인해요."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy import text

from app import backend
from app.core.db import transaction
from app.mock import seed, store
from tests.integration.api.helpers import BASE, err
from tests.integration.api.test_cards import create, detail


@pytest.fixture(autouse=True, params=["mock", "db"])
def consultation_backend(request, monkeypatch):
    if request.param == "db":
        request.getfixturevalue("seeded_db")
        from app.core import users
        from app.modules.cards import cards, card_views
        from app.modules.requests import requests
    else:
        from app.mock import cards, card_views, request_actions as requests
        users = store
    for name, module in dict(users=users, cards=cards, card_views=card_views, request_actions=requests).items():
        monkeypatch.setattr(backend, name, module)
    return request.param


def prepare(client, parent, teacher):
    rid, cid = create(client, parent, teacher, type="consultation", body="[TEST] 친구 관계 상담")
    slots = client.get(f"{BASE}/requests/{rid}", headers=parent).json()["consultation"]["slots"]
    assert len(slots) == 3
    return rid, cid, slots


def choose(client, parent, rid, slots):
    return client.post(f"{BASE}/requests/{rid}/slot-choices", headers=parent,
                       json={"slot_ids": [s["id"] for s in slots]})


def book(client, teacher, cid, slot, version=1):
    return client.post(f"{BASE}/cards/{cid}/bookings", headers=teacher,
                       json={"version": version, "slot_id": slot["id"]})


def test_choice_booking_permissions_version_events_and_parent_view(
    client, parent, parent_other, teacher, teacher_other, director
):
    rid, cid, slots = prepare(client, parent, teacher)
    err(choose(client, teacher, rid, slots[:1]), 403, "FORBIDDEN_ROLE")
    err(choose(client, parent_other, rid, slots[:1]), 404, "NOT_FOUND")
    err(book(client, teacher, cid, slots[0]), 409, "SLOT_NOT_CHOSEN")
    assert choose(client, parent, rid, slots[:2]).json()["request"]["status"] == "awaiting_review"
    selected = detail(client, teacher, cid)["parent_choices"]
    assert len(selected) == 2
    assert all(s["chosen_at"] < s["hold_expires_at"] for s in selected)
    err(choose(client, parent, rid, slots[:1]), 409, "INVALID_TRANSITION")
    err(book(client, parent, cid, slots[0]), 403, "FORBIDDEN_ROLE")
    err(book(client, director, cid, slots[0]), 403, "FORBIDDEN_ROLE")
    err(book(client, teacher_other, cid, slots[0]), 404, "NOT_FOUND")
    err(book(client, teacher, cid, slots[0], version=9), 409, "CARD_VERSION_CONFLICT")
    err(book(client, teacher, cid, slots[2]), 409, "SLOT_NOT_CHOSEN")
    response = book(client, teacher, cid, slots[0])
    assert response.status_code == 200, response.text
    saved = client.get(f"{BASE}/requests/{rid}", headers=parent).json()
    assert saved["request"]["status"] == "sent_or_booked"
    assert saved["request"]["status_label"] == "예약 확정"
    assert saved["consultation"]["booking"] == response.json()["booking"]
    assert len(saved["consultation"]["slots"]) == 1
    assert saved["consultation"]["slots"][0]["status"] == "confirmed"
    card = detail(client, teacher, cid)
    assert card["card"]["status"] == "done" and card["card"]["version"] == 2
    assert [e["action"] for e in card["timeline"]][-2:] == ["approved", "booked"]
    assert [(e["from_status"], e["to_status"]) for e in card["timeline"][-2:]] == [
        ("awaiting_review", "approved"), ("approved", "sent_or_booked")]
    err(book(client, teacher, cid, slots[0]), 409, "ALREADY_DECIDED")


def test_other_request_and_discarded_round_candidates_are_not_selectable(client, parent, teacher):
    rid, cid, slots = prepare(client, parent, teacher)
    other_rid, _, others = prepare(client, parent, teacher)
    err(choose(client, parent, rid, others[:1]), 404, "NOT_FOUND")
    response = client.post(f"{BASE}/requests/{rid}/slot-choices", headers=parent,
                           json={"none_fit": True, "preferred_times": "[TEST] 다른 시간"})
    assert response.status_code == 200 and response.json()["request"]["status"] == "needs_info"
    after = client.get(f"{BASE}/requests/{rid}", headers=parent).json()["consultation"]["slots"]
    assert len(after) == 3 and not ({s["id"] for s in slots} & {s["id"] for s in after})
    assert after[0]["period"]["start"] > slots[0]["period"]["start"]
    err(choose(client, parent, rid, slots[:1]), 404, "NOT_FOUND")
    assert choose(client, parent, rid, after[:1]).status_code == 200
    assert choose(client, parent, other_rid, others[:1]).status_code == 200
    err(book(client, teacher, cid, others[0]), 404, "NOT_FOUND")
    assert book(client, teacher, cid, after[0]).status_code == 200


def test_colliding_booking_rolls_back_and_adjacent_candidate_can_be_booked(client, parent, teacher):
    pairs = [prepare(client, parent, teacher) for _ in range(2)]
    for rid, _, slots in pairs:
        assert choose(client, parent, rid, slots).status_code == 200
    assert pairs[0][2][0]["period"] == pairs[1][2][0]["period"]
    assert book(client, teacher, pairs[0][1], pairs[0][2][0]).status_code == 200
    rid, cid, slots = pairs[1]
    before = detail(client, teacher, cid)
    err(book(client, teacher, cid, slots[0]), 409, "SLOT_TAKEN")
    assert detail(client, teacher, cid) == before
    assert client.get(f"{BASE}/requests/{rid}", headers=parent).json()["consultation"]["booking"] is None
    assert book(client, teacher, cid, slots[1]).status_code == 200


def test_simultaneous_confirmations_of_same_card_only_record_once(client, parent, teacher):
    rid, cid, slots = prepare(client, parent, teacher)
    assert choose(client, parent, rid, slots[:1]).status_code == 200
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: book(client, teacher, cid, slots[0]), range(2)))
    assert sorted(r.status_code for r in responses) == [200, 409]
    assert next(r for r in responses if r.status_code == 409).json()["error"]["code"] == "ALREADY_DECIDED"
    events = detail(client, teacher, cid)["timeline"]
    assert len([e for e in events if e["action"] == "booked"]) == 1


def test_expired_choice_is_released_once_and_can_be_selected_again(client, parent, teacher, consultation_backend):
    rid, cid, slots = prepare(client, parent, teacher)
    assert choose(client, parent, rid, slots[:1]).status_code == 200
    if consultation_backend == "mock":
        store.state().slots[slots[0]["id"]].chosen_at = store.now() - timedelta(hours=25)
    else:
        with transaction() as connection:
            connection.execute(text("UPDATE consultation_slots SET chosen_at=now()-interval '25 hours' WHERE id=:id"),
                               {"id": slots[0]["id"]})
    err(book(client, teacher, cid, slots[0]), 409, "SLOT_NOT_CHOSEN")
    assert client.get(f"{BASE}/requests/{rid}", headers=parent).json()["request"]["status"] == "needs_info"
    for _ in range(2):
        data = detail(client, teacher, cid)
        assert data["parent_choices"] == []
        assert len([e for e in data["timeline"] if e["action"] == "slot_hold_expired"]) == 1
    if consultation_backend == "mock":
        notifications = [n for n in store.state().notifications.values()
                         if n.request_id == UUID(rid) and n.kind == "slot_hold_expired"]
        assert len(notifications) == 1
    else:
        with transaction() as connection:
            assert connection.scalar(text("SELECT count(*) FROM notifications WHERE request_id=:id AND kind='slot_hold_expired'"),
                                     {"id": rid}) == 1
    assert choose(client, parent, rid, slots[:1]).status_code == 200
    assert book(client, teacher, cid, slots[0]).status_code == 200


def test_rejected_consultation_has_new_candidates_and_needs_parent_choice(client, parent, teacher):
    rid, cid, slots = prepare(client, parent, teacher)
    assert choose(client, parent, rid, slots[:1]).status_code == 200
    response = client.post(f"{BASE}/cards/{cid}/decisions", headers=teacher,
                           json={"version": 1, "decision": "reject", "reason_code": "slot_unavailable"})
    assert response.status_code == 200, response.text
    next_card = response.json()["next_card_id"]
    assert next_card and next_card != cid
    current = client.get(f"{BASE}/requests/{rid}", headers=parent).json()
    assert current["request"]["status"] == "needs_info"
    after = current["consultation"]["slots"]
    assert len(after) == 3 and all(s["status"] == "proposed" for s in after)
    err(choose(client, parent, rid, slots[:1]), 404, "NOT_FOUND")
    assert choose(client, parent, rid, after[:1]).status_code == 200
    assert book(client, teacher, next_card, after[0]).status_code == 200


def test_reassigned_teacher_from_other_class_cannot_confirm(client, parent, teacher, teacher_other, director):
    rid, cid, slots = prepare(client, parent, teacher)
    assert choose(client, parent, rid, slots[:1]).status_code == 200
    response = client.post(f"{BASE}/cards/{cid}/reassign", headers=director,
                           json={"assignee_id": str(seed.TEACHER_OTHER), "reason": "[TEST] 재배정"})
    assert response.status_code == 200, response.text
    assert client.get(f"{BASE}/cards/{cid}", headers=teacher_other).status_code == 200
    err(book(client, teacher_other, cid, slots[0], version=2), 403, "FORBIDDEN_ROLE")
    assert book(client, teacher, cid, slots[0], version=2).status_code == 200
