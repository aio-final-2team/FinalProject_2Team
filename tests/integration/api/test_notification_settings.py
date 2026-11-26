"""[TEST] 본인 설정·역할·시각 계약을 mock과 시험 DB에서 확인해요."""

from datetime import datetime, timezone

import pytest

from app import backend
from app.core.schedule import deliver_after
from app.mock import seed, store
from tests.integration.api.helpers import BASE, err

PATH = BASE + "/me/notification-settings"
EMPTY = {"quiet_start": None, "quiet_end": None}
NIGHT = {"quiet_start": "22:00", "quiet_end": "07:00"}


@pytest.fixture(autouse=True, params=["mock", "db"])
def settings_backend(request, monkeypatch, _reset_store):
    if request.param == "db":
        request.getfixturevalue("seeded_db")
        from app.core import users
        from app.modules.notifications import settings
    else:
        from app.mock import notification_settings as settings
        users = store
    monkeypatch.setattr(backend, "users", users)
    monkeypatch.setattr(backend, "notification_settings", settings)


def test_own_settings_round_trip_reset_and_isolation(client, teacher, teacher_other, director):
    assert client.get(PATH, headers=teacher).json() == EMPTY
    assert client.patch(PATH, headers=teacher, json=NIGHT).json() == NIGHT
    assert client.get(PATH, headers=teacher).json() == NIGHT
    assert client.get(PATH, headers=teacher_other).json() == EMPTY
    assert client.patch(PATH, headers=director, json=NIGHT).json() == NIGHT
    assert client.patch(PATH, headers=teacher, json=EMPTY).json() == EMPTY
    assert client.get(PATH, headers=teacher).json() == EMPTY
    assert client.get(PATH, headers=director).json() == NIGHT


def test_invalid_settings_do_not_replace_saved_pair(client, teacher):
    client.patch(PATH, headers=teacher, json=NIGHT)
    for body in ({}, {"quiet_start": "22:00"}, {**NIGHT, "quiet_start": None},
                 {**NIGHT, "quiet_end": None}, {**NIGHT, "quiet_end": "22:00"},
                 {**NIGHT, "quiet_start": "24:00"}, {**NIGHT, "quiet_start": "9:00"},
                 {**NIGHT, "quiet_start": "22:00:00"}, {**NIGHT, "user_id": str(seed.DIRECTOR)}):
        err(client.patch(PATH, headers=teacher, json=body), 422, "VALIDATION_FAILED")
        assert client.get(PATH, headers=teacher).json() == NIGHT


def test_login_and_staff_role_required(client, parent):
    for method in (client.get, client.patch):
        body = {"json": NIGHT} if method == client.patch else {}
        err(method(PATH, **body), 401, "UNAUTHENTICATED")
        err(method(PATH, headers=parent, **body), 403, "FORBIDDEN_ROLE")


def test_kst_boundaries_daytime_and_immediate_exceptions(client, teacher):
    def at(value):
        return datetime.fromisoformat("2026-12-04T" + value + "+09:00")
    client.patch(PATH, headers=teacher, json=NIGHT)
    for clock, expected in (("00:00", "07:00"), ("06:59", "07:00"), ("07:00", "07:00"), ("21:59", "21:59")):
        assert deliver_after(at(clock), "teacher", user_id=seed.TEACHER) == at(expected)
    late = at("22:00").astimezone(timezone.utc)
    assert deliver_after(late, "teacher", user_id=seed.TEACHER).isoformat() == "2026-12-05T07:00:00+09:00"
    for role, risk, category, kind in (("parent", None, None, None), ("teacher", "urgent", "child_safety", None),
                                       ("teacher", None, None, "pickup")):
        assert deliver_after(late, role, risk, category, request_type=kind, user_id=seed.TEACHER) == late
    client.patch(PATH, headers=teacher, json={"quiet_start": "12:00", "quiet_end": "13:00"})
    assert deliver_after(at("12:00"), "teacher", user_id=seed.TEACHER) == at("13:00")
    client.patch(PATH, headers=teacher, json=EMPTY)
    assert deliver_after(at("22:00"), "teacher", user_id=seed.TEACHER).isoformat() == "2026-12-07T09:00:00+09:00"
