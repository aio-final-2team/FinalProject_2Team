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
from app.core.photos import profile_view
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


def teachers_of(org_id: UUID, on: date | None = None) -> list[dict]:
    """같은 기관의 활성 선생님과 오늘 맡은 반(70번 API). 연락처·로그인 ID는 넣지 않아요."""
    with transaction() as connection:
        rows = connection.execute(text("""
            SELECT u.id, u.display_name,
                   coalesce(json_agg(json_build_object('id', c.id, 'name', c.name) ORDER BY c.name COLLATE "C", c.id)
                            FILTER (WHERE c.id IS NOT NULL), CAST('[]' AS json)) AS classrooms
            FROM users u
            LEFT JOIN classroom_staff s ON (s.user_id, s.org_id)=(u.id, u.org_id)
              AND (s.valid_from IS NULL OR s.valid_from<=:on)
              AND (s.valid_to IS NULL OR s.valid_to>=:on)
            LEFT JOIN classrooms c ON (c.id, c.org_id)=(s.classroom_id, s.org_id)
            WHERE u.org_id=:org AND u.role='teacher' AND u.is_active
            GROUP BY u.id, u.display_name
            ORDER BY u.display_name COLLATE "C", u.id
        """), {"org": org_id, "on": on or datetime.now(KST).date()}).mappings()
        return [dict(row) for row in rows]


def children_of(parent_id: UUID) -> list[SimpleNamespace]:
    with transaction() as connection:
        rows = connection.execute(text("""
            SELECT c.id, c.display_name, c.classroom_id, c.profile_photo_path FROM children c
            JOIN child_guardians g ON (g.child_id, g.org_id)=(c.id, c.org_id)
            JOIN users u ON (u.id, u.org_id)=(g.user_id, g.org_id)
            WHERE u.id=:id AND u.role='parent' AND u.is_active ORDER BY c.id
        """), {"id": parent_id}).mappings()
        return [SimpleNamespace(**{key: value for key, value in row.items() if key != "profile_photo_path"},
                                profile_photo=profile_view(row["id"], row["profile_photo_path"])) for row in rows]
