"""상대 날짜 시드와 실제 상담 후보·확정의 연결을 검증해요."""

from datetime import datetime, timedelta

from sqlalchemy import text

from app.core.schedule import KST, working_day
from app.mock import seed
from app.modules.consultations.slots import find_consult_slots
from db.seeds.demo import seed_demo
from tests.integration.db.test_cards import BASE, auth, create


def test_two_week_seed_is_idempotent_and_consult_slots_avoid_class_and_duty(seeded_db):
    today = datetime.now(KST).date()
    with seeded_db.begin() as connection:
        before = connection.execute(text("SELECT * FROM staff_busy_blocks ORDER BY id")).all()
        seed_demo(connection)
        assert connection.execute(text("SELECT * FROM staff_busy_blocks ORDER BY id")).all() == before
        assert len(before) == 40
        for block in seed.demo_busy_blocks(today):
            period = block["period"]
            candidates = find_consult_slots(connection, block["user_id"], period["start"].date(), org_id=seed.ORG,
                now=datetime.combine(today-timedelta(days=1), datetime.min.time(), KST),
                preferred_times=period["start"].strftime("%H:%M"))
            assert bool(candidates) == working_day(period["start"].date())
            assert all(c["end"] <= period["start"] or period["end"] <= c["start"] for c in candidates)


def test_new_busy_block_invalidates_previously_chosen_candidate(db_client, monkeypatch):
    from app import backend
    from app.modules.consultations import busy_blocks
    monkeypatch.setattr(backend, "busy_blocks", busy_blocks)
    rid, cid = create(db_client, "consultation")
    slot = db_client.get(f"{BASE}/requests/{rid}", headers=auth(seed.PARENT)).json()["consultation"]["slots"][0]
    assert db_client.post(f"{BASE}/requests/{rid}/slot-choices", headers=auth(seed.PARENT),
                          json={"slot_ids": [slot["id"]]}).status_code == 200
    response = db_client.post(BASE+"/staff/busy-blocks", headers=auth(seed.TEACHER),
        json={"start_at": slot["period"]["start"], "end_at": slot["period"]["end"], "kind": "other"})
    assert response.status_code == 201, response.text
    response = db_client.post(f"{BASE}/cards/{cid}/bookings", headers=auth(seed.TEACHER),
                             json={"version": 1, "slot_id": slot["id"]})
    assert response.status_code == 409 and response.json()["error"]["code"] == "SLOT_TAKEN"
