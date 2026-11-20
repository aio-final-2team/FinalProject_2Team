"""계정 유무·활성 여부와 무관하게 argon2 verify를 한 번 실행한다."""

from unittest.mock import Mock
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from app.core import users
from app.mock import seed


@pytest.mark.parametrize("case", ["missing", "inactive", "wrong_password", "success"])
def test_login_always_verifies_one_argon2_hash(seeded_db, monkeypatch, case):
    if case == "inactive":
        with seeded_db.begin() as connection:
            connection.execute(text("UPDATE users SET is_active=false WHERE id=:id"), {"id": seed.TEACHER})
    stored_hash = users.get_user(seed.TEACHER).password_hash
    verify = Mock(wraps=users._passwords.verify)
    monkeypatch.setattr(users, "_passwords", SimpleNamespace(verify=verify))
    password = "wrong" if case == "wrong_password" else seed.DEMO_PASSWORD
    result = users.authenticate("missing" if case == "missing" else "teacher01", password)
    verify.assert_called_once()
    checked_hash, checked_password = verify.call_args.args
    assert checked_password == password and checked_hash.startswith("$argon2id$")
    if case in ("missing", "inactive"):
        assert checked_hash != stored_hash
    else:
        assert checked_hash == stored_hash
    assert (result is not None) is (case == "success")
    if result is not None:
        assert result.id == seed.TEACHER


@pytest.mark.parametrize("login_id", ["missing", "teacher01"])
def test_dummy_hash_success_still_cannot_authenticate(seeded_db, monkeypatch, login_id):
    with seeded_db.begin() as connection:
        connection.execute(text("UPDATE users SET is_active=false WHERE id=:id"), {"id": seed.TEACHER})
    verify = Mock(return_value=True)
    monkeypatch.setattr(users, "_passwords", SimpleNamespace(verify=verify))
    assert users.authenticate(login_id, seed.DEMO_PASSWORD) is None
    verify.assert_called_once()
