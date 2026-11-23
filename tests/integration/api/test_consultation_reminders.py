"""T48 내부 입구·시간 경계·알림 읽기를 두 저장소에서 확인해요."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import text

from app import backend
from app.core.errors import ApiError
from app.core.schedule import KST
from app.mock import seed, store
from app.mock.records import Booking

NOW = datetime(2026, 11, 16, 9, 20, tzinfo=KST)
BASE = "/api/v1"


@pytest.fixture(params=["mock", "db"])
def reminders(request, monkeypatch):
    monkeypatch.setattr(store, "now", lambda: NOW)
    if request.param == "db":
        engine = request.getfixturevalue("seeded_db")
        from app.core import users
        from app.modules.consultations import reminders as module
        from app.modules.notifications import notifications
    else:
        engine = None
        from app.mock import consultation_reminders as module, notifications
        users = store
    monkeypatch.setattr(backend, "consultation_reminders", module)
    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW.astimezone(tz)
    monkeypatch.setattr(module, "datetime", FrozenDatetime)
    monkeypatch.setattr(backend, "users", users)
    monkeypatch.setattr(backend, "notifications", notifications)
    return SimpleNamespace(module=module, engine=engine)


def booking(ctx, start=NOW-timedelta(minutes=20), *, teacher=seed.TEACHER, room=None, status="confirmed"):
    bid, rid = uuid4(), uuid4()
    end = start+timedelta(minutes=30)
    if ctx.engine is None:
        state = store.state()
        room = room or next(iter(state.rooms))
        state.requests[rid] = store.Request(rid, seed.ORG, seed.CLASS_STAR, seed.CHILD, seed.PARENT,
                                           str(rid), "consultation", "[TEST] 상담", status="sent_or_booked")
        state.bookings[bid] = Booking(bid, seed.ORG, rid, None, teacher, room,
                                     {"start": start, "end": end}, seed.TEACHER, status=status)
    else:
        with ctx.engine.begin() as c:
            room = room or c.scalar(text("SELECT id FROM rooms WHERE org_id=:org LIMIT 1"), {"org": seed.ORG})
            c.execute(text("""
                INSERT INTO requests(id,org_id,classroom_id,child_id,requester_id,client_request_id,type,body,status)
                VALUES (:id,:org,:class,:child,:parent,:key,'consultation','[TEST] 상담','sent_or_booked')
            """), {"id": rid, "org": seed.ORG, "class": seed.CLASS_STAR, "child": seed.CHILD,
                   "parent": seed.PARENT, "key": str(rid)})
            c.execute(text("""
                INSERT INTO consultation_bookings(id,org_id,request_id,teacher_id,room_id,period,confirmed_by,status)
                VALUES (:id,:org,:req,:teacher,:room,tstzrange(:start,:end,'[)'),:user,:status)
            """), {"id": bid, "org": seed.ORG, "req": rid, "teacher": teacher, "room": room,
                   "start": start, "end": end, "user": seed.TEACHER, "status": status})
    return bid, rid


def user(uid=seed.TEACHER, role="teacher"):
    return SimpleNamespace(id=uid, org_id=seed.ORG, role=role)


def notices(ctx):
    if ctx.engine is None:
        return [n.__dict__ for n in store.state().notifications.values() if n.kind.startswith("consultation_")]
    with ctx.engine.connect() as c:
        return [dict(n) for n in c.execute(text("SELECT * FROM notifications WHERE kind LIKE 'consultation_%'" )).mappings()]


def test_ending_window_boundary_late_tick_and_repeat(reminders):
    booking(reminders)
    sweep = reminders.module.sweep_consultation_notifications
    assert sweep(NOW-timedelta(microseconds=1)) == 0
    assert sweep(NOW) == 1
    assert sweep(NOW+timedelta(minutes=9)) == 0
    assert sweep(NOW+timedelta(minutes=10)) == 0
    rows = notices(reminders)
    assert len(rows) == 1 and rows[0]["recipient_id"] == seed.TEACHER
    assert rows[0]["kind"] == "consultation_ending" and "09:30" in rows[0]["body"]


def test_delayed_tick_inside_window_but_no_catchup_after_end(reminders):
    booking(reminders)
    assert reminders.module.sweep_consultation_notifications(NOW+timedelta(minutes=3)) == 1


@pytest.mark.parametrize("status", ["confirmed", "done", "cancelled"])
def test_elapsed_booking_without_explicit_delay_never_warns_next_parent(reminders, status):
    booking(reminders, status=status)
    booking(reminders, NOW+timedelta(minutes=10))
    reminders.module.sweep_consultation_notifications(NOW+timedelta(minutes=15))
    assert not any(n["kind"] == "consultation_delayed" for n in notices(reminders))


def test_recorded_delay_notifies_teacher_parent_once_and_is_readable_with_scope(
    reminders, client, parent, parent_other, teacher
):
    first, _ = booking(reminders)
    _, target = booking(reminders, NOW+timedelta(minutes=10))
    until = NOW+timedelta(minutes=35)
    reminders.module.report_delay(user(), first, until, now=NOW)
    reminders.module.report_delay(user(), first, until, now=NOW)
    assert reminders.module.sweep_consultation_notifications(NOW) == 2
    assert reminders.module.sweep_consultation_notifications(NOW+timedelta(seconds=30)) == 0
    rows = notices(reminders)
    assert {n["recipient_id"] for n in rows} == {seed.TEACHER, seed.PARENT}
    assert all(n["request_id"] == target and n["kind"] == "consultation_delayed" for n in rows)
    assert all("대체 시간 제안:" in n["body"] and "확정된 시간이 아니에요" in n["body"] for n in rows)
    for auth, expected in ((parent, 1), (teacher, 1), (parent_other, 0)):
        response = client.get(BASE+"/notifications", headers=auth)
        assert response.status_code == 200, response.text
        received = [n for n in response.json()["items"] if n["kind"] == "consultation_delayed"]
        assert len(received) == expected
        if received:
            nid = received[0]["id"]
            assert client.post(f"{BASE}/notifications/{nid}/read", headers=auth).status_code == 200
    mine = next(n for n in rows if n["recipient_id"] == seed.PARENT)
    assert client.post(f"{BASE}/notifications/{mine['id']}/read", headers=parent_other).status_code == 404
    if reminders.engine:
        with reminders.engine.connect() as c:
            assert c.scalar(text("SELECT count(*) FROM events WHERE action='consultation_delay_reported'")) == 1
            assert c.scalar(text("SELECT count(*) FROM consultation_bookings")) == 2
            assert c.scalar(text("SELECT status FROM requests WHERE id=:id"), {"id": target}) == "sent_or_booked"
    else:
        assert sum(e.action == "consultation_delay_reported" for e in store.state().events) == 1
        assert len(store.state().bookings) == 2 and store.state().requests[target].status == "sent_or_booked"


@pytest.mark.parametrize("role,uid,code", [("parent", seed.PARENT, "FORBIDDEN_ROLE"),
                                         ("director", seed.DIRECTOR, "FORBIDDEN_ROLE"),
                                         ("teacher", seed.TEACHER_OTHER, "NOT_FOUND")])
def test_only_booking_teacher_can_report_delay(reminders, role, uid, code):
    bid, _ = booking(reminders)
    with pytest.raises(ApiError) as error:
        reminders.module.report_delay(user(uid, role), bid, NOW+timedelta(hours=1), now=NOW)
    assert error.value.code == code


@pytest.mark.parametrize("until", [NOW, NOW+timedelta(minutes=10), NOW.replace(tzinfo=None)])
def test_invalid_delay_is_rejected_without_notifications(reminders, until):
    bid, _ = booking(reminders)
    with pytest.raises(ApiError) as error:
        reminders.module.report_delay(user(), bid, until, now=NOW)
    assert error.value.code == "VALIDATION_FAILED" and notices(reminders) == []


def test_delay_uses_revised_end_for_reminder_and_no_free_slot_fallback(reminders, monkeypatch):
    first, _ = booking(reminders)
    booking(reminders, NOW+timedelta(minutes=10))
    reminders.module.report_delay(user(), first, (NOW+timedelta(minutes=40)).astimezone(timezone.utc), now=NOW)
    monkeypatch.setattr(reminders.module, "alternatives", lambda *args: [])
    assert reminders.module.sweep_consultation_notifications(NOW) == 2
    assert all("가능한 대체 시간이 없어" in n["body"] for n in notices(reminders))
    reminders.module.sweep_consultation_notifications(NOW+timedelta(minutes=30))
    assert any(n["kind"] == "consultation_ending" and "10:00" in n["body"] for n in notices(reminders))


@pytest.mark.parametrize("status", ["done", "cancelled"])
def test_finished_or_cancelled_booking_never_gets_ending_reminder(reminders, status):
    booking(reminders, status=status)
    assert reminders.module.sweep_consultation_notifications(NOW) == 0


def test_ending_outside_work_hours_is_immediate(reminders):
    booking(reminders, NOW.replace(hour=19, minute=0))
    assert reminders.module.sweep_consultation_notifications(NOW.replace(hour=19, minute=20)) == 1


def test_no_new_ending_alert_is_created_after_window(reminders):
    booking(reminders)
    assert reminders.module.sweep_consultation_notifications(NOW+timedelta(minutes=10)) == 0


@pytest.mark.parametrize("until", [NOW+timedelta(days=2), NOW+timedelta(hours=3, minutes=10, microseconds=1)])
def test_delay_upper_bound_is_rejected_without_effect(reminders, until):
    bid, _ = booking(reminders)
    with pytest.raises(ApiError) as error:
        reminders.module.report_delay(user(), bid, until, now=NOW)
    assert error.value.code == "VALIDATION_FAILED"
    assert not notices(reminders)


def test_delay_accepts_exact_three_hour_limit_and_rejects_next_kst_day(reminders):
    bid, _ = booking(reminders)
    reminders.module.report_delay(user(), bid, NOW+timedelta(hours=3, minutes=10), now=NOW)
    late, _ = booking(reminders, NOW.replace(hour=23, minute=0))
    with pytest.raises(ApiError) as error:
        reminders.module.report_delay(user(), late, NOW.replace(hour=23, minute=40)+timedelta(minutes=30),
                                      now=NOW.replace(hour=23, minute=20))
    assert error.value.code == "VALIDATION_FAILED"


def test_end_reminder_after_delay_change_supersedes_previous_pending(reminders):
    bid, _ = booking(reminders)
    sweep = reminders.module.sweep_consultation_notifications
    assert sweep(NOW) == 1
    reminders.module.report_delay(user(), bid, NOW+timedelta(minutes=30), now=NOW+timedelta(minutes=5))
    assert notices(reminders)[0]["status"] == "held"
    assert sweep(NOW+timedelta(minutes=20)) == 1
    assert sweep(NOW+timedelta(minutes=21)) == 0
    rows = notices(reminders)
    assert len({n["dedupe_key"] for n in rows}) == 2
    assert "09:50" in rows[1]["body"] and rows[1]["status"] == "pending"


@pytest.mark.parametrize("old_status", ["pending", "sent"])
def test_extended_delay_replaces_old_alternatives_once(reminders, old_status):
    # 두 대역 모두 처음 제안한 15시를 다음 지연이 덮도록 해요.
    first, _ = booking(reminders, NOW.replace(hour=14, minute=0))
    _, target = booking(reminders, NOW.replace(hour=14, minute=30))
    now = NOW.replace(hour=14, minute=20)
    sweep = reminders.module.sweep_consultation_notifications
    reminders.module.report_delay(user(), first, now.replace(hour=14, minute=50), now=now)
    assert sweep(now) == 2
    if reminders.engine:
        with reminders.engine.begin() as c:
            c.execute(text("UPDATE notifications SET status=:status,sent_at=CASE WHEN :status='sent' THEN :now END "
                           "WHERE kind='consultation_delayed'"), {"status": old_status, "now": now})
    else:
        for n in store.state().notifications.values():
            if n.kind == "consultation_delayed":
                n.status = old_status
    reminders.module.report_delay(user(), first, now.replace(hour=15, minute=20), now=now+timedelta(minutes=2))
    assert sweep(now+timedelta(minutes=2)) == 2
    assert sweep(now+timedelta(minutes=3)) == 0
    rows = [n for n in notices(reminders) if n["request_id"] == target]
    assert len(rows) == 4
    assert all("11/16 15:00~15:30" in n["body"] for n in rows[:2])
    assert all("11/16 15:00~15:30" not in n["body"] for n in rows[2:])
    assert all(n["status"] == ("held" if old_status == "pending" else "sent") for n in rows[:2])
    if reminders.engine:
        with reminders.engine.connect() as c:
            assert c.scalar(text("SELECT count(*) FROM events WHERE detail->>'outcome'='superseded'")) == 2
    else:
        assert sum(e.detail.get("outcome") == "superseded" for e in store.state().events) == 2


@pytest.mark.parametrize("old_status", ["pending", "sent"])
def test_unchanged_delay_ending_does_not_supersede_alternatives(reminders, old_status):
    first, _ = booking(reminders)
    booking(reminders, NOW+timedelta(minutes=10))
    until = NOW+timedelta(minutes=35)
    reminders.module.report_delay(user(), first, until, now=NOW)
    assert reminders.module.sweep_consultation_notifications(NOW) == 2
    if reminders.engine:
        with reminders.engine.begin() as c:
            c.execute(text("UPDATE notifications SET status=:status,sent_at=CASE WHEN :status='sent' THEN :now END "
                           "WHERE kind='consultation_delayed'"), {"status": old_status, "now": NOW})
    else:
        for n in store.state().notifications.values():
            if n.kind == "consultation_delayed":
                n.status = old_status
    for minutes in (1, 2):
        reminders.module.sweep_consultation_notifications(until+timedelta(minutes=minutes))
    rows = [n for n in notices(reminders) if n["kind"] == "consultation_delayed"]
    assert len(rows) == 2 and all(n["status"] == old_status for n in rows)
    if reminders.engine:
        with reminders.engine.connect() as c:
            assert c.scalar(text("SELECT count(*) FROM events WHERE detail->>'outcome'='superseded'")) == 0
    else:
        assert not any(e.detail.get("outcome") == "superseded" for e in store.state().events)


def test_http_delay_generates_alternatives_and_notifications(reminders, client, teacher, parent):
    bid, _ = booking(reminders)
    _, target = booking(reminders, NOW+timedelta(minutes=10))
    data = {"expected_end_at": (NOW+timedelta(minutes=35)).astimezone(timezone.utc).isoformat()}
    response = client.post(f"{BASE}/consultations/{bid}/delay", headers=teacher, json=data)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["affected_bookings"] == 1 and result["booking"]["id"] == str(bid)
    assert result["booking"]["expected_end_at"].endswith("+09:00")
    response = client.get(BASE+"/notifications", headers=parent)
    rows = [n for n in response.json()["items"] if n["kind"] == "consultation_delayed"]
    assert len(rows) == 1 and rows[0]["request_id"] == str(target) and "대체 시간 제안:" in rows[0]["body"]
    assert client.post(f"{BASE}/consultations/{bid}/delay", headers=teacher, json=data).json() == result
    assert len(notices(reminders)) == 2


def test_http_delay_sweeps_only_booking_teacher_and_kst_day(reminders, client, teacher, monkeypatch):
    first, _ = booking(reminders)
    target, _ = booking(reminders, NOW+timedelta(minutes=10))
    tomorrow, _ = booking(reminders, NOW+timedelta(hours=23))
    other_room = uuid4()
    if reminders.engine:
        with reminders.engine.begin() as c:
            c.execute(text("INSERT INTO rooms(id,org_id,name) VALUES (:id,:org,'[TEST] 다른 상담실')"),
                      {"id": other_room, "org": seed.ORG})
    else:
        store.state().rooms[other_room] = store.Room(other_room, seed.ORG, "[TEST] 다른 상담실")
    other, other_request = booking(reminders, teacher=seed.TEACHER_OTHER, room=other_room)
    seen = []
    actual_alerts = reminders.module.alerts
    def inspect_rows(rows, now):
        seen.append({row["id"] for row in rows})
        return actual_alerts(rows, now)
    monkeypatch.setattr(reminders.module, "alerts", inspect_rows)
    response = client.post(f"{BASE}/consultations/{first}/delay", headers=teacher,
                           json={"expected_end_at": (NOW+timedelta(minutes=35)).isoformat()})
    assert response.status_code == 200, response.text
    assert seen == [{first, target}]
    assert tomorrow not in seen[0] and other not in seen[0]
    assert len(notices(reminders)) == 2
    assert not any(n["request_id"] == other_request for n in notices(reminders))
    # 인자 없는 Beat 점검은 다른 담임까지 계속 처리해요.
    assert reminders.module.sweep_consultation_notifications(NOW) == 1
    assert any(n["request_id"] == other_request and n["recipient_id"] == seed.TEACHER_OTHER
               for n in notices(reminders))


def test_http_same_class_other_teacher_cannot_report_delay(reminders, client, teacher_other):
    bid, _ = booking(reminders)
    if reminders.engine:
        with reminders.engine.begin() as c:
            c.execute(text("INSERT INTO classroom_staff(org_id,classroom_id,user_id) VALUES (:org,:class,:user)"),
                      {"org": seed.ORG, "class": seed.CLASS_STAR, "user": seed.TEACHER_OTHER})
    else:
        store.state().classroom_staff.append(store.ClassroomStaff(seed.CLASS_STAR, seed.TEACHER_OTHER))
    response = client.post(f"{BASE}/consultations/{bid}/delay", headers=teacher_other,
                           json={"expected_end_at": (NOW+timedelta(minutes=35)).isoformat()})
    assert response.status_code == 403 and response.json()["error"]["code"] == "FORBIDDEN_ROLE"
    assert not notices(reminders)
    if reminders.engine:
        with reminders.engine.connect() as c:
            assert c.scalar(text("SELECT expected_end_at FROM consultation_bookings WHERE id=:id"), {"id": bid}) is None
    else:
        assert store.state().bookings[bid].expected_end_at is None


@pytest.mark.parametrize("actor,expected", [("parent", 403), ("director", 403), ("teacher_other", 404)])
def test_http_delay_enforces_booking_teacher(reminders, client, request, actor, expected):
    bid, _ = booking(reminders)
    auth = request.getfixturevalue(actor)
    response = client.post(f"{BASE}/consultations/{bid}/delay", headers=auth,
                           json={"expected_end_at": (NOW+timedelta(hours=1)).isoformat()})
    assert response.status_code == expected, response.text
    assert not notices(reminders)


@pytest.mark.parametrize("value", ["2026-11-16T09:55:00", "2026-11-18T09:55:00+09:00", "not a date"])
def test_http_invalid_delay_has_common_error(reminders, client, teacher, value):
    bid, _ = booking(reminders)
    response = client.post(f"{BASE}/consultations/{bid}/delay", headers=teacher, json={"expected_end_at": value})
    assert response.status_code == 422 and response.json()["error"]["code"] == "VALIDATION_FAILED"
    assert not notices(reminders)



def test_expired_teacher_assignment_cannot_use_old_card_to_report_delay(reminders):
    bid, rid = booking(reminders)
    if reminders.engine:
        with reminders.engine.begin() as c:
            c.execute(text("INSERT INTO cards(org_id,request_id,kind,assignee_id) "
                           "VALUES (:org,:req,'consult_slots',:teacher)"),
                      {"org": seed.ORG, "req": rid, "teacher": seed.TEACHER})
            c.execute(text("UPDATE classroom_staff SET valid_to='2020-01-01' WHERE user_id=:user"),
                      {"user": seed.TEACHER})
    else:
        store._new_card(store.state().requests[rid], "consult_slots", seed.TEACHER)
        for assignment in store.state().classroom_staff:
            if assignment.user_id == seed.TEACHER:
                assignment.valid_to = NOW.date()-timedelta(days=1)
    with pytest.raises(ApiError) as error:
        reminders.module.report_delay(user(), bid, NOW+timedelta(hours=1), now=NOW)
    assert error.value.code == "NOT_FOUND"
    assert not notices(reminders)
