"""[TEST] 70번 API: 원장이 재배정할 때 고를 선생님 목록을 mock·임시 PG에서 같은 계약으로 확인해요."""

from datetime import timedelta
from uuid import uuid4

import pytest
from argon2 import PasswordHasher
from sqlalchemy import text

from app import backend
from app.core.db import transaction
from app.mock import seed, store
from tests.integration.api.helpers import BASE, err
from tests.integration.api.test_cards import create, detail

STAR = {"id": str(seed.CLASS_STAR), "name": "만 4세 별빛반"}
SUN = {"id": str(seed.CLASS_SUN), "name": "만 5세 햇님반"}


@pytest.fixture(autouse=True, params=["mock", "db"])
def teachers_backend(request, monkeypatch, _reset_store):
    if request.param == "db":
        request.getfixturevalue("seeded_db")
        from app.core import users
        from app.modules.cards import cards, card_views
        from app.modules.notifications import notifications
        from app.modules.requests import requests
    else:
        from app.mock import cards, card_views, notifications, request_actions as requests
        users = store
    for name, module in dict(users=users, cards=cards, card_views=card_views,
                             notifications=notifications, request_actions=requests).items():
        monkeypatch.setattr(backend, name, module)
    return request.param


def listing(client, headers):
    response = client.get(BASE + "/staff/teachers", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["items"]


def item(teacher_id, name, *classrooms):
    return {"id": str(teacher_id), "display_name": name, "classrooms": list(classrooms)}


def test_director_gets_name_and_classrooms_only(client, director):
    items = listing(client, director)
    assert items == [
        item(seed.TEACHER, "별빛반 선생님", STAR),
        item(seed.TEACHER_AIDE, "보조 선생님"),
        item(seed.TEACHER_OTHER, "햇님반 선생님", SUN),
    ]
    # 연락처·로그인 ID·역할 칸은 주지 않아요.
    assert all(set(row) == {"id", "display_name", "classrooms"} for row in items)


def test_list_skips_inactive_other_org_and_ended_assignments(client, director, teachers_backend):
    other_org, outsider = uuid4(), uuid4()
    yesterday = store.now().date() - timedelta(days=1)
    if teachers_backend == "mock":
        state = store.state()
        state.users[seed.TEACHER_OTHER].is_active = False
        state.users[outsider] = store.User(id=outsider, org_id=other_org, role="teacher", login_id="[TEST] outsider",
                                           password=seed.DEMO_PASSWORD, display_name="[TEST] 다른 원 선생님")
        for staff in state.classroom_staff:
            if staff.user_id == seed.TEACHER:
                staff.valid_to = yesterday
    else:
        with transaction() as connection:
            connection.execute(text("UPDATE users SET is_active=false WHERE id=:id"), {"id": seed.TEACHER_OTHER})
            connection.execute(text("INSERT INTO organizations(id,name) VALUES (:org,'[TEST] 다른 원')"), {"org": other_org})
            connection.execute(text("""
                INSERT INTO users(id,org_id,role,login_id,display_name,password_hash)
                VALUES (:id,:org,'teacher','[TEST] outsider','[TEST] 다른 원 선생님',:hash)
            """), {"id": outsider, "org": other_org, "hash": PasswordHasher().hash(seed.DEMO_PASSWORD)})
            connection.execute(text("UPDATE classroom_staff SET valid_to=:day WHERE user_id=:id"),
                               {"day": yesterday, "id": seed.TEACHER})
    # 담임 기간이 끝난 선생님은 남되 반이 비고, 비활성·다른 기관 선생님은 빠져요.
    assert listing(client, director) == [item(seed.TEACHER, "별빛반 선생님"), item(seed.TEACHER_AIDE, "보조 선생님")]


def test_only_director_can_list(client, teacher, parent):
    assert client.get(BASE + "/staff/teachers").status_code == 401
    for headers in (teacher, parent):
        err(client.get(BASE + "/staff/teachers", headers=headers), 403, "FORBIDDEN_ROLE")


def test_teacher_from_list_without_classroom_can_take_reassigned_card(client, parent, teacher, director):
    aide = next(row for row in listing(client, director) if not row["classrooms"])
    rid, cid = create(client, parent, teacher)
    response = client.post(f"{BASE}/cards/{cid}/reassign", headers=director,
                           json={"assignee_id": aide["id"], "reason": "[TEST] 담당 부재"})
    assert response.status_code == 200, response.text
    res = client.post("/api/v1/auth/login", json={"login_id": "teacher03", "password": seed.DEMO_PASSWORD})
    assert res.status_code == 200, res.text
    teacher03 = {"Authorization": f"Bearer {res.json()['access_token']}"}
    assert detail(client, teacher03, cid)["request"]["id"] == rid
