"""59~61번의 권한·반개구간·예약 충돌을 mock·DB에서 같은 요청으로 검증해요."""

from datetime import datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import text

from app import backend
from app.core.db import transaction
from app.core.schedule import KST
from app.mock import seed, store
from tests.integration.api.helpers import BASE, err
from tests.integration.api.test_consultation_reminders import booking

URL = BASE + "/staff/busy-blocks"
START = datetime(2030, 1, 7, 15, tzinfo=KST)
BODY = {"start_at": START.isoformat(), "end_at": (START+timedelta(minutes=30)).isoformat(), "kind": "meeting"}
QUERY = {"from": BODY["start_at"], "to": BODY["end_at"]}


@pytest.fixture(autouse=True, params=["mock", "db"])
def busy_backend(request, monkeypatch):
    if request.param == "db":
        engine = request.getfixturevalue("seeded_db")
        from app.core import users
        from app.modules.consultations import busy_blocks
    else:
        from app.mock import busy_blocks
        users, engine = store, None
    monkeypatch.setattr(backend, "users", users)
    monkeypatch.setattr(backend, "busy_blocks", busy_blocks)
    return SimpleNamespace(engine=engine)


def test_crud_overlap_filter_order_and_owner_only_delete(client, teacher, teacher_other, director):
    row = client.post(URL, headers=teacher, json=BODY)
    assert row.status_code == 201, row.text
    row = row.json()
    assert set(row) == {"id", "user_id", "start_at", "end_at", "kind"} and row["user_id"] == str(seed.TEACHER)
    assert client.get(URL, headers=teacher, params=QUERY).json()["items"] == [row]
    assert client.get(URL, headers=teacher_other, params=QUERY).json() == {"items": []}
    assert client.get(URL, headers=director, params={**QUERY, "user_id": str(seed.TEACHER)}).json()["items"] == [row]
    adjacent = {"from": BODY["end_at"], "to": (START+timedelta(hours=1)).isoformat()}
    assert client.get(URL, headers=teacher, params=adjacent).json()["items"] == []
    earlier = {**BODY, "start_at": (START-timedelta(minutes=30)).isoformat(), "end_at": BODY["start_at"]}
    assert client.post(URL, headers=teacher, json=earlier).status_code == 201
    assert [r["start_at"] for r in client.get(URL, headers=teacher, params={**QUERY, "from": earlier["start_at"]})
            .json()["items"]] == [earlier["start_at"], BODY["start_at"]]
    err(client.delete(f"{URL}/{row['id']}", headers=director), 404, "NOT_FOUND")
    err(client.delete(f"{URL}/{row['id']}", headers=teacher_other), 404, "NOT_FOUND")
    assert client.delete(f"{URL}/{row['id']}", headers=teacher).status_code == 204
    err(client.delete(f"{URL}/{row['id']}", headers=teacher), 404, "NOT_FOUND")


def test_forbidden_scope_is_recorded_without_foreign_data(client, teacher, director, busy_backend):
    foreign, other = uuid4(), uuid4()
    if busy_backend.engine:
        with transaction() as connection:
            connection.execute(text("INSERT INTO organizations(id,name) VALUES (:id,'[TEST] 다른 원')"), {"id": foreign})
            connection.execute(text("""INSERT INTO users(id,org_id,role,login_id,display_name,password_hash)
                VALUES (:id,:org,'teacher','test-foreign','[TEST] 교사','test')"""), {"id": other, "org": foreign})
    else:
        store.state().users[other] = store.User(other, foreign, "teacher", "test-foreign", "test", "[TEST] 교사")
    for headers, uid in ((teacher, seed.TEACHER_OTHER), (director, other), (director, seed.PARENT), (director, uuid4())):
        err(client.get(URL, headers=headers, params={**QUERY, "user_id": str(uid)}), 404, "NOT_FOUND")
    if busy_backend.engine:
        with transaction() as connection:
            events = connection.execute(text("SELECT * FROM events WHERE action='permission_denied'")).mappings().all()
    else:
        events = [e.__dict__ for e in store.state().events if e.action == "permission_denied"]
    assert len(events) == 4 and all(e["org_id"] == seed.ORG for e in events)
    assert all(e["detail"]["resource"] == "staff" and e["detail"]["trace_id"] for e in events)


def test_auth_role_and_validation(client, teacher, parent):
    err(client.get(URL, params=QUERY), 401, "UNAUTHENTICATED")
    for method, path, kwargs in (("get", URL, {"params": QUERY}), ("post", URL, {"json": BODY}),
                                 ("delete", URL+"/1", {})):
        err(getattr(client, method)(path, headers=parent, **kwargs), 403, "FORBIDDEN_ROLE")
    for changes in ({"end_at": BODY["start_at"]}, {"end_at": (START-timedelta(minutes=1)).isoformat()},
                    {"start_at": "2030-01-07T15:00:00"}, {"kind": "unknown"}, {"user_id": str(seed.TEACHER_OTHER)}):
        err(client.post(URL, headers=teacher, json={**BODY, **changes}), 422, "VALIDATION_FAILED")
    for query in ({}, {**QUERY, "to": BODY["start_at"]}, {**QUERY, "from": "wrong"}):
        err(client.get(URL, headers=teacher, params=query), 422, "VALIDATION_FAILED")


def test_confirmed_and_delayed_booking_conflict_but_cancelled_and_adjacent_do_not(client, teacher, busy_backend):
    bid, _ = booking(busy_backend, START)
    err(client.post(URL, headers=teacher, json=BODY), 409, "SLOT_TAKEN")
    extended = {**BODY, "start_at": BODY["end_at"], "end_at": (START+timedelta(hours=1)).isoformat()}
    assert client.post(URL, headers=teacher, json=extended).status_code == 201
    if busy_backend.engine:
        with transaction() as connection:
            connection.execute(text("UPDATE consultation_bookings SET expected_end_at=:end WHERE id=:id"),
                               {"id": bid, "end": START+timedelta(hours=1)})
    else:
        store.state().bookings[bid].expected_end_at = START+timedelta(hours=1)
    err(client.post(URL, headers=teacher, json=extended), 409, "SLOT_TAKEN")
    if busy_backend.engine:
        with transaction() as connection:
            connection.execute(text("UPDATE consultation_bookings SET status='cancelled' WHERE id=:id"), {"id": bid})
    else:
        store.state().bookings[bid].status = "cancelled"
    assert client.post(URL, headers=teacher, json=BODY).status_code == 201
