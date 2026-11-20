"""기존 인증 시험과 DB 계정 검증을 같은 HTTP 호출로 실행한다."""

from datetime import timedelta
from uuid import uuid4

import jwt
import pytest
from sqlalchemy import text

from app import backend
from app.core.auth import issue_token
from app.core.config import settings
from app.mock import seed, store

BASE = "/api/v1"


@pytest.fixture(autouse=True, params=["mock", "db"])
def auth_backend(request, monkeypatch):
    if request.param == "db":
        request.getfixturevalue("seeded_db")
        from app.core import users
        monkeypatch.setattr(backend, "users", users)
    else:
        monkeypatch.setattr(backend, "users", store)
    return request.param


def change_user(auth_backend, user_id, **values):
    if auth_backend == "mock":
        for name, value in values.items():
            setattr(store.get_user(user_id), name, value)
    else:
        from app.core.db import transaction
        with transaction() as connection:
            # 칸 이름은 이 파일의 고정 호출에서만 온다.
            assignments = ", ".join(f"{name}=:{name}" for name in values)
            connection.execute(text(f"UPDATE users SET {assignments} WHERE id=:id"),
                               {"id": user_id, **values})


def test_missing_token_is_401(client):
    res = client.get(BASE + "/me")
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "UNAUTHENTICATED"


def test_me_gives_teacher_classrooms_and_parent_children(client, teacher, parent):
    assert client.get(BASE + "/me", headers=teacher).json()["user"]["classroom_ids"] == [str(seed.CLASS_STAR)]
    assert [c["id"] for c in client.get(BASE + "/me", headers=parent).json()["children"]] == [str(seed.CHILD)]


@pytest.mark.parametrize("mutation", ["expired", "version", "inactive", "org", "role", "signature",
                                      "missing_exp", "missing_ver", "missing_sub", "missing_org",
                                      "missing_role", "missing_iat", "bad_sub", "unknown_user"])
def test_auth_rejects_invalid_claims(client, mutation, auth_backend):
    user = backend.users.get_user(seed.TEACHER)
    claims = jwt.decode(issue_token(user), settings.jwt_secret, algorithms=["HS256"])
    if mutation == "expired":
        claims["exp"] = 0
    elif mutation == "version":
        change_user(auth_backend, user.id, token_version=user.token_version + 1)
    elif mutation == "inactive":
        change_user(auth_backend, user.id, is_active=False)
    elif mutation == "org":
        claims["org"] = str(uuid4())
    elif mutation == "role":
        claims["role"] = "director"
    elif mutation.startswith("missing_"):
        claims.pop(mutation.removeprefix("missing_"))
    elif mutation == "bad_sub":
        claims["sub"] = ["not-a-uuid"]
    elif mutation == "unknown_user":
        claims["sub"] = str(uuid4())
    key = "wrong-signature-key-32-characters-long" if mutation == "signature" else settings.jwt_secret
    token = jwt.encode(claims, key, algorithm="HS256")
    response = client.get(BASE + "/me", headers={"Authorization": "Bearer " + token})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


@pytest.mark.parametrize("login_id,password", [("missing", "demo1234"), ("teacher01", "wrong")])
def test_bad_login_has_common_error(client, login_id, password):
    response = client.post(BASE + "/auth/login", json={"login_id": login_id, "password": password},
                           headers={"X-Request-ID": "auth-failed"})
    assert response.status_code == 401
    assert response.json()["error"] == {
        "code": "UNAUTHENTICATED", "message": "아이디나 비밀번호가 맞지 않아요.",
        "trace_id": "auth-failed", "details": {}}


def test_inactive_account_cannot_login(client, auth_backend):
    change_user(auth_backend, seed.TEACHER, is_active=False)
    assert client.post(BASE + "/auth/login", json={"login_id": "teacher01", "password": "demo1234"}).status_code == 401


@pytest.mark.parametrize("login_id,role", [("parent01", "parent"), ("teacher01", "teacher"),
                                          ("director01", "director")])
def test_login_and_me_keep_contract(client, login_id, role):
    response = client.post(BASE + "/auth/login", json={"login_id": login_id, "password": "demo1234"})
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"access_token", "token_type", "user", "children"}
    assert body["token_type"] == "bearer"
    assert body["user"]["role"] == role
    assert "password" not in body["user"] and "password_hash" not in body["user"]
    claims = jwt.decode(body["access_token"], settings.jwt_secret, algorithms=["HS256"])
    assert set(claims) == {"sub", "org", "role", "ver", "iat", "exp"}
    assert claims["exp"] - claims["iat"] == settings.jwt_access_ttl_hours * 3600
    assert claims["org"] == str(seed.ORG) and claims["role"] == role and claims["ver"] == 0
    me = client.get(BASE + "/me", headers={"Authorization": "Bearer " + body["access_token"]})
    assert me.status_code == 200
    assert me.json() == {"user": body["user"], "children": body["children"]}


def test_me_rechecks_assignment_period(client, teacher, auth_backend):
    from datetime import datetime
    from app.core.schedule import KST
    today = datetime.now(KST).date()
    if auth_backend == "mock":
        store.state().classroom_staff[0].valid_to = today - timedelta(days=1)
    else:
        from app.core.db import transaction
        with transaction() as connection:
            connection.execute(text("UPDATE classroom_staff SET valid_to=:until WHERE user_id=:id"),
                               {"until": today - timedelta(days=1), "id": seed.TEACHER})
    assert client.get(BASE + "/me", headers=teacher).json()["user"]["classroom_ids"] == []
