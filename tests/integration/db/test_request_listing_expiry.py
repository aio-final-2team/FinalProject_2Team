"""[TEST] 요청 목록은 만료될 요청만 골라 처리해요(요청마다 만료 조회를 하지 않음)."""

from sqlalchemy import text

from app.mock import seed
from app.modules.requests import requests
from tests.integration.db.test_cards import BASE, auth, create


def test_listing_expires_only_due_requests(db_client, seeded_db, monkeypatch):
    rid, _ = create(db_client)
    other, _ = create(db_client)
    calls = []
    original = requests._expire
    monkeypatch.setattr(requests, "_expire", lambda connection, req: calls.append(req["id"]) or original(connection, req))
    for user in (seed.TEACHER, seed.DIRECTOR, seed.PARENT):
        assert db_client.get(BASE + "/requests?size=100", headers=auth(user)).status_code == 200
    assert calls == []
    with seeded_db.begin() as connection:
        connection.execute(text("""
            UPDATE cards SET status='on_hold',hold_until=CURRENT_DATE-1 WHERE request_id=:id
        """), {"id": rid})
    response = db_client.get(BASE + "/requests?size=100", headers=auth(seed.TEACHER))
    assert response.status_code == 200
    assert [str(i) for i in calls] == [rid]
    with seeded_db.connect() as connection:
        assert connection.scalar(text("SELECT status FROM cards WHERE request_id=:id"), {"id": rid}) == "pending"
        assert connection.scalar(text("SELECT status FROM cards WHERE request_id=:id"), {"id": other}) != "on_hold"
    calls.clear()
    assert db_client.get(BASE + "/requests?size=100", headers=auth(seed.PARENT)).status_code == 200
    assert calls == []
