"""56~58번과 API 22의 메모 우선순위를 모의·임시 PG에서 대조해요."""

from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from app import backend
from app.core.db import transaction
from app.mock import seed, store
from tests.integration.api.helpers import BASE, err

URL = BASE + f"/classrooms/{seed.CLASS_STAR}/records"


@pytest.fixture(autouse=True, params=["mock", "db"])
def daily_records_backend(request, monkeypatch):
    if request.param == "db":
        request.getfixturevalue("seeded_db")
        from app.core import users
        from app.modules.daily_records import records as daily_records
        from app.modules.daily_notes import notes
    else:
        from app.mock import daily_records, notes
        users = store
    for name, module in dict(users=users, daily_records=daily_records, notes=notes).items():
        monkeypatch.setattr(backend, name, module)
    return request.param


def create(client, teacher, **changes):
    response = client.post(URL, headers=teacher,
                           json={"child_id": str(seed.CHILD), "body": "[TEST] 블록 놀이", **changes})
    assert response.status_code == 201, response.text
    return response.json()


def test_daily_records_crud_child_time_order_and_soft_delete(client, teacher, director, daily_records_backend):
    first = create(client, teacher, body="[TEST] 먼저")
    last = create(client, teacher, body="[TEST] 나중")
    other = create(client, teacher, child_id=str(seed.demo_id("503")))
    create(client, teacher, note_date=(store.now().date()-timedelta(days=1)).isoformat())
    query = {"date": first["note_date"]}
    assert first["note_date"] == store.now().date().isoformat()
    assert set(first) == {"id", "classroom_id", "child_id", "body", "note_date", "author_id", "created_at"}
    assert client.get(URL, headers=teacher, params=query).json()["items"] == [first, last, other]
    assert client.get(URL, headers=director, params=query).json()["items"] == [first, last, other]
    assert client.delete(BASE+f"/records/{first['id']}", headers=teacher).status_code == 204
    err(client.delete(BASE+f"/records/{first['id']}", headers=teacher), 404, "NOT_FOUND")
    assert client.get(URL, headers=teacher, params=query).json()["items"] == [last, other]
    if daily_records_backend == "db":
        with transaction() as connection:
            row = connection.execute(text("SELECT * FROM daily_records WHERE id=:id"),
                                     {"id": first["id"]}).mappings().one()
    else:
        row = store.state().daily_records[UUID(first["id"])]
    assert row["deleted_at"] and row["body"] == first["body"] and row["author_id"] == seed.TEACHER


def test_daily_records_auth_roles_and_validation(client, teacher, parent, director):
    row = create(client, teacher, body="가"*500)
    err(client.get(URL, params={"date": row["note_date"]}), 401, "UNAUTHENTICATED")
    err(client.get(URL, headers=parent, params={"date": row["note_date"]}), 403, "FORBIDDEN_ROLE")
    for actor in (parent, director):
        err(client.post(URL, headers=actor, json={"child_id": str(seed.CHILD), "body": "[TEST] 금지"}),
            403, "FORBIDDEN_ROLE")
        err(client.delete(BASE+f"/records/{row['id']}", headers=actor), 403, "FORBIDDEN_ROLE")
    for changes in ({"body": "가"*501}, {"body": ""}, {"note_date": "wrong"},
                    {"child_id": "wrong"}, {"author_id": str(seed.TEACHER_OTHER)}):
        err(client.post(URL, headers=teacher, json={"child_id": str(seed.CHILD), "body": "[TEST] 글", **changes}),
            422, "VALIDATION_FAILED")
    for query in ({}, {"date": "wrong"}):
        err(client.get(URL, headers=teacher, params=query), 422, "VALIDATION_FAILED")
    assert client.get(URL, headers=teacher, params={"date": row["note_date"]}).json()["items"] == [row]


def test_daily_records_scope_denials_and_current_teacher_delete(client, teacher, teacher_other, director,
                                                                daily_records_backend):
    row = create(client, teacher)
    foreign, classroom = uuid4(), uuid4()
    if daily_records_backend == "db":
        with transaction() as connection:
            connection.execute(text("INSERT INTO organizations(id,name) VALUES (:id,'[TEST] 다른 원')"), {"id": foreign})
            connection.execute(text("INSERT INTO classrooms(id,org_id,name,school_year) VALUES (:id,:org,'[TEST] 반',2026)"),
                               {"id": classroom, "org": foreign})
    else:
        store.state().classrooms[classroom] = store.Classroom(classroom, foreign, "[TEST] 반")
    err(client.get(URL, headers=teacher_other, params={"date": row["note_date"]}), 404, "NOT_FOUND")
    err(client.get(BASE+f"/classrooms/{classroom}/records", headers=director,
                   params={"date": row["note_date"]}), 404, "NOT_FOUND")
    for path, child in ((URL, seed.CHILD_OTHER), (URL, uuid4()),
                        (BASE+f"/classrooms/{classroom}/records", seed.CHILD)):
        err(client.post(path, headers=teacher, json={"child_id": str(child), "body": "[TEST] 금지"}), 404, "NOT_FOUND")
    err(client.delete(BASE+f"/records/{row['id']}", headers=teacher_other), 404, "NOT_FOUND")
    if daily_records_backend == "db":
        with transaction() as connection:
            events = connection.execute(text("SELECT * FROM events WHERE action='permission_denied'")).mappings().all()
            connection.execute(text("""INSERT INTO classroom_staff(org_id,classroom_id,user_id)
                VALUES (:org,:class,:user)"""), {"org": seed.ORG, "class": seed.CLASS_STAR, "user": seed.TEACHER_OTHER})
    else:
        events = [e.__dict__ for e in store.state().events if e.action == "permission_denied"]
        store.state().classroom_staff.append(store.ClassroomStaff(seed.CLASS_STAR, seed.TEACHER_OTHER))
    assert len(events) == 6 and all(e["org_id"] == seed.ORG for e in events)
    assert client.delete(BASE+f"/records/{row['id']}", headers=teacher_other).status_code == 204


def test_daily_records_draft_fallback_explicit_priority_and_regeneration(client, teacher):
    first = create(client, teacher, body="[TEST] 먼저 관찰")
    create(client, teacher, body="[TEST] 나중 관찰")
    create(client, teacher, body="[TEST] 어제", note_date=(store.now().date()-timedelta(days=1)).isoformat())
    removed = create(client, teacher, body="[TEST] 삭제한 기록")
    assert client.delete(BASE+f"/records/{removed['id']}", headers=teacher).status_code == 204
    create(client, teacher, child_id=str(seed.demo_id("503")), body="[TEST] 서버 글")
    create(client, teacher, child_id=str(seed.demo_id("5401")), body="[TEST] 빈 메모보다 후순위")
    response = client.post(BASE+"/daily-notes/drafts", headers=teacher, json={
        "classroom_id": str(seed.CLASS_STAR), "note_date": first["note_date"], "activities": "[TEST] 산책",
        "supplies": "", "child_memos": [{"child_id": str(seed.demo_id("503")), "memo": "[TEST] 직접 쓴 글"},
                                       {"child_id": str(seed.demo_id("5401")), "memo": " "}]})
    assert response.status_code == 202 and set(response.json()) == {"input_id", "draft_status", "error"}
    def memos():
        notes = client.get(BASE+"/daily-notes", headers=teacher,
                           params={"date": first["note_date"], "classroom_id": str(seed.CLASS_STAR)}).json()["items"]
        return {n["child_id"]: [i["value"] for i in n["content"]["items"] if i["key"] == "child"] for n in notes}
    result = memos()
    assert result[str(seed.CHILD)] == ["[TEST] 먼저 관찰\n[TEST] 나중 관찰"]
    assert result[str(seed.demo_id("503"))] == ["[TEST] 직접 쓴 글"]
    assert result[str(seed.demo_id("5401"))] == [] and result[str(seed.demo_id("5402"))] == []
    create(client, teacher, body="[TEST] 추가 관찰")
    assert client.post(BASE+f"/daily-notes/drafts/{response.json()['input_id']}/regenerate", headers=teacher).status_code == 202
    assert memos()[str(seed.CHILD)] == ["[TEST] 먼저 관찰\n[TEST] 나중 관찰\n[TEST] 추가 관찰"]
