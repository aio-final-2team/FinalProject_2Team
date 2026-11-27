"""[제안] 원 일정의 같은 계약을 mock·임시 PG에서 확인해요."""

from dataclasses import asdict
from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import text

from app import backend
from app.core.db import transaction
from app.mock import seed, store
from tests.integration.api.helpers import BASE, err

PERIOD = {"from": "2026-12-01", "to": "2027-01-31"}


@pytest.fixture(autouse=True, params=["mock", "db"])
def calendar_backend(request, monkeypatch, _reset_store):
    if request.param == "db":
        request.getfixturevalue("seeded_db")
        from app.core import users
        from app.modules.documents import calendar
    else:
        from app.mock import calendar
        users = store
    monkeypatch.setattr(backend, "users", users)
    monkeypatch.setattr(backend, "calendar", calendar)
    return request.param


def add(mode, content="- 행사: 2026-12-18", targets=(), location="2쪽 3항", **changes):
    doc = store.Document(**({"id": uuid4(), "org_id": seed.ORG, "title": "[TEST] 가상 일정", "doc_type": "schedule",
                            "visibility": "all", "content_sha256": str(uuid4()), "effective_from": date(2026, 11, 1),
                            "created_at": store.now()} | changes))
    if mode == "mock":
        state = store.state()
        state.documents[doc.id], state.document_classrooms[doc.id] = doc, list(targets)
        index = state.next_int()
        state.chunks[index] = store.Chunk(index, doc.org_id, doc.id, 0, location, content)
    else:
        values = asdict(doc)
        with transaction() as connection:
            if doc.org_id != seed.ORG:
                connection.execute(text("INSERT INTO organizations(id,name) VALUES (:org,'[TEST] 외부')"), {"org": doc.org_id})
            connection.execute(text("INSERT INTO documents (" + ",".join(values) + ") VALUES (" +
                                    ",".join(":" + k for k in values) + ")"), values)
            for target in targets:
                connection.execute(text("INSERT INTO document_classrooms(org_id,document_id,classroom_id) VALUES (:org,:doc,:class)"),
                                   {"org": doc.org_id, "doc": doc.id, "class": target})
            connection.execute(text("INSERT INTO document_chunks(org_id,document_id,chunk_index,location,content) VALUES (:org,:doc,0,:loc,:content)"),
                               {"org": doc.org_id, "doc": doc.id, "loc": location, "content": content})
    return str(doc.id)


def test_calendar_period_overlap_preserves_conflicting_sources_and_locations(client, parent, calendar_backend):
    first = add(calendar_backend, "- 겨울방학: 2026-12-24 ~ 2027-01-03\n- 비용: 100원\n- 잘못: 2026-13-40", doc_type="notice")
    second = add(calendar_backend, "- 겨울방학: 2026-12-26 ~ 2027-01-03")
    rows = client.get(BASE + "/calendar", headers=parent, params={"from": "2026-12-28", "to": "2026-12-28"}).json()["items"]
    assert rows == [{"date": day, "end_date": "2027-01-03", "title": "겨울방학", "document_id": did,
                     "document_title": "[TEST] 가상 일정", "location": "2쪽 3항"}
                    for day, did in (("2026-12-24", first), ("2026-12-26", second))]
    for day, count in (("2026-12-24", 1), ("2027-01-03", 2), ("2027-01-04", 0)):
        assert len(client.get(BASE + "/calendar", headers=parent, params={"from": day, "to": day}).json()["items"]) == count
    for title, location in (("[TEST] 나 자료", "가 위치"), ("[TEST] 가 자료", "나 위치"), ("[TEST] 가 자료", "가 위치")):
        add(calendar_backend, "- 나 행사: 2026-12-18\n- 가 행사: 2026-12-18", title=title, location=location)
    rows = client.get(BASE + "/calendar", headers=parent, params={"from": "2026-12-18", "to": "2026-12-18"}).json()["items"]
    assert [(r["title"], r["document_title"], r["location"]) for r in rows] == [
        (event, title, loc) for event in ("가 행사", "나 행사") for title, loc in
        (("[TEST] 가 자료", "가 위치"), ("[TEST] 가 자료", "나 위치"), ("[TEST] 나 자료", "가 위치"))]


def test_calendar_scope_status_visibility_and_current_assignments(client, parent, teacher, director, calendar_backend):
    own = add(calendar_backend, targets=[seed.CLASS_STAR])
    other = add(calendar_backend, targets=[seed.CLASS_SUN])
    public = add(calendar_backend, location="가 위치")
    staff = add(calendar_backend, visibility="staff")
    for changes in ({"status": "superseded"}, {"status": "conflict_pending"}, {"ingest_status": "failed"}):
        add(calendar_backend, **changes)
    for kind in ("menu", "policy", "consult_timetable"):
        add(calendar_backend, doc_type=kind)
    add(calendar_backend, org_id=uuid4())
    for actor, expected in ((parent, {own, public}), (teacher, {own, public, staff}), (director, {own, other, public, staff})):
        response = client.get(BASE + "/calendar", headers={**actor, "X-Request-ID": "[TEST]-calendar"}, params=PERIOD)
        assert response.status_code == 200, response.text
        rows = response.json()["items"]
        assert {r["document_id"] for r in rows} == expected and all(r["end_date"] is None for r in rows)
        assert rows == sorted(rows, key=lambda r: (r["date"], r["title"], r["document_title"], r["location"]))
        assert client.get(BASE + "/calendar", headers=actor, params=PERIOD).json() == response.json()
    if calendar_backend == "mock":
        events = [e.__dict__ for e in store.state().events if e.action == "permission_denied"]
        store.state().classroom_staff.clear()
        store.state().children[seed.CHILD].guardian_ids.clear()
    else:
        with transaction() as connection:
            events = connection.execute(text("SELECT * FROM events WHERE action='permission_denied'")).mappings().all()
            connection.execute(text("UPDATE classroom_staff SET valid_to=CURRENT_DATE-1"))
            connection.execute(text("DELETE FROM child_guardians WHERE user_id=:user"), {"user": seed.PARENT})
    assert events == []
    for actor, expected in ((parent, {public}), (teacher, {public, staff})):
        assert {r["document_id"] for r in client.get(BASE + "/calendar", headers=actor, params=PERIOD).json()["items"]} == expected
    if calendar_backend == "mock":
        assert not any(e.action == "permission_denied" for e in store.state().events)
    else:
        with transaction() as connection:
            assert connection.scalar(text("SELECT count(*) FROM events WHERE action='permission_denied'")) == 0


def test_calendar_required_dates_validation_and_login(client, parent):
    for query in ({}, {"from": "2026-12-01"}, {"to": "2026-12-31"},
                  {"from": "bad", "to": "2026-12-31"}, {"from": "2026-02-30", "to": "2026-12-31"},
                  {"from": "2026-12-31", "to": "2026-12-01"}):
        err(client.get(BASE + "/calendar", headers=parent, params=query), 422, "VALIDATION_FAILED")
    err(client.get(BASE + "/calendar", params=PERIOD), 401, "UNAUTHENTICATED")
