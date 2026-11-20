"""실제 PG의 빈 시간 계산·배제 제약·동시 확정·알림 원자성을 검증해요."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, time, timedelta
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import event, text

from app.core import schedule
from app.core.schedule import KST
from app.mock import seed
from app.modules.consultations import slots
from tests.integration.db.test_cards import BASE, auth, create


def future_day():
    day = datetime.now(KST).date() + timedelta(days=1)
    while not schedule.working_day(day):
        day += timedelta(days=1)
    return day


def at(day, hour, minute=0):
    return datetime.combine(day, time(hour, minute), KST)


def find(connection, day, **extra):
    return slots.find_consult_slots(connection, seed.TEACHER, day, org_id=seed.ORG, **extra)


def add_booking(connection, teacher, room, start, end, status="confirmed"):
    rid = connection.scalar(text("""
        INSERT INTO requests (org_id,classroom_id,child_id,requester_id,client_request_id,type,body)
        VALUES (:org,:class,:child,:parent,:key,'consultation','[TEST] 충돌 일정') RETURNING id
    """), {"org": seed.ORG, "class": seed.CLASS_STAR, "child": seed.CHILD,
           "parent": seed.PARENT, "key": str(uuid4())})
    connection.execute(text("""
        INSERT INTO consultation_bookings (org_id,request_id,teacher_id,room_id,period,confirmed_by,status)
        VALUES (:org,:request,:teacher,:room,tstzrange(:start,:end,'[)'),:user,:status)
    """), {"org": seed.ORG, "request": rid, "teacher": teacher, "room": room,
           "start": start, "end": end, "user": seed.TEACHER, "status": status})


def test_candidates_respect_work_hours_busy_blocks_half_open_bounds_and_limit(seeded_db, monkeypatch):
    day = future_day()
    monkeypatch.setattr(slots, "settings", replace(slots.settings, work_hours=(time(10, 15), time(12, 15))))
    with seeded_db.begin() as connection:
        connection.execute(text("""
            INSERT INTO staff_busy_blocks (org_id,user_id,period,kind)
            VALUES (:org,:user,tstzrange(:start,:end,'[)'),'meeting')
        """), {"org": seed.ORG, "user": seed.TEACHER, "start": at(day, 10, 45), "end": at(day, 11, 15)})
        result = find(connection, day)
        assert [s["start"] for s in result] == [at(day, 10, 15), at(day, 11, 15), at(day, 11, 45)]
        assert all(s["end"]-s["start"] == timedelta(minutes=30) for s in result)
        # 다른 교사 일정은 내 후보를 막지 않아요.
        connection.execute(text("""
            INSERT INTO staff_busy_blocks (org_id,user_id,period,kind)
            VALUES (:org,:user,tstzrange(:start,:end,'[)'),'class')
        """), {"org": seed.ORG, "user": seed.TEACHER_OTHER, "start": at(day, 9), "end": at(day, 18)})
        assert find(connection, day) == result


def test_weekend_holiday_closed_day_and_inactive_resources_have_no_candidates(seeded_db, monkeypatch):
    day = future_day()
    with seeded_db.begin() as connection:
        saturday = day + timedelta(days=(5-day.weekday()) % 7)
        assert find(connection, saturday) == []
        monkeypatch.setattr(schedule, "settings", replace(schedule.settings, holidays=(day,)))
        assert find(connection, day) == []
        monkeypatch.setattr(schedule, "settings", replace(schedule.settings, holidays=()))
        connection.execute(text("UPDATE users SET is_active=false WHERE id=:id"), {"id": seed.TEACHER})
        assert find(connection, day) == []
        connection.execute(text("UPDATE users SET is_active=true WHERE id=:id"), {"id": seed.TEACHER})
        connection.execute(text("UPDATE rooms SET is_active=false WHERE org_id=:org"), {"org": seed.ORG})
        assert find(connection, day) == []


def test_room_and_teacher_bookings_filter_candidates_but_cancelled_does_not(seeded_db):
    day = future_day()
    with seeded_db.begin() as connection:
        room = connection.scalar(text("SELECT id FROM rooms WHERE org_id=:org ORDER BY id LIMIT 1"), {"org": seed.ORG})
        another = uuid4()
        connection.execute(text("INSERT INTO rooms (id,org_id,name) VALUES (:id,:org,'[TEST] 상담실 2')"),
                           {"id": another, "org": seed.ORG})
        add_booking(connection, seed.TEACHER_OTHER, room, at(day, 9), at(day, 9, 30))
        result = find(connection, day)
        assert result[0]["start"] == at(day, 9) and result[0]["room_id"] == another
        # 다른 방이어도 같은 담임은 같은 시간에 상담할 수 없어요.
        add_booking(connection, seed.TEACHER, room, at(day, 9, 30), at(day, 10))
        add_booking(connection, seed.TEACHER, room, at(day, 10), at(day, 10, 30), "cancelled")
        result = find(connection, day)
        assert [s["start"] for s in result] == [at(day, 9), at(day, 10), at(day, 10, 30)]
        assert len({s["start"] for s in result}) == 3


def test_live_parent_hold_blocks_new_candidates_and_expires_without_booking(db_client, seeded_db):
    rid, _ = create(db_client, "consultation")
    with seeded_db.begin() as connection:
        slot = connection.execute(text("""
            SELECT s.* FROM consultation_slots s JOIN cards c ON c.id=s.card_id
            WHERE c.request_id=:id ORDER BY s.rank LIMIT 1
        """), {"id": rid}).mappings().one()
        day, start = slot["period"].lower.date(), slot["period"].lower
        assert find(connection, day)[0]["start"] == start
        connection.execute(text("UPDATE consultation_slots SET status='chosen_by_parent',chosen_at=now() WHERE id=:id"),
                           {"id": slot["id"]})
        assert all(s["start"] != start for s in find(connection, day))
        connection.execute(text("UPDATE consultation_slots SET chosen_at=now()-interval '24 hours' WHERE id=:id"),
                           {"id": slot["id"]})
        assert find(connection, day)[0]["start"] == start
        assert connection.scalar(text("SELECT count(*) FROM consultation_bookings")) == 0


def test_only_active_consultation_rules_affect_proposals(db_client, seeded_db):
    with seeded_db.begin() as connection:
        rule_id = connection.scalar(text("""
            INSERT INTO memory_rules (org_id,owner_id,reason_code,rule_text,rule_json)
            VALUES (:org,:owner,'slot_unavailable','[TEST] 오후부터','{"after":"14:00"}') RETURNING id
        """), {"org": seed.ORG, "owner": seed.TEACHER})
    rid, _ = create(db_client, "consultation")
    with seeded_db.begin() as connection:
        start = connection.scalar(text("""
            SELECT min(lower(s.period)) FROM consultation_slots s JOIN cards c ON c.id=s.card_id WHERE c.request_id=:id
        """), {"id": rid})
        assert start.hour == 9
        connection.execute(text("UPDATE memory_rules SET status='active' WHERE id=:id"), {"id": rule_id})
    rid, _ = create(db_client, "consultation")
    with seeded_db.connect() as connection:
        starts = connection.scalars(text("""
            SELECT lower(s.period) FROM consultation_slots s JOIN cards c ON c.id=s.card_id WHERE c.request_id=:id
        """), {"id": rid}).all()
        assert len(starts) == 3 and all(s.hour >= 14 for s in starts)


def test_no_available_slots_stays_empty_and_none_fit_does_not_crash(db_client, seeded_db):
    with seeded_db.begin() as connection:
        connection.execute(text("UPDATE rooms SET is_active=false WHERE org_id=:org"), {"org": seed.ORG})
    rid, _ = create(db_client, "consultation")
    response = db_client.post(f"{BASE}/requests/{rid}/slot-choices", headers=auth(seed.PARENT),
                              json={"none_fit": True, "preferred_times": "[TEST] 다른 날"})
    assert response.status_code == 200 and response.json()["slots"] == []
    assert response.json()["request"]["status"] == "needs_info"


def prepare_chosen(client):
    rid, cid = create(client, "consultation")
    result = client.get(f"{BASE}/requests/{rid}", headers=auth(seed.PARENT)).json()
    slot = result["consultation"]["slots"][0]
    response = client.post(f"{BASE}/requests/{rid}/slot-choices", headers=auth(seed.PARENT),
                           json={"slot_ids": [slot["id"]]})
    assert response.status_code == 200, response.text
    return rid, cid, slot


@pytest.mark.parametrize("collision", ["room", "teacher"])
def test_distinct_requests_simultaneously_confirming_conflict_only_store_one(db_client, seeded_db, collision):
    # 두 요청 모두 같은 후보를 받은 뒤 체크하도록 먼저 만들어요.
    first_rid, first_cid = create(db_client, "consultation")
    second_rid, second_cid = create(db_client, "consultation")
    pairs = []
    for rid, cid in ((first_rid, first_cid), (second_rid, second_cid)):
        slot = db_client.get(f"{BASE}/requests/{rid}", headers=auth(seed.PARENT)).json()["consultation"]["slots"][0]
        assert db_client.post(f"{BASE}/requests/{rid}/slot-choices", headers=auth(seed.PARENT),
                              json={"slot_ids": [slot["id"]]}).status_code == 200
        pairs.append((rid, cid, slot))
    assert pairs[0][2]["period"] == pairs[1][2]["period"]
    with seeded_db.begin() as connection:
        if collision == "teacher":
            another = connection.scalar(text("INSERT INTO rooms (org_id,name) VALUES (:org,'[TEST] 방 2') RETURNING id"),
                                        {"org": seed.ORG})
            connection.execute(text("UPDATE consultation_slots SET room_id=:room WHERE id=:id"),
                               {"room": another, "id": pairs[1][2]["id"]})
        else:
            connection.execute(text("UPDATE consultation_slots SET teacher_id=:teacher WHERE id=:id"),
                               {"teacher": seed.TEACHER_OTHER, "id": pairs[1][2]["id"]})
    barrier = Barrier(2)

    def meet(connection, cursor, statement, parameters, context, executemany):
        if "INSERT INTO consultation_bookings" in statement:
            barrier.wait(timeout=10)

    headers = auth(seed.TEACHER)

    def confirm(pair):
        _, cid, slot = pair
        return db_client.post(f"{BASE}/cards/{cid}/bookings", headers=headers,
                              json={"version": 1, "slot_id": slot["id"]})

    event.listen(seeded_db, "before_cursor_execute", meet)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(confirm, pairs))
    finally:
        event.remove(seeded_db, "before_cursor_execute", meet)
    assert sorted(r.status_code for r in responses) == [200, 409], [r.text for r in responses]
    loser = next(pair for pair, response in zip(pairs, responses) if response.status_code == 409)
    failure = next(r for r in responses if r.status_code == 409)
    assert failure.json()["error"]["code"] == "SLOT_TAKEN"
    with seeded_db.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM consultation_bookings")) == 1
        assert connection.scalar(text("SELECT count(*) FROM approvals")) == 1
        assert connection.scalar(text("SELECT count(*) FROM events WHERE action='booked'")) == 1
        assert connection.scalar(text("SELECT status FROM requests WHERE id=:id"), {"id": loser[0]}) == "awaiting_review"
        assert connection.execute(text("SELECT status,version FROM cards WHERE id=:id"), {"id": loser[1]}).one() == ("pending", 1)
        assert connection.scalar(text("SELECT status FROM consultation_slots WHERE id=:id"), {"id": loser[2]["id"]}) == "chosen_by_parent"
        notifications = connection.execute(text("""
            SELECT recipient_id,kind,status,dedupe_key,deliver_after,created_at FROM notifications WHERE kind='sent_or_booked'
        """)).mappings().all()
        assert len(notifications) == 1
        notice = notifications[0]
        assert notice["recipient_id"] == seed.PARENT and notice["status"] == "pending"
        assert notice["dedupe_key"] and notice["deliver_after"] == notice["created_at"]


def test_notification_failure_rolls_back_booking_approval_and_slot_state(db_client, seeded_db, monkeypatch):
    from app.modules.requests import events

    rid, cid, slot = prepare_chosen(db_client)

    def failed(*args):
        raise RuntimeError("[TEST] 상담 알림 저장 실패")

    monkeypatch.setattr(events, "notify_event", failed)
    response = db_client.post(f"{BASE}/cards/{cid}/bookings", headers=auth(seed.TEACHER),
                              json={"version": 1, "slot_id": slot["id"]})
    assert response.status_code == 500 and response.json()["error"]["code"] == "INTERNAL_ERROR"
    with seeded_db.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM consultation_bookings")) == 0
        assert connection.scalar(text("SELECT count(*) FROM approvals")) == 0
        assert connection.scalar(text("SELECT count(*) FROM events WHERE action IN ('approved','booked')")) == 0
        assert connection.scalar(text("SELECT status FROM requests WHERE id=:id"), {"id": rid}) == "awaiting_review"
        assert connection.scalar(text("SELECT status FROM consultation_slots WHERE id=:id"), {"id": slot["id"]}) == "chosen_by_parent"
        assert connection.execute(text("SELECT status,version FROM cards WHERE id=:id"), {"id": cid}).one() == ("pending", 1)
