"""[제안][선택] T56: 실제 WebSocket과 mock·전용 DB 예약을 함께 검사해요."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import jwt
import pytest
from sqlalchemy import text
from starlette.websockets import WebSocketDisconnect

from app import backend
from app.core import config, video_consult as rules
from app.core.auth import CurrentUser
from app.mock import seed, store, video_consult

BASE = f"/api/v1/consultations/{seed.VIDEO_BOOKING}"


@pytest.fixture(autouse=True, params=["mock", "db"])
def video_backend(request, monkeypatch, _reset_store):
    enabled = replace(config.settings, feature_video_consult=True)
    monkeypatch.setattr(config, "settings", enabled)
    monkeypatch.setattr(rules, "settings", enabled)
    monkeypatch.setattr(rules, "now", lambda: seed.video_period()["start"])
    if request.param == "db":
        engine = request.getfixturevalue("seeded_db")
        from app.core import users
        from app.modules.consultations import video as module
    else:
        engine, users, module = None, store, video_consult
        store.reset()
    monkeypatch.setattr(backend, "users", users)
    monkeypatch.setattr(backend, "video_consult", module)
    return SimpleNamespace(engine=engine)


def events(ctx, action):
    if ctx.engine is None:
        return [e.__dict__ for e in store.state().events if e.action == action]
    with ctx.engine.connect() as c:
        return list(c.execute(text("SELECT * FROM events WHERE action=:action ORDER BY id"), {"action": action}).mappings())


def change(ctx, **values):
    if ctx.engine is None:
        for key, value in values.items():
            setattr(store.state().bookings[seed.VIDEO_BOOKING], key, value)
    else:
        with ctx.engine.begin() as c:
            for key, value in values.items():
                assert key in ("status", "expected_end_at")
                c.execute(text(f"UPDATE consultation_bookings SET {key}=:value WHERE id=:id"),
                          {"value": value, "id": seed.VIDEO_BOOKING})


def room(client, actor):
    response = client.get(BASE + "/room", headers=actor)
    assert response.status_code == 200, response.text
    return response.json()


def connect(client, result, **kwargs):
    return client.websocket_connect(result["signal_path"], params={"ticket": result["ticket"]}, **kwargs)


def rejected(client, result):
    with pytest.raises(WebSocketDisconnect) as exc, connect(client, result) as ws:
        ws.receive_json()
    assert exc.value.code == 1008 and exc.value.reason == "access_denied"


def test_participants_exchange_signals_and_record_no_payload(video_backend, client, teacher, parent):
    with client:
        t, p = room(client, teacher), room(client, parent)
        claims = jwt.decode(t["ticket"], rules.settings.jwt_secret, algorithms=["HS256"], audience="consult-signal")
        assert claims["exp"] - claims["iat"] == 60
        assert set(t) == {"booking_id", "opens_at", "closes_at", "ice_servers", "signal_path", "ticket", "ticket_expires_at"}
        with connect(client, t) as a:
            with connect(client, p) as b:
                assert a.receive_json() == b.receive_json() == {"type": "peer_joined"}
                for sender, receiver, kind in ((a, b, "offer"), (b, a, "answer"), (a, b, "ice")):
                    msg = {"type": kind, "data": {"synthetic": "[TEST] 신호"}}
                    sender.send_json(msg)
                    assert receiver.receive_json() == msg
                b.send_json({"type": "bye", "data": None})
                assert a.receive_json() == {"type": "bye", "data": None}
                assert a.receive_json() == {"type": "peer_left"}
                assert b.receive()["code"] == 1000
        assert len(events(video_backend, "video_joined")) == len(events(video_backend, "video_left")) == 2
        for action in ("video_joined", "video_left"):
            assert all(e["request_id"] == seed.VIDEO_REQUEST and "synthetic" not in str(e["detail"])
                       for e in events(video_backend, action))


@pytest.mark.parametrize("actor", ["director", "parent_other", "teacher_other"])
def test_nonparticipant_forbidden_and_audited(video_backend, client, request, actor):
    response = client.get(BASE + "/room", headers=request.getfixturevalue(actor))
    assert response.status_code == 403 and response.json()["error"]["code"] == "FORBIDDEN"
    assert events(video_backend, "permission_denied")[-1]["request_id"] == seed.VIDEO_REQUEST


def test_other_org_and_missing_booking_are_404(video_backend, client, teacher):
    outsider = CurrentUser(id=seed.TEACHER, org_id=uuid4(), role="teacher")
    from app.core.errors import ApiError
    with pytest.raises(ApiError) as exc:
        backend.video_consult.access(outsider, seed.VIDEO_BOOKING)
    assert exc.value.status == 404 and not events(video_backend, "permission_denied")
    assert client.get(f"/api/v1/consultations/{uuid4()}/room", headers=teacher).status_code == 404
    from app.core.auth import current_user
    from app.main import app
    app.dependency_overrides[current_user] = lambda: outsider
    try:
        assert client.get(BASE + "/room", headers=teacher).status_code == 404
    finally:
        del app.dependency_overrides[current_user]


@pytest.mark.parametrize("minutes,status,reason", [(-11, 409, "room_not_open"), (-10, 200, None),
                                                   (65, 200, None), (66, 409, "room_closed")])
def test_opening_boundaries(client, teacher, monkeypatch, minutes, status, reason):
    monkeypatch.setattr(rules, "now", lambda: seed.video_period()["start"] + timedelta(minutes=minutes))
    response = client.get(BASE + "/room", headers=teacher)
    assert response.status_code == status, response.text
    if reason:
        error = response.json()["error"]
        assert error["code"] == "CONFLICT" and error["details"]["reason"] == reason
        assert {"opens_at", "closes_at"} <= error["details"].keys()


def test_expected_end_extends_room(video_backend, client, teacher, monkeypatch):
    change(video_backend, expected_end_at=seed.video_period()["end"] + timedelta(minutes=40))
    monkeypatch.setattr(rules, "now", lambda: seed.video_period()["start"] + timedelta(minutes=90))
    assert datetime.fromisoformat(room(client, teacher)["closes_at"]) == seed.video_period()["end"] + timedelta(minutes=70)


def test_cancelled_booking_conflict_and_connect_recheck(video_backend, client, teacher):
    t = room(client, teacher)
    change(video_backend, status="cancelled")
    response = client.get(BASE + "/room", headers=teacher)
    assert response.status_code == 409 and response.json()["error"]["code"] == "CONFLICT"
    rejected(client, t)


@pytest.mark.parametrize("invalid", ["expired", "booking", "role", "aud", "version", "malformed"])
def test_invalid_tickets_rejected(client, teacher, invalid):
    t = room(client, teacher)
    claims = jwt.decode(t["ticket"], rules.settings.jwt_secret, algorithms=["HS256"], audience="consult-signal")
    if invalid == "expired":
        claims["exp"] = int(datetime.now(timezone.utc).timestamp()) - 1
    elif invalid == "booking":
        claims["booking"] = str(uuid4())
    elif invalid == "role":
        claims["role"] = "director"
    elif invalid == "aud":
        claims["aud"] = "other"
    elif invalid == "version":
        claims["ver"] += 1
    t["ticket"] = "bad" if invalid == "malformed" else jwt.encode(claims, rules.settings.jwt_secret, algorithm="HS256")
    rejected(client, t)


def test_connect_rechecks_time_and_participant(video_backend, client, teacher, monkeypatch):
    t = room(client, teacher)
    monkeypatch.setattr(rules, "now", lambda: seed.video_period()["end"] + timedelta(hours=1))
    rejected(client, t)
    monkeypatch.setattr(rules, "now", lambda: seed.video_period()["start"])
    t = room(client, teacher)
    if video_backend.engine:
        with video_backend.engine.begin() as c:
            c.execute(text("UPDATE consultation_bookings SET teacher_id=:teacher WHERE id=:id"),
                      {"teacher": seed.TEACHER_OTHER, "id": seed.VIDEO_BOOKING})
    else:
        store.state().bookings[seed.VIDEO_BOOKING].teacher_id = seed.TEACHER_OTHER
    rejected(client, t)
    assert events(video_backend, "permission_denied")


@pytest.mark.parametrize("raw", ['{"type":"offer","data":"' + "가" * 22000 + '"}',
                                '{"type":"secret","data":null}', '{"type":"offer"}', '[]', '{'])
def test_bad_or_oversize_signal_closed(client, teacher, raw):
    with connect(client, room(client, teacher)) as ws:
        ws.send_text(raw)
        assert ws.receive()["code"] == 1008


def test_rate_limit(client, teacher):
    with connect(client, room(client, teacher)) as ws:
        for _ in range(21):
            ws.send_json({"type": "ice", "data": None})
        assert ws.receive()["code"] == 1008


def test_reconnect_replaces_old_and_peer_stays(client, teacher, parent):
    with client, connect(client, room(client, parent)) as p:
        with connect(client, room(client, teacher)) as old:
            assert p.receive_json() == old.receive_json() == {"type": "peer_joined"}
            with connect(client, room(client, teacher)) as new:
                assert old.receive()["code"] == 1008
                assert p.receive_json() == new.receive_json() == {"type": "peer_joined"}
                new.send_json({"type": "offer", "data": "[TEST] replacement"})
                assert p.receive_json()["data"] == "[TEST] replacement"
            assert p.receive_json() == {"type": "peer_left"}


def test_disabled_routes_return_common_404(client, teacher, monkeypatch):
    monkeypatch.setattr(rules, "settings", replace(rules.settings, feature_video_consult=False))
    for headers in (teacher, {}):
        response = client.get(BASE + "/room", headers=headers)
        assert response.status_code == 404 and response.json()["error"]["code"] == "NOT_FOUND"
    from starlette.testclient import WebSocketDenialResponse
    with pytest.raises(WebSocketDenialResponse) as exc, client.websocket_connect(BASE + "/signal"):
        pass
    assert exc.value.status_code == 404 and exc.value.json()["error"]["code"] == "NOT_FOUND"


def test_ice_configuration_and_seed_idempotency(video_backend, client, teacher, monkeypatch):
    ice = [{"urls": ["turn:example.invalid"], "username": "[TEST] user", "credential": "[TEST] credential"}]
    monkeypatch.setenv("VIDEO_ICE_SERVERS", __import__("json").dumps(ice))
    monkeypatch.setattr(rules, "settings", replace(rules.settings, video_ice_servers=config.load_settings().video_ice_servers))
    assert room(client, teacher)["ice_servers"] == ice
    if video_backend.engine:
        from db.seeds.demo import seed_video_consult
        with video_backend.engine.begin() as c:
            seed_video_consult(c)
            assert c.scalar(text("SELECT count(*) FROM consultation_bookings")) == 1
    else:
        assert list(store.state().bookings) == [seed.VIDEO_BOOKING]


@pytest.mark.parametrize("invalid", ["clock", "cancelled", "inactive", "version", "teacher"])
def test_connected_access_rechecked(video_backend, client, teacher, parent, monkeypatch, invalid):
    from app.api.routes import video_consult as route
    clock = [100.0]
    monkeypatch.setattr(route, "monotonic", lambda: clock[0])
    with client, connect(client, room(client, parent)) as p, connect(client, room(client, teacher)) as t:
        assert p.receive_json() == t.receive_json() == {"type": "peer_joined"}
        if invalid == "clock":
            monkeypatch.setattr(rules, "now", lambda: seed.video_period()["end"] + timedelta(hours=1))
        elif video_backend.engine:
            sql, values = {
                "cancelled": ("UPDATE consultation_bookings SET status='cancelled' WHERE id=:id", {"id": seed.VIDEO_BOOKING}),
                "teacher": ("UPDATE consultation_bookings SET teacher_id=:other WHERE id=:id",
                            {"id": seed.VIDEO_BOOKING, "other": seed.TEACHER_OTHER}),
                "inactive": ("UPDATE users SET is_active=false WHERE id=:id", {"id": seed.TEACHER}),
                "version": ("UPDATE users SET token_version=token_version+1 WHERE id=:id", {"id": seed.TEACHER}),
            }[invalid]
            with video_backend.engine.begin() as c:
                c.execute(text(sql), values)
        elif invalid == "cancelled":
            store.state().bookings[seed.VIDEO_BOOKING].status = "cancelled"
        elif invalid == "teacher":
            store.state().bookings[seed.VIDEO_BOOKING].teacher_id = seed.TEACHER_OTHER
        elif invalid == "inactive":
            store.state().users[seed.TEACHER].is_active = False
        else:
            store.state().users[seed.TEACHER].token_version += 1
        clock[0] += 11
        t.send_json({"type": "offer", "data": "[TEST] revoked"})
        frame = t.receive()
        assert frame["code"] == 1008
        assert frame["reason"] == ("room_closed" if invalid == "clock" else "access_denied")
        assert p.receive_json() == {"type": "peer_left"}
    assert len(events(video_backend, "video_left")) == 2


def test_quiet_connection_closes_at_deadline(client, teacher, monkeypatch):
    deadline = seed.video_period()["end"] + timedelta(minutes=30)
    monkeypatch.setattr(rules, "now", lambda: deadline - timedelta(seconds=0.2))
    with connect(client, room(client, teacher)) as ws:
        frame = ws.receive()
        assert frame["code"] == 1008 and frame["reason"] == "room_closed"


def test_binary_frame_has_invalid_signal_reason(client, teacher):
    with connect(client, room(client, teacher)) as ws:
        ws.send_bytes(b"[TEST] binary")
        frame = ws.receive()
        assert frame["code"] == 1008 and frame["reason"] == "invalid_signal"


def test_ticket_single_use_and_expired_entries_pruned(client, teacher):
    import time
    rules._used_tickets["[TEST] expired"] = time.time() - 1
    t = room(client, teacher)
    with connect(client, t) as original:
        rejected(client, t)
        original.send_json({"type": "bye", "data": None})
        assert original.receive()["code"] == 1000
    assert "[TEST] expired" not in rules._used_tickets
    rejected(client, t)


@pytest.mark.parametrize("conflict", [None, "teacher", "room"])
def test_expired_demo_refresh_and_resource_conflicts(video_backend, monkeypatch, caplog, conflict):
    from app.mock import seeding
    from db.seeds.demo import seed_video_consult
    target = seed.video_period()
    old = {key: value - timedelta(days=2) for key, value in target.items()}
    other = seed.demo_id("902")
    other_room = seed.demo_id("602")
    teacher_id = seed.TEACHER if conflict == "teacher" else seed.TEACHER_OTHER
    room_id = seed.ROOM if conflict == "room" else other_room
    if video_backend.engine:
        with video_backend.engine.begin() as c:
            c.execute(text("UPDATE consultation_bookings SET period=tstzrange(:start,:end,'[)') WHERE id=:id"),
                      {"id": seed.VIDEO_BOOKING, **old})
            if conflict:
                c.execute(text("INSERT INTO rooms(id,org_id,name) VALUES (:id,:org,'[TEST] 방')"),
                          {"id": other_room, "org": seed.ORG})
                c.execute(text("""
                    INSERT INTO consultation_bookings(id,org_id,request_id,teacher_id,room_id,period,confirmed_by)
                    VALUES (:id,:org,:req,:teacher,:room,tstzrange(:start,:end,'[)'),:teacher)
                """), {"id": other, "org": seed.ORG, "req": seed.REQUEST_COUGH,
                       "teacher": teacher_id, "room": room_id, **target})
            seed_video_consult(c)
            seed_video_consult(c)
            period = c.scalar(text("SELECT period FROM consultation_bookings WHERE id=:id"), {"id": seed.VIDEO_BOOKING})
            result = {"start": period.lower, "end": period.upper}
            if conflict:
                assert c.scalar(text("SELECT period FROM consultation_bookings WHERE id=:id"), {"id": other}).lower == target["start"]
    else:
        from app.mock.records import Booking
        store.state().bookings[seed.VIDEO_BOOKING].period = old
        if conflict:
            store.state().bookings[other] = Booking(other, seed.ORG, seed.REQUEST_COUGH, None, teacher_id,
                                                   room_id, target, teacher_id)
        seeding.seed_video_consult()
        seeding.seed_video_consult()
        result = store.state().bookings[seed.VIDEO_BOOKING].period
        if conflict:
            assert store.state().bookings[other].period == target
    assert result == (old if conflict else target)
    assert bool("갱신 생략" in caplog.text) == bool(conflict)


def test_disabled_ice_config_warns_and_enabled_config_rejects(monkeypatch, caplog):
    monkeypatch.setenv("VIDEO_ICE_SERVERS", '[{"urls":')
    monkeypatch.setenv("FEATURE_VIDEO_CONSULT", "false")
    assert config.load_settings().video_ice_servers == [{"urls": "stun:stun.l.google.com:19302"}]
    assert "기능이 꺼져" in caplog.text
    monkeypatch.setenv("FEATURE_VIDEO_CONSULT", "true")
    with pytest.raises(ValueError):
        config.load_settings()
