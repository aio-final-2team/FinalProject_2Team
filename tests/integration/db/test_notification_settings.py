"""[TEST] 개인 설정의 마이그레이션·알림 저장·발송 재계산을 확인해요."""

from datetime import datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core import users
from app.core.schedule import KST
from app.api.schemas.notification_settings import NotificationSettings
from app.mock import seed
from app.modules.notifications import settings, delivery
from app.modules.notifications.notifications import enqueue


def test_enqueue_and_delivery_recheck_recipient_settings(seeded_db):
    user = users.get_user(seed.TEACHER)
    night = datetime(2026, 12, 4, 23, tzinfo=KST)
    settings.save(user, NotificationSettings(quiet_start="22:00", quiet_end="07:00"))
    with seeded_db.begin() as connection:
        enqueue(connection, {"id": 999, "org_id": seed.ORG, "card_id": None, "created_at": night},
                None, user.id, "new_card")
        row = connection.execute(text("SELECT * FROM notifications")).mappings().one()
        assert row["deliver_after"] == datetime(2026, 12, 7, 7, tzinfo=KST)
        connection.execute(text("UPDATE notifications SET deliver_after=:now,next_attempt_at=:now"), {"now": night})
    assert delivery.deliver_pending(night) == 0
    with seeded_db.connect() as connection:
        assert connection.scalar(text("SELECT next_attempt_at FROM notifications")) == row["deliver_after"]
    assert delivery.deliver_pending(row["deliver_after"]) == 1


def test_notification_settings_rejects_user_from_another_org(seeded_db):
    with seeded_db.begin() as connection:
        other_org = connection.scalar(text("INSERT INTO organizations(name) VALUES ('[TEST] 다른 기관') RETURNING id"))
        statement = text("INSERT INTO user_settings(user_id,org_id) VALUES (:user,:org)")
        with pytest.raises(IntegrityError) as error, connection.begin_nested():
            connection.execute(statement, {"user": seed.TEACHER, "org": other_org})
        assert error.value.orig.sqlstate == "23503"
        assert error.value.orig.diag.constraint_name == "user_settings_user_id_org_id_fkey"
        connection.execute(statement, {"user": seed.TEACHER, "org": seed.ORG})
        assert connection.scalar(text("SELECT org_id FROM user_settings WHERE user_id=:user"),
                                 {"user": seed.TEACHER}) == seed.ORG
