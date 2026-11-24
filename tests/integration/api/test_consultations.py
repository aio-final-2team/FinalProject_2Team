"""T35의 시간 선택·담임 확정 계약을 모의·DB 두 모드에서 확인해요."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Event
from uuid import UUID

import pytest
from sqlalchemy import text

from app import backend
from app.core.db import transaction
from app.mock import seed, store
from tests.integration.api.helpers import decision
from tests.integration.api.helpers import BASE, err
from tests.integration.api.test_cards import create, detail
from tests.integration.api.test_requests import notices


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


def test_booking_notification_has_own_kind_title_and_local_date_time(client, parent, teacher, consultation_backend):
    rid, cid, slots = prepare(client, parent, teacher)
    assert choose(client, parent, rid, slots[:1]).status_code == 200
    response = book(client, teacher, cid, slots[0])
    assert response.status_code == 200, response.text
    saved = [n for n in notices(consultation_backend, rid) if n["kind"] == "consultation_booked"]
    assert len(saved) == 1
    notice = saved[0]
    assert (str(notice["recipient_id"]), str(notice["card_id"]), notice["title"]) == (
        str(seed.PARENT), cid, "상담 예약 확정")
    start, end = (datetime.fromisoformat(slots[0]["period"][key]) for key in ("start", "end"))
    assert notice["body"] == f"{start:%Y-%m-%d %H:%M}~{end:%H:%M}"
    assert not any(n["kind"] == "sent_or_booked" for n in notices(consultation_backend, rid))
    err(book(client, teacher, cid, slots[0]), 409, "ALREADY_DECIDED")
    assert len([n for n in notices(consultation_backend, rid) if n["kind"] == "consultation_booked"]) == 1


@pytest.mark.parametrize("candidate_status", ["none", "discarded", "proposed", "chosen_by_parent"])
def test_reassign_consultation_reproposes_only_when_no_live_candidates(
    client, parent, teacher, director, consultation_backend, candidate_status
):
    rid, cid, slots = prepare(client, parent, teacher)
    if candidate_status == "chosen_by_parent":
        assert choose(client, parent, rid, slots).status_code == 200
    elif candidate_status != "proposed":
        if consultation_backend == "mock":
            for slot in slots:
                if candidate_status == "none":
                    del store.state().slots[slot["id"]]
                else:
                    store.state().slots[slot["id"]].status = "discarded"
        else:
            with transaction() as connection:
                statement = ("DELETE FROM consultation_slots WHERE card_id=:id" if candidate_status == "none"
                             else "UPDATE consultation_slots SET status='discarded' WHERE card_id=:id")
                connection.execute(text(statement), {"id": cid})
    before = notices(consultation_backend, rid)
    response = client.post(f"{BASE}/cards/{cid}/reassign", headers=director,
                           json={"assignee_id": str(seed.TEACHER_OTHER), "reason": "[TEST] 담당자 변경"})
    assert response.status_code == 200, response.text
    assert response.json()["card"]["version"] == 2
    new = [n for n in notices(consultation_backend, rid) if n["id"] not in {n["id"] for n in before}]
    reassigned = [n for n in new if n["kind"] == "reassigned"]
    assert len(reassigned) == 1
    assert str(reassigned[0]["recipient_id"]) == str(seed.TEACHER_OTHER)
    assert reassigned[0]["title"] == "요청이 배정됐어요"
    saved = client.get(f"{BASE}/requests/{rid}", headers=parent).json()
    needs_candidates = candidate_status in ("none", "discarded")
    assert saved["request"]["status"] == ("awaiting_review" if candidate_status == "chosen_by_parent" else "needs_info")
    candidates = saved["consultation"]["slots"]
    assert len(candidates) == 3
    assert {s["id"] for s in slots}.isdisjoint(s["id"] for s in candidates) == needs_candidates
    parent_notices = [n for n in new if str(n["recipient_id"]) == str(seed.PARENT)]
    assert [n["kind"] for n in parent_notices] == (["needs_info"] if needs_candidates else [])
    if consultation_backend == "mock":
        teachers = {store.state().slots[s["id"]].teacher_id for s in candidates}
    else:
        with transaction() as connection:
            teachers = set(connection.scalars(text("SELECT teacher_id FROM consultation_slots WHERE id=ANY(:ids)"),
                                               {"ids": [s["id"] for s in candidates]}))
    assert teachers == {seed.TEACHER_OTHER}
    if not needs_candidates:
        assert candidates == slots if candidate_status == "proposed" else all(
            s["status"] == "chosen_by_parent" for s in candidates)


@pytest.mark.parametrize("chosen", [False, True])
@pytest.mark.parametrize("conflict", ["busy", "booking", "delayed", "adjacent", "unavailable"])
def test_reassign_rechecks_conflicts_refills_only_missing_and_resets_lost_choices(
    client, parent, teacher, teacher_other, director, consultation_backend, chosen, conflict
):
    from types import SimpleNamespace
    from app.core.db import get_engine
    from tests.integration.api.test_consultation_reminders import booking

    rid, cid, slots = prepare(client, parent, teacher)
    if chosen:
        assert choose(client, parent, rid, slots[:2]).status_code == 200
    start, end = (datetime.fromisoformat(slots[0]["period"][key]) for key in ("start", "end"))
    engine = get_engine() if consultation_backend == "db" else None
    if conflict in ("booking", "delayed"):
        bid, _ = booking(SimpleNamespace(engine=engine), start if conflict == "booking" else start-timedelta(minutes=30),
                         teacher=seed.TEACHER_OTHER)
        if conflict == "delayed":
            if engine:
                with engine.begin() as connection:
                    connection.execute(text("UPDATE consultation_bookings SET expected_end_at=:end WHERE id=:id"),
                                       {"id": bid, "end": end})
            else:
                store.state().bookings[bid].expected_end_at = end
    else:
        if conflict == "adjacent":
            start, end = start-timedelta(minutes=30), start
        elif conflict == "unavailable":
            end = start+timedelta(days=15)
        if engine:
            with engine.begin() as connection:
                connection.execute(text("""
                    INSERT INTO staff_busy_blocks (org_id,user_id,period,kind)
                    VALUES (:org,:teacher,tstzrange(:start,:end,'[)'),'meeting')
                """), {"org": seed.ORG, "teacher": seed.TEACHER_OTHER, "start": start, "end": end})
        else:
            store.state().staff_busy_blocks.append({"org_id": seed.ORG, "user_id": seed.TEACHER_OTHER,
                                                   "period": {"start": start, "end": end}})
    before = {n["id"] for n in notices(consultation_backend, rid)}
    response = client.post(f"{BASE}/cards/{cid}/reassign", headers=director,
                           json={"assignee_id": str(seed.TEACHER_OTHER), "reason": "[TEST] 일정 재검사"})
    assert response.status_code == 200, response.text
    assert response.json()["card"]["version"] == 2
    saved = client.get(f"{BASE}/requests/{rid}", headers=parent).json()
    candidates = saved["consultation"]["slots"]
    discarded = slots if conflict == "unavailable" else slots[:1] if conflict != "adjacent" else []
    kept = [s for s in slots if s not in discarded]
    assert len(candidates) == (0 if conflict == "unavailable" else 3)
    assert {s["id"] for s in kept} <= {s["id"] for s in candidates}
    assert {s["id"] for s in discarded}.isdisjoint(s["id"] for s in candidates)
    if engine:
        with engine.connect() as connection:
            rows = connection.execute(text("SELECT id,status,teacher_id,round,chosen_at FROM consultation_slots WHERE card_id=:id"),
                                      {"id": cid}).mappings().all()
    else:
        rows = [s.__dict__ for s in store.slots_of_request(UUID(rid))]
    assert {r["id"] for r in rows if r["status"] == "discarded"} == {s["id"] for s in discarded}
    assert all(r["teacher_id"] == seed.TEACHER_OTHER for r in rows if r["status"] != "discarded")
    assert len([r for r in rows if r["round"] == 2]) == (1 if conflict not in ("adjacent", "unavailable") else 0)
    reset = chosen and bool(discarded)
    assert saved["request"]["status"] == ("awaiting_review" if chosen and not reset else "needs_info")
    parent_notices = [n["kind"] for n in notices(consultation_backend, rid)
                      if n["id"] not in before and str(n["recipient_id"]) == str(seed.PARENT)]
    assert parent_notices == (["needs_info"] if reset else [])
    if reset:
        assert all(r["status"] == "proposed" and r["chosen_at"] is None for r in rows if r["status"] != "discarded")
        if candidates:
            assert choose(client, parent, rid, candidates[-1:]).status_code == 200
            assert book(client, teacher_other, cid, candidates[-1], version=2).status_code == 200


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


@pytest.mark.parametrize("reassign", [False, True])
def test_colliding_booking_discards_only_conflict_and_reproposes_for_parent(
    client, parent, teacher, teacher_other, director, consultation_backend, reassign
):
    pairs = [prepare(client, parent, teacher) for _ in range(2)]
    for index, (rid, _, slots) in enumerate(pairs):
        assert choose(client, parent, rid, slots[index:] if index else slots[:1]).status_code == 200
    # 예전 체크가 겹친 경우도 최종 확정에서 지키도록 선택 후 겹침을 만들어요.
    set_period(pairs[1][2][1], pairs[0][2][0]["period"], consultation_backend)
    assert pairs[0][2][0]["period"] == pairs[1][2][0]["period"]
    assert book(client, teacher, pairs[0][1], pairs[0][2][0]).status_code == 200
    rid, cid, slots = pairs[1]
    before = notices(consultation_backend, rid)
    err(book(client, teacher, cid, slots[1]), 409, "SLOT_TAKEN")
    saved = client.get(f"{BASE}/requests/{rid}", headers=parent).json()
    assert saved["request"]["status"] == "needs_info"
    assert saved["consultation"]["booking"] is None
    after = saved["consultation"]["slots"]
    assert slots[1]["id"] not in {s["id"] for s in after}
    assert {slots[0]["id"], slots[2]["id"]} <= {s["id"] for s in after}
    assert next(s for s in after if s["id"] == slots[2]["id"])["status"] == "chosen_by_parent"
    new_slots = [s for s in after if s["id"] not in {s["id"] for s in slots}]
    assert len(new_slots) == 3
    assert all(s["period"]["start"] >= pairs[0][2][0]["period"]["end"] for s in new_slots)
    timeline = detail(client, teacher, cid)["timeline"]
    event = next(e for e in timeline if e["action"] == "slot_conflict_reproposed")
    assert event["detail"]["slot_id"] == slots[1]["id"]
    assert set(event["detail"]["new_slot_ids"]) == {s["id"] for s in new_slots}
    assert not any(e["action"] in ("approved", "booked") for e in timeline)
    new = [n for n in notices(consultation_backend, rid) if n["id"] not in {n["id"] for n in before}]
    assert [(n["kind"], str(n["recipient_id"])) for n in new] == [("needs_info", str(seed.PARENT))]
    if reassign:
        start = min(datetime.fromisoformat(s["period"]["start"]) for s in after)
        end = max(datetime.fromisoformat(s["period"]["end"]) for s in after)
        if consultation_backend == "mock":
            store.state().staff_busy_blocks.append({"org_id": seed.ORG, "user_id": seed.TEACHER_OTHER,
                                                   "period": {"start": start, "end": end}})
        else:
            with transaction() as connection:
                connection.execute(text("""
                    INSERT INTO staff_busy_blocks (org_id,user_id,period,kind)
                    VALUES (:org,:teacher,tstzrange(:start,:end,'[)'),'meeting')
                """), {"org": seed.ORG, "teacher": seed.TEACHER_OTHER, "start": start, "end": end})
        response = client.post(f"{BASE}/cards/{cid}/reassign", headers=director,
                               json={"assignee_id": str(seed.TEACHER_OTHER), "reason": "[TEST] 여러 회차 재검사"})
        assert response.status_code == 200, response.text
        replacements = client.get(f"{BASE}/requests/{rid}", headers=parent).json()["consultation"]["slots"]
        assert len(replacements) == len(after) == 5
        assert {s["id"] for s in after}.isdisjoint(s["id"] for s in replacements)
        assert all(datetime.fromisoformat(s["period"]["start"]) >= end for s in replacements)
        assert choose(client, parent, rid, replacements[:1]).status_code == 200
        assert book(client, teacher_other, cid, replacements[0], version=3).status_code == 200
        return
    assert choose(client, parent, rid, [slots[2]]).status_code == 200
    assert book(client, teacher, cid, slots[2], version=2).status_code == 200


def test_simultaneous_confirmations_of_same_card_only_record_once(
    client, parent, teacher, consultation_backend, monkeypatch
):
    from app.mock import cards as mock_cards
    from app.modules.cards import cards as db_cards

    rid, cid, slots = prepare(client, parent, teacher)
    assert choose(client, parent, rid, slots[:1]).status_code == 200
    cards = mock_cards if consultation_backend == "mock" else db_cards
    original = cards.version
    entered, release, second_started = Event(), Event(), Event()

    def pause(*args, **kwargs):
        original(*args, **kwargs)
        entered.set()
        assert release.wait(10)

    def second():
        second_started.set()
        return book(client, teacher, cid, slots[0])

    monkeypatch.setattr(cards, "version", pause)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(book, client, teacher, cid, slots[0])
        try:
            assert entered.wait(10)
            other = pool.submit(second)
            assert second_started.wait(5)
            with pytest.raises(TimeoutError):
                other.result(timeout=0.5)
        finally:
            release.set()
        responses = [first.result(timeout=10), other.result(timeout=10)]
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


def test_reassigned_teacher_from_other_class_can_confirm_as_card_assignee(client, parent, teacher, teacher_other, director):
    rid, cid, slots = prepare(client, parent, teacher)
    assert choose(client, parent, rid, slots[:1]).status_code == 200
    response = client.post(f"{BASE}/cards/{cid}/reassign", headers=director,
                           json={"assignee_id": str(seed.TEACHER_OTHER), "reason": "[TEST] 재배정"})
    assert response.status_code == 200, response.text
    assert client.get(f"{BASE}/cards/{cid}", headers=teacher_other).status_code == 200
    err(book(client, teacher, cid, slots[0], version=2), 403, "FORBIDDEN_ROLE")
    assert book(client, teacher_other, cid, slots[0], version=2).status_code == 200


def set_period(slot, period, mode):
    values = {key: datetime.fromisoformat(value) if isinstance(value, str) else value for key, value in period.items()}
    if mode == "mock":
        store.state().slots[slot["id"]].period = values
    else:
        with transaction() as connection:
            connection.execute(text("UPDATE consultation_slots SET period=tstzrange(:start,:end,'[)') WHERE id=:id"),
                               {"id": slot["id"], **values})


def age_choice(slot, mode):
    if mode == "mock":
        store.state().slots[slot["id"]].chosen_at = store.now()-timedelta(hours=25)
    else:
        with transaction() as connection:
            connection.execute(text("UPDATE consultation_slots SET chosen_at=now()-interval '25 hours' WHERE id=:id"),
                               {"id": slot["id"]})


@pytest.mark.parametrize("stage", ["check", "book"])
def test_started_candidate_is_rejected_without_state_change(client, parent, teacher, consultation_backend, stage):
    rid, cid, slots = prepare(client, parent, teacher)
    if stage == "book":
        assert choose(client, parent, rid, slots[:1]).status_code == 200
    start = store.now()-timedelta(hours=1)
    set_period(slots[0], {"start": start, "end": start+timedelta(minutes=30)}, consultation_backend)
    before = detail(client, teacher, cid)
    response = choose(client, parent, rid, slots[:1]) if stage == "check" else book(client, teacher, cid, slots[0])
    err(response, 409, "SLOT_PAST")
    assert detail(client, teacher, cid) == before
    assert client.get(f"{BASE}/requests/{rid}", headers=parent).json()["consultation"]["booking"] is None


@pytest.mark.parametrize("automatic", [False, True])
def test_hold_keeps_expired_choice_until_resume_then_parent_can_choose(
    client, parent, teacher, consultation_backend, automatic
):
    rid, cid, slots = prepare(client, parent, teacher)
    assert choose(client, parent, rid, slots[:1]).status_code == 200
    until = (store.now().date()+timedelta(days=3)).isoformat()
    assert decision(client, teacher, cid, "hold", hold_until=until, reason_text="[TEST] 확인 중").status_code == 200
    age_choice(slots[0], consultation_backend)
    for _ in range(2):
        saved = client.get(f"{BASE}/requests/{rid}", headers=parent).json()
        assert saved["request"]["status"] == "on_hold"
        assert saved["consultation"]["slots"][0]["status"] == "chosen_by_parent"
    err(choose(client, parent, rid, slots[:1]), 409, "INVALID_TRANSITION")
    if automatic:
        if consultation_backend == "mock":
            store.state().cards[UUID(cid)].hold_until = store.now().date()
        else:
            with transaction() as connection:
                connection.execute(text("UPDATE cards SET hold_until=CURRENT_DATE WHERE id=:id"), {"id": cid})
        version = 3
    else:
        resumed = decision(client, teacher, cid, "resume", version=2)
        assert resumed.status_code == 200, resumed.text
        assert resumed.json()["request"]["status"] == "needs_info"
        version = 3
    assert client.get(f"{BASE}/requests/{rid}", headers=parent).json()["request"]["status"] == "needs_info"
    assert choose(client, parent, rid, slots[:1]).status_code == 200
    assert book(client, teacher, cid, slots[0], version=version).status_code == 200
    assert len([e for e in detail(client, teacher, cid)["timeline"] if e["action"] == "slot_hold_expired"]) == 1


@pytest.mark.parametrize("expired", [False, True])
def test_consultation_escalation_requires_instruction_and_closes_report(
    client, parent, teacher, director, consultation_backend, expired
):
    rid, cid, slots = prepare(client, parent, teacher)
    assert choose(client, parent, rid, slots[:1]).status_code == 200
    waiting = client.get(f"{BASE}/overview", headers=director).json()["waiting"]
    escalated = decision(client, teacher, cid, "escalate")
    assert escalated.status_code == 200, escalated.text
    report_id = escalated.json()["next_card_id"]
    assert client.get(f"{BASE}/overview", headers=director).json()["waiting"] == waiting+1
    if expired:
        age_choice(slots[0], consultation_backend)
    saved = client.get(f"{BASE}/requests/{rid}", headers=parent).json()
    assert saved["request"]["status"] == "escalated"
    assert saved["consultation"]["slots"][0]["status"] == "chosen_by_parent"
    err(book(client, teacher, cid, slots[0], version=2), 409, "INVALID_TRANSITION")
    assert detail(client, director, report_id)["card"]["status"] == "pending"
    # 담임이 올린 보고는 확인만으로 닫지 못해요. 닫히면 요청이 escalated에서 풀 길이 없어요.
    err(decision(client, director, report_id, "acknowledge"), 409, "INVALID_TRANSITION")
    assert detail(client, director, report_id)["card"]["status"] == "pending"
    response = client.post(f"{BASE}/cards/{report_id}/instructions", headers=director,
                           json={"version": 1, "instruction": "[TEST] 상담을 진행해 주세요"})
    assert response.status_code == 200, response.text
    assert response.json()["card"]["status"] == "done"
    assert client.get(f"{BASE}/overview", headers=director).json()["waiting"] == waiting
    if expired:
        assert client.get(f"{BASE}/requests/{rid}", headers=parent).json()["request"]["status"] == "needs_info"
        assert choose(client, parent, rid, slots[:1]).status_code == 200
    assert book(client, teacher, cid, slots[0], version=2).status_code == 200
    err(client.post(f"{BASE}/cards/{report_id}/instructions", headers=director,
                    json={"version": 1, "instruction": "[TEST] 중복 지시"}), 409, "ALREADY_DECIDED")
    assert len([e for e in detail(client, teacher, cid)["timeline"] if e["action"] == "booked"]) == 1


@pytest.mark.parametrize("confirmed", [False, True])
def test_choice_rejects_other_live_hold_or_confirmed_booking_atomically(
    client, parent, teacher, consultation_backend, confirmed
):
    first, second = [prepare(client, parent, teacher) for _ in range(2)]
    # 두 번 생성하는 사이 날짜가 바뀌어도 충돌 상황은 같게 맞춰요.
    for candidate, original in zip(second[2], first[2], strict=True):
        set_period(candidate, original["period"], consultation_backend)
    assert choose(client, parent, first[0], first[2][:1]).status_code == 200
    if confirmed:
        assert book(client, teacher, first[1], first[2][0]).status_code == 200
    # 자유 후보와 겹치는 후보를 함께 보내도 부분 체크하지 않아요.
    before = detail(client, teacher, second[1])
    err(choose(client, parent, second[0], second[2][:2]), 409, "SLOT_TAKEN")
    assert detail(client, teacher, second[1]) == before
    assert choose(client, parent, second[0], second[2][1:2]).status_code == 200


def test_booking_checks_version_and_candidate_before_nonconsultation_kind(client, parent, teacher):
    _, cid = create(client, parent, teacher, type="inquiry", body="[TEST] 문의")
    err(book(client, teacher, cid, {"id": 9223372036854775807}, version=9), 409, "CARD_VERSION_CONFLICT")
    err(book(client, teacher, cid, {"id": 9223372036854775807}), 404, "NOT_FOUND")


@pytest.mark.parametrize("confirmed", [False, True])
def test_new_candidates_skip_live_checks_and_confirmed_bookings(client, parent, teacher, confirmed):
    rid, cid, slots = prepare(client, parent, teacher)
    assert choose(client, parent, rid, slots[:2]).status_code == 200
    if confirmed:
        assert book(client, teacher, cid, slots[0]).status_code == 200
    _, new_cid, candidates = prepare(client, parent, teacher)
    busy = slots[:1] if confirmed else slots[:2]
    for candidate in candidates:
        for taken in busy:
            assert candidate["period"]["start"] >= taken["period"]["end"] or taken["period"]["start"] >= candidate["period"]["end"]
    # 제안부터 빈 칸을 주므로 이어지는 보호자 체크도 성공해요.
    new_rid = detail(client, teacher, new_cid)["request"]["id"]
    assert choose(client, parent, new_rid, candidates[:1]).status_code == 200


@pytest.mark.parametrize("stage", ["choice", "booking"])
def test_previously_issued_candidate_rejects_new_delay_overlap(
    client, parent, teacher, consultation_backend, stage
):
    from types import SimpleNamespace
    from app.core.db import get_engine
    from tests.integration.api.test_consultation_reminders import booking
    rid, cid, offered = prepare(client, parent, teacher)
    slot = offered[0]
    if stage == "booking":
        assert choose(client, parent, rid, [slot]).status_code == 200
    start = datetime.fromisoformat(slot["period"]["start"])
    engine = get_engine() if consultation_backend == "db" else None
    bid, _ = booking(SimpleNamespace(engine=engine), start-timedelta(minutes=30))
    until = start+timedelta(minutes=20)
    if engine:
        with engine.begin() as c:
            c.execute(text("UPDATE consultation_bookings SET expected_end_at=:until WHERE id=:id"),
                      {"id": bid, "until": until})
    else:
        store.state().bookings[bid].expected_end_at = until
    response = choose(client, parent, rid, [slot]) if stage == "choice" else book(client, teacher, cid, slot)
    err(response, 409, "SLOT_TAKEN")
    assert client.get(f"{BASE}/requests/{rid}", headers=parent).json()["consultation"]["booking"] is None


def test_none_fit_prefers_requested_window_and_notifies_teacher(client, parent, teacher, consultation_backend):
    rid, cid, slots = prepare(client, parent, teacher)
    day = store.now().date()+timedelta(days=7)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    preferred = f"[TEST] {day} 오후 4시~5시"
    before = notices(consultation_backend, rid)
    response = client.post(f"{BASE}/requests/{rid}/slot-choices", headers=parent,
                           json={"none_fit": True, "preferred_times": preferred})
    assert response.status_code == 200, response.text
    saved = client.get(f"{BASE}/requests/{rid}", headers=parent).json()
    after = saved["consultation"]["slots"]
    first = datetime.fromisoformat(after[0]["period"]["start"])
    assert first.date() == day and first.hour == 16
    assert set(s["id"] for s in slots).isdisjoint(s["id"] for s in after)
    assert saved["request"]["status"] == "needs_info"
    new = [n for n in notices(consultation_backend, rid) if n["id"] not in {n["id"] for n in before}]
    assert len(new) == 1
    assert (new[0]["kind"], str(new[0]["recipient_id"]), str(new[0]["card_id"]), new[0]["body"]) == (
        "parent_message", str(seed.TEACHER), cid, preferred)
    event = detail(client, teacher, cid)["timeline"][-1]
    assert event["detail"]["preferred_times"] == preferred


@pytest.mark.parametrize("phase", ["needs_info", "awaiting_review"])
@pytest.mark.parametrize("finish", ["acknowledge", "resume", "automatic"])
def test_consultation_report_decisions_do_not_change_parent_flow(
    client, parent, teacher, director, consultation_backend, phase, finish
):
    rid, cid = create(client, parent, teacher, type="consultation", body="[TEST] 아이가 다쳤어요 상담")
    slots = client.get(f"{BASE}/requests/{rid}", headers=parent).json()["consultation"]["slots"]
    report_id = next(row["id"] for row in client.get(BASE+"/cards?size=100", headers=director).json()["items"]
                     if row["request_id"] == rid and row["kind"] == "director_report")
    if phase == "awaiting_review":
        assert choose(client, parent, rid, slots[:1]).status_code == 200
    before = client.get(f"{BASE}/requests/{rid}", headers=parent).json()
    parent_notices = [n for n in notices(consultation_backend, rid) if str(n["recipient_id"]) == str(seed.PARENT)]
    err(decision(client, teacher, report_id, "acknowledge"), 403, "FORBIDDEN_ROLE")
    held = decision(client, director, report_id, "hold", reason_text="[TEST] 보고 확인 예정",
                    hold_until=(store.now().date()+timedelta(days=3)).isoformat())
    assert held.status_code == 200, held.text
    assert held.json()["request"]["status"] == phase
    assert held.json()["card"]["status"] == "on_hold"
    assert client.get(f"{BASE}/requests/{rid}", headers=parent).json() == before
    if finish == "automatic":
        if consultation_backend == "mock":
            store.state().cards[UUID(report_id)].hold_until = store.now().date()
        else:
            with transaction() as connection:
                connection.execute(text("UPDATE cards SET hold_until=CURRENT_DATE WHERE id=:id"), {"id": report_id})
        assert detail(client, director, report_id)["card"]["status"] == "pending"
    else:
        response = decision(client, director, report_id, finish, version=2)
        assert response.status_code == 200, response.text
        assert response.json()["request"]["status"] == phase
    assert client.get(f"{BASE}/requests/{rid}", headers=parent).json() == before
    assert [n for n in notices(consultation_backend, rid) if str(n["recipient_id"]) == str(seed.PARENT)] == parent_notices
    if finish != "acknowledge":
        acknowledged = decision(client, director, report_id, "acknowledge", version=3)
        assert acknowledged.status_code == 200, acknowledged.text
    final = detail(client, director, report_id)
    assert final["card"]["status"] == "done"
    event = next(e for e in final["timeline"] if e["action"] == "report_acknowledged")
    assert event["card_id"] == report_id and event["from_status"] is None and event["to_status"] is None
    if phase == "needs_info":
        assert choose(client, parent, rid, slots[:1]).status_code == 200
    assert book(client, teacher, cid, slots[0]).status_code == 200


def test_acknowledge_only_accepts_consultation_report_and_is_idempotent_per_version(client, parent, teacher, director):
    rid, cid = create(client, parent, teacher, type="consultation", body="[TEST] 상담 다쳤어요")
    report_id = next(row["id"] for row in client.get(BASE+"/cards?size=100", headers=director).json()["items"]
                     if row["request_id"] == rid and row["kind"] == "director_report")
    err(decision(client, teacher, cid, "acknowledge"), 409, "INVALID_TRANSITION")
    err(decision(client, director, report_id, "acknowledge", version=9), 409, "CARD_VERSION_CONFLICT")
    response = decision(client, director, report_id, "acknowledge")
    assert response.status_code == 200, response.text
    err(decision(client, director, report_id, "acknowledge"), 409, "ALREADY_DECIDED")
    assert response.json()["request"]["status"] == "needs_info"
    assert len([e for e in detail(client, director, report_id)["timeline"] if e["action"] == "report_acknowledged"]) == 1
    other_rid, _ = create(client, parent, teacher, body="[TEST] 민원 아이 다쳤어요")
    other_report = next(row["id"] for row in client.get(BASE+"/cards?size=100", headers=director).json()["items"]
                        if row["request_id"] == other_rid and row["kind"] == "director_report")
    err(decision(client, director, other_report, "acknowledge"), 409, "INVALID_TRANSITION")


def test_dismiss_consultation_releases_chosen_holds(client, parent, teacher, consultation_backend):
    rid, cid, slots = prepare(client, parent, teacher)
    assert choose(client, parent, rid, slots[:2]).status_code == 200
    response = decision(client, teacher, cid, "dismiss", reason_code="policy", reason_text="[TEST] 반려")
    assert response.status_code == 200, response.text
    assert detail(client, teacher, cid)["parent_choices"] == []
    if consultation_backend == "mock":
        assert all(store.state().slots[s["id"]].status == "discarded" for s in slots[:2])
    else:
        with transaction() as connection:
            assert connection.scalar(text("SELECT count(*) FROM consultation_slots WHERE card_id=:id AND status='chosen_by_parent'"),
                                     {"id": cid}) == 0
    _, _, offered = prepare(client, parent, teacher)
    assert offered[0]["period"] == slots[0]["period"]


@pytest.mark.parametrize("has_candidates", [False, True])
def test_unassigned_consultation_notifies_director_allows_choices_and_recovers_on_reassign(
    client, parent, teacher_other, director, consultation_backend, has_candidates
):
    from uuid import uuid4
    from app.modules.consultations.slots import propose_slots

    if consultation_backend == "mock":
        store.state().classroom_staff[:] = [s for s in store.state().classroom_staff if s.classroom_id != seed.CLASS_STAR]
    else:
        with transaction() as connection:
            connection.execute(text("DELETE FROM classroom_staff WHERE classroom_id=:id"), {"id": seed.CLASS_STAR})
    response = client.post(BASE+"/requests", headers=parent,
                           json={"client_request_id": str(uuid4()), "child_id": str(seed.CHILD),
                                 "type": "consultation", "body": "[TEST] 담임 없는 반 상담"})
    assert response.status_code == 202, response.text
    rid = response.json()["request"]["id"]
    cid = next(row["id"] for row in client.get(BASE+"/cards?size=100", headers=director).json()["items"]
               if row["request_id"] == rid and row["kind"] == "consult_slots")
    staff_notices = [n for n in notices(consultation_backend, rid) if n["kind"] == "new_card"]
    assert len(staff_notices) == 1 and str(staff_notices[0]["recipient_id"]) == str(seed.DIRECTOR)
    assert detail(client, director, cid)["card"]["status"] == "unassigned"
    if consultation_backend == "db" and has_candidates:
        with transaction() as connection:
            req = dict(connection.execute(text("SELECT * FROM requests WHERE id=:id"), {"id": rid}).mappings().one())
            propose_slots(connection, req, {"id": cid}, seed.TEACHER)
    elif not has_candidates:
        if consultation_backend == "mock":
            for slot in list(store.slots_of_request(UUID(rid))):
                del store.state().slots[slot.id]
    before = client.get(f"{BASE}/requests/{rid}", headers=parent).json()["consultation"]["slots"]
    if has_candidates:
        assert choose(client, parent, rid, before[:1]).status_code == 200
        assert detail(client, director, cid)["card"]["status"] == "unassigned"
    response = client.post(f"{BASE}/cards/{cid}/reassign", headers=director,
                           json={"assignee_id": str(seed.TEACHER_OTHER), "reason": "[TEST] 담당 지정"})
    assert response.status_code == 200, response.text
    after = client.get(f"{BASE}/requests/{rid}", headers=parent).json()["consultation"]["slots"]
    assert len(after) == 3
    if not has_candidates:
        assert choose(client, parent, rid, after[:1]).status_code == 200
    assert book(client, teacher_other, cid, after[0], version=2).status_code == 200
    if consultation_backend == "mock":
        booking = store.confirmed_booking_of(UUID(rid))
        assert booking.teacher_id == seed.TEACHER_OTHER and booking.confirmed_by == seed.TEACHER_OTHER
    else:
        with transaction() as connection:
            assert connection.execute(text("SELECT teacher_id,confirmed_by FROM consultation_bookings WHERE request_id=:id"),
                                      {"id": rid}).one() == (seed.TEACHER_OTHER, seed.TEACHER_OTHER)
