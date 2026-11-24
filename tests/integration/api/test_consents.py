"""[제안] 필수 동의 계약과 여섯 쓰기 경로를 mock·시험 PG에서 확인해요."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import text

from app import backend
from app.core.constants import CONSENT_VERSION
from app.core.consents import required_items
from app.core.db import transaction
from app.mock import seed, store
from tests.integration.api.conftest import _login
from tests.integration.api.helpers import BASE, err


@pytest.fixture(autouse=True, params=["mock", "db"])
def consent_backend(request, monkeypatch, _reset_store):
    if request.param == "db":
        request.getfixturevalue("seeded_db")
        from app.core import users
        from app.modules.consents import consents
        from app.modules.daily_notes import notes
        from app.modules.feed import feed
        from app.modules.requests import requests as request_actions
    else:
        from app.mock import consents, notes, feed, request_actions
        users = store
    for name, module in dict(users=users, consents=consents, notes=notes, feed=feed,
                             request_actions=request_actions).items():
        monkeypatch.setattr(backend, name, module)
    return request.param


def expire(mode, user_id):
    if mode == "mock":
        rows = store.state().consents
        for key in list(rows):
            if key[1] == user_id:
                rows[(*key[:3], "previous")] = rows.pop(key)
    else:
        with transaction() as connection:
            connection.execute(text("UPDATE user_consents SET terms_version='previous' WHERE user_id=:id"),
                               {"id": user_id})


def records(mode, user_id):
    if mode == "mock":
        return {key: at for key, at in store.state().consents.items() if key[1] == user_id}
    with transaction() as connection:
        return {tuple(row[:4]): row[4] for row in connection.execute(text("""
            SELECT org_id,user_id,item,terms_version,agreed_at FROM user_consents WHERE user_id=:id
        """), {"id": user_id})}


def events(mode):
    if mode == "mock":
        return [e.__dict__ for e in store.state().events if e.action == "consent_agreed"]
    with transaction() as connection:
        return list(connection.execute(text("SELECT * FROM events WHERE action='consent_agreed'")).mappings())


def write_counts(mode):
    if mode == "mock":
        state = store.state()
        return tuple(len(rows) for rows in (state.requests, state.messages, state.note_inputs, state.feed_posts))
    with transaction() as connection:
        return tuple(connection.scalar(text(f"SELECT count(*) FROM {table}"))
                     for table in ("requests", "request_messages", "daily_note_inputs", "feed_posts"))


def agree(client, headers, role="parent", **changes):
    return client.post(BASE + "/consents", headers=headers,
                       json={"items": required_items(role), "terms_version": CONSENT_VERSION, **changes})


@pytest.mark.parametrize("role,login,count", [("parent", "parent01", 6), ("teacher", "teacher01", 3),
                                            ("director", "director01", 3)])
def test_role_items_and_seed_accounts_start_complete(client, role, login, count):
    headers = _login(client, login)
    result = client.get(BASE + "/consents", headers=headers).json()
    assert result["terms_version"] == CONSENT_VERSION and result["complete"] is True
    assert [i["item"] for i in result["items"]] == required_items(role)
    assert len(result["items"]) == count
    assert all(i["label"] and i["required"] is True and i["agreed_at"] for i in result["items"])
    assert client.get(BASE + "/me", headers=headers).json()["user"]["consents_complete"] is True
    assert all(backend.consents.get(backend.users.get_user(u["id"]))["complete"] for u in seed.USERS)


@pytest.mark.parametrize("role,login,uid", [("parent", "parent01", seed.PARENT),
    ("teacher", "teacher01", seed.TEACHER), ("director", "director01", seed.DIRECTOR)])
def test_agree_is_atomic_idempotent_preserves_old_version_and_me(client, consent_backend, role, login, uid):
    headers = _login(client, login)
    expire(consent_backend, uid)
    old = records(consent_backend, uid)
    result = client.get(BASE + "/consents", headers=headers).json()
    assert result["complete"] is False and all(i["agreed_at"] is None for i in result["items"])
    assert client.get(BASE + "/me", headers=headers).json()["user"]["consents_complete"] is False
    headers = {**headers, "X-Request-ID": "[TEST]-consent"}
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: agree(client, headers, role), range(2)))
    assert all(r.status_code == 200 for r in responses), [r.text for r in responses]
    first = responses[0].json()
    assert first["complete"] is True and first == responses[1].json()
    assert agree(client, headers, role, items=list(reversed(required_items(role)))).json() == first
    assert client.get(BASE + "/consents", headers=headers).json() == first
    assert client.get(BASE + "/me", headers=headers).json()["user"]["consents_complete"] is True
    rows = records(consent_backend, uid)
    assert len(rows) == len(old) * 2 and all(rows[key] == at for key, at in old.items())
    audit = events(consent_backend)
    assert len(audit) == 1 and audit[0]["actor_id"] == uid and audit[0]["actor_type"] == "user"
    assert audit[0]["detail"] == {"items": required_items(role), "terms_version": CONSENT_VERSION,
                                   "trace_id": "[TEST]-consent"}


@pytest.mark.parametrize("changes,status,code", [
    ({"items": ["terms"]}, 422, "CONSENT_INCOMPLETE"),
    ({"items": ["terms", "privacy", "ai_processing", "child_info"]}, 422, "VALIDATION_FAILED"),
    ({"items": ["unknown"]}, 422, "VALIDATION_FAILED"),
    ({"terms_version": "previous"}, 409, "CONSENT_VERSION_MISMATCH"),
    ({"unexpected": True}, 422, "VALIDATION_FAILED"),
])
def test_invalid_agreement_saves_no_partial_records(client, teacher, consent_backend, changes, status, code):
    expire(consent_backend, seed.TEACHER)
    before = records(consent_backend, seed.TEACHER)
    response = agree(client, teacher, "teacher", **changes)
    err(response, status, code)
    if code == "CONSENT_INCOMPLETE":
        assert response.json()["error"]["details"]["missing_items"] == ["privacy", "ai_processing"]
    assert records(consent_backend, seed.TEACHER) == before and events(consent_backend) == []


@pytest.mark.parametrize("target", ["request", "message", "draft", "regenerate", "class", "org"])
def test_six_writes_block_until_current_consent_and_reads_stay_open(client, parent, teacher, consent_backend, target):
    is_teacher = target in ("draft", "regenerate")
    actor, uid, role = (teacher, seed.TEACHER, "teacher") if is_teacher else (parent, seed.PARENT, "parent")
    note = {"classroom_id": str(seed.CLASS_STAR), "note_date": store.now().date().isoformat(),
            "activities": "[TEST] 블록 놀이", "supplies": "[TEST] 수건"}
    if target == "regenerate":
        created = client.post(BASE + "/daily-notes/drafts", headers=actor, json=note)
        assert created.status_code == 202, created.text
        path = f"/daily-notes/drafts/{created.json()['input_id']}/regenerate"
    else:
        path = {"request": "/requests", "message": f"/requests/{seed.REQUEST_COUGH}/messages",
                "draft": "/daily-notes/drafts", "class": f"/classrooms/{seed.CLASS_STAR}/posts",
                "org": f"/organizations/{seed.ORG}/posts"}[target]
    def send():
        if target in ("class", "org"):
            return client.post(BASE + path, headers=actor, data={"body": "[TEST] 동의 뒤 사진"},
                               files=[("files", ("test.png", seed.feed_png(), "image/png"))])
        body = {"request": {"client_request_id": str(uuid4()), "type": "inquiry", "body": "[TEST] 준비물",
                            "child_id": str(seed.CHILD)}, "message": {"body": "[TEST] 추가 글"}, "draft": note}
        return client.post(BASE + path, headers=actor, **({"json": body[target]} if target != "regenerate" else {}))
    expire(consent_backend, uid)
    before = write_counts(consent_backend)
    err(send(), 403, "CONSENT_REQUIRED")
    assert write_counts(consent_backend) == before
    assert client.get(BASE + "/consents", headers=actor).status_code == 200
    assert client.get(BASE + f"/organizations/{seed.ORG}/posts", headers=actor).status_code == 200
    assert client.get(BASE + f"/requests/{seed.REQUEST_COUGH}", headers=parent).status_code == 200
    assert agree(client, actor, role).status_code == 200
    response = send()
    assert response.status_code == {"request": 202, "message": 201, "draft": 202,
                                     "regenerate": 202, "class": 201, "org": 201}[target], response.text


def test_scope_and_role_are_checked_before_consent_and_upload_body(client, parent, teacher, consent_backend):
    expire(consent_backend, seed.PARENT)
    expire(consent_backend, seed.TEACHER)
    err(client.post(BASE + f"/organizations/{seed.ORG}/posts", headers=parent, content=b"bad body"),
        403, "CONSENT_REQUIRED")
    err(client.post(BASE + f"/classrooms/{seed.CLASS_STAR}/posts", headers=teacher, content=b"bad body"),
        403, "FORBIDDEN")
    err(client.post(BASE + f"/organizations/{uuid4()}/posts", headers=parent, content=b"bad body"), 404, "NOT_FOUND")
    err(client.post(BASE + f"/requests/{seed.REQUEST_PICKUP}/messages", headers=parent,
                    json={"body": "[TEST] 남의 요청"}), 404, "NOT_FOUND")


def test_classroom_permissions_and_guardian_counts(client, parent, teacher, teacher_other, director, consent_backend):
    path = BASE + f"/classrooms/{seed.CLASS_STAR}/consents"
    first = client.get(path, headers=teacher).json()
    assert len(first["items"]) == 20 and client.get(path, headers=director).json() == first
    for actor in (parent, teacher_other):
        err(client.get(path, headers=actor), 403, "FORBIDDEN_ROLE")
    err(client.get(BASE + f"/classrooms/{uuid4()}/consents", headers=director), 404, "NOT_FOUND")
    # 보호자 둘 중 하나만 완료한 아이와 연결된 보호자가 없는 아이도 세요.
    expire(consent_backend, seed.PARENT)
    incomplete = next(r for r in client.get(path, headers=teacher).json()["items"] if r["child_id"] == str(seed.CHILD))
    assert (incomplete["guardians_total"], incomplete["guardians_complete"], incomplete["complete"]) == (1, 0, False)
    if consent_backend == "mock":
        store.state().children[seed.CHILD].guardian_ids.append(seed.PARENT_OTHER)
        store.state().children[seed.demo_id("503")].guardian_ids.clear()
    else:
        with transaction() as connection:
            connection.execute(text("INSERT INTO child_guardians(org_id,child_id,user_id,relation) VALUES (:org,:child,:user,'other')"),
                               {"org": seed.ORG, "child": seed.CHILD, "user": seed.PARENT_OTHER})
            connection.execute(text("DELETE FROM child_guardians WHERE child_id=:id"), {"id": seed.demo_id("503")})
    rows = {r["child_id"]: r for r in client.get(path, headers=teacher).json()["items"]}
    assert (rows[str(seed.CHILD)]["guardians_total"], rows[str(seed.CHILD)]["guardians_complete"],
            rows[str(seed.CHILD)]["complete"]) == (2, 1, True)
    assert (rows[str(seed.demo_id("503"))]["guardians_total"], rows[str(seed.demo_id("503"))]["complete"]) == (0, False)


def test_consent_apis_require_login(client):
    err(client.get(BASE + "/consents"), 401, "UNAUTHENTICATED")
    err(agree(client, {}), 401, "UNAUTHENTICATED")
