"""DB 계정과 내 정보. 표 정의는 DDL에만 두고 SQL 결과를 읽는다."""

from dataclasses import dataclass
from datetime import date, datetime
from secrets import token_urlsafe
from types import SimpleNamespace
from uuid import UUID

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import text

from app.core.db import transaction
from app.core.schedule import KST

_passwords = PasswordHasher()
_DUMMY_PASSWORD_HASH = _passwords.hash(token_urlsafe(32))


@dataclass(frozen=True)
class User:
    id: UUID
    org_id: UUID
    role: str
    login_id: str
    display_name: str
    password_hash: str
    token_version: int
    is_active: bool


def _user(row):
    return User(**{name: row[name] for name in User.__dataclass_fields__}) if row else None


def get_user(user_id: UUID) -> User | None:
    with transaction() as connection:
        return _user(connection.execute(text("SELECT * FROM users WHERE id=:id"),
                                        {"id": user_id}).mappings().one_or_none())


def authenticate(login_id: str, password: str) -> User | None:
    with transaction() as connection:
        user = _user(connection.execute(text("SELECT * FROM users WHERE login_id=:login_id"),
                                        {"login_id": login_id}).mappings().one_or_none())
    active = user is not None and user.is_active
    password_hash = user.password_hash if active else _DUMMY_PASSWORD_HASH
    try:
        _passwords.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return None
    return user if active else None


def classroom_ids_of(teacher_id: UUID, on: date | None = None) -> list[UUID]:
    with transaction() as connection:
        return list(connection.scalars(text("""
            SELECT s.classroom_id FROM classroom_staff s
            JOIN users u ON (u.id, u.org_id)=(s.user_id, s.org_id)
            WHERE u.id=:id AND u.role='teacher' AND u.is_active
              AND (s.valid_from IS NULL OR s.valid_from<=:on)
              AND (s.valid_to IS NULL OR s.valid_to>=:on)
            ORDER BY s.classroom_id
        """), {"id": teacher_id, "on": on or datetime.now(KST).date()}))


def children_of(parent_id: UUID) -> list[SimpleNamespace]:
    with transaction() as connection:
        rows = connection.execute(text("""
            SELECT c.id, c.display_name, c.classroom_id FROM children c
            JOIN child_guardians g ON (g.child_id, g.org_id)=(c.id, c.org_id)
            JOIN users u ON (u.id, u.org_id)=(g.user_id, g.org_id)
            WHERE u.id=:id AND u.role='parent' AND u.is_active ORDER BY c.id
        """), {"id": parent_id}).mappings()
        return [SimpleNamespace(**row) for row in rows]
