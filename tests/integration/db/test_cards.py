"""결정의 원자성·DB 제약·받은함 뷰와 교직원 상세의 읽기 경계를 확인해요."""

import json
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core import users
from app.core.auth import issue_token
from app.core.schedule import KST
from app.mock import seed

BASE = "/api/v1"


def auth(user_id):
    return {"Authorization": "Bearer " + issue_token(users.get_user(user_id))}


def create(client, kind="complaint"):
    response = client.post(
        BASE + "/requests",
        headers=auth(seed.PARENT),
        json={"client_request_id": str(uuid4()), "type": kind, "body": "[TEST] 일반 요청", "child_id": str(seed.CHILD)},
    )
    assert response.status_code == 202, response.text
    rid = response.json()["request"]["id"]
    cards = client.get(BASE + "/cards?size=100", headers=auth(seed.TEACHER)).json()["items"]
    return rid, next(c["id"] for c in cards if c["request_id"] == rid)


def test_approvals_trigger_and_unique_constraint_block_invalid_direct_sql(db_client, seeded_db):
    rid, cid = create(db_client)
    values = {"org": seed.ORG, "card": cid, "user": seed.TEACHER}
    statement = """INSERT INTO approvals (org_id,card_id,card_version,decided_by,decision,reason_text)
        VALUES (:org,:card,1,:user,'complete',:reason)"""
    with seeded_db.begin() as connection:
        with pytest.raises(IntegrityError) as failure, connection.begin_nested():
            connection.execute(text(statement), {**values, "reason": None})
        assert failure.value.orig.sqlstate == "23514"
        connection.execute(text(statement), {**values, "reason": "[TEST] 전화 설명"})
        with pytest.raises(IntegrityError) as failure, connection.begin_nested():
            connection.execute(text(statement), {**values, "reason": "[TEST] 재시도"})
        assert failure.value.orig.sqlstate == "23505"
        assert failure.value.orig.diag.constraint_name == "approvals_card_id_card_version_key"


def test_notification_failure_rolls_back_decision_message_status_and_event(db_client, seeded_db, monkeypatch):
    from app.modules.requests import events

    rid, cid = create(db_client)
    with seeded_db.connect() as connection:
        before = {
            table: connection.scalar(text(f"SELECT count(*) FROM {table}"))
            for table in ("events", "approvals", "request_messages", "notifications")
        }

    def failed(*args):
        raise RuntimeError("[TEST] 알림 저장 실패")

    monkeypatch.setattr(events, "notify_event", failed)
    response = db_client.post(f'{BASE}/cards/{cid}/decisions', headers=auth(seed.TEACHER),
                              json={'version': 1, 'decision': 'approve'})
    assert response.status_code == 500 and response.json()['error']['code'] == 'INTERNAL_ERROR'
    with seeded_db.connect() as connection:
        after = {table: connection.scalar(text(f"SELECT count(*) FROM {table}")) for table in before}
        assert after == before
        assert connection.scalar(text("SELECT status FROM requests WHERE id=:id"), {"id": rid}) == "awaiting_review"
        assert connection.execute(text("SELECT status,version FROM cards WHERE id=:id"), {"id": cid}).one() == (
            "pending",
            1,
        )


def test_view_migration_roundtrip_preserves_rows_and_complaint_inbox(db_client, seeded_db, alembic_config):
    rid, cid = create(db_client)
    response = db_client.post(
        f"{BASE}/cards/{cid}/decisions", headers=auth(seed.TEACHER), json={"version": 1, "decision": "approve"}
    )
    assert response.status_code == 200, response.text

    def bucket():
        with seeded_db.connect() as connection:
            return connection.scalar(text("SELECT inbox_filter FROM staff_inbox WHERE card_id=:id"), {"id": cid})

    assert bucket() == "in_progress"
    command.downgrade(alembic_config, "0003")
    assert bucket() == "done"
    command.upgrade(alembic_config, "head")
    assert bucket() == "in_progress"
    with seeded_db.begin() as connection:
        connection.execute(text("UPDATE requests SET parent_confirmed_at=now() WHERE id=:id"), {"id": rid})
    assert bucket() == "needs_review"
    with seeded_db.begin() as connection:
        connection.execute(text("UPDATE requests SET status='completed' WHERE id=:id"), {"id": rid})
    assert bucket() == "done"


def test_automatic_hold_expiry_on_list_is_once_and_no_human_approval(db_client, seeded_db):
    rid, cid = create(db_client)
    tomorrow = (datetime.now(KST).date() + timedelta(days=1)).isoformat()
    response = db_client.post(
        f"{BASE}/cards/{cid}/decisions",
        headers=auth(seed.TEACHER),
        json={"version": 1, "decision": "hold", "reason_text": "[TEST] 확인 중", "hold_until": tomorrow},
    )
    assert response.status_code == 200, response.text
    with seeded_db.begin() as connection:
        connection.execute(text("UPDATE cards SET hold_until=CURRENT_DATE WHERE id=:id"), {"id": cid})
    for _ in range(2):
        assert db_client.get(BASE + "/cards", headers=auth(seed.TEACHER)).status_code == 200
    with seeded_db.connect() as connection:
        assert connection.execute(
            text("SELECT status,version,hold_until FROM cards WHERE id=:id"), {"id": cid}
        ).one() == ("pending", 3, None)
        assert connection.scalar(text("SELECT count(*) FROM approvals WHERE card_id=:id"), {"id": cid}) == 1
        events = (
            connection.execute(text("SELECT * FROM events WHERE request_id=:id AND action='resumed'"), {"id": rid})
            .mappings()
            .all()
        )
        assert len(events) == 1 and events[0]["actor_type"] == "system" and events[0]["detail"]["automatic"]
        assert (
            connection.scalar(
                text("SELECT count(*) FROM notifications WHERE request_id=:id AND kind='hold_resumed'"), {"id": rid}
            )
            == 1
        )


def test_overview_reads_view_and_eval_and_empty_organization(db_client, seeded_db):
    with seeded_db.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO eval_runs (suite,requested_model,total,passed,started_at) VALUES ('service','[TEST] model',3,2,now())"
            )
        )
    response = db_client.get(BASE + "/overview", headers=auth(seed.DIRECTOR))
    assert response.status_code == 200, response.text
    assert {
        k: response.json()[k] for k in ("unassigned", "waiting", "delayed", "done_today", "completed_unconfirmed")
    } == dict.fromkeys(("unassigned", "waiting", "delayed", "done_today", "completed_unconfirmed"), 0)
    assert response.json()["eval"][0]["passed"] == 2


def test_evidence_staleness_warnings_and_parent_sources(db_client, seeded_db):
    rid, cid = create(db_client, "inquiry")
    with seeded_db.begin() as connection:
        connection.execute(
            text("""INSERT INTO card_evidence (card_id,org_id,chunk_id,rank,quote)
            SELECT :card,org_id,id,1,'[TEST] 옛 자료 인용' FROM document_chunks WHERE document_id=:doc"""),
            {"card": cid, "doc": seed.OLD_NOTICE},
        )
        connection.execute(
            text("""UPDATE cards SET draft=CAST(:draft AS jsonb),check_result=NULL WHERE id=:id"""),
            {"id": cid, "draft": json.dumps({"text": "[TEST] 회신", "law_unchecked": True, "notify_failed": True})},
        )
    response = db_client.get(f"{BASE}/cards/{cid}", headers=auth(seed.TEACHER))
    assert response.status_code == 200, response.text
    saved = response.json()
    assert set(saved["warnings"]) == {"stale_evidence", "law_unchecked", "check_unavailable", "notify_failed"}
    assert saved["evidence"][0]["is_current"] is False and saved["evidence"][0]["quote"] == "[TEST] 옛 자료 인용"
    assert (
        db_client.post(
            f"{BASE}/cards/{cid}/decisions", headers=auth(seed.TEACHER), json={"version": 1, "decision": "approve"}
        ).status_code
        == 200
    )
    assert db_client.get(f"{BASE}/requests/{rid}", headers=auth(seed.PARENT)).json()["sources"]
    with seeded_db.begin() as connection:
        connection.execute(text("UPDATE documents SET visibility='staff' WHERE id=:id"), {"id": seed.OLD_NOTICE})
    assert db_client.get(f"{BASE}/requests/{rid}", headers=auth(seed.PARENT)).json()["sources"] == []


def test_unassigned_card_reassign_and_cards_without_request(db_client, seeded_db):
    from app.modules.requests.runner import sweep_missing_cards

    with seeded_db.begin() as connection:
        rid = connection.scalar(
            text("""INSERT INTO requests (org_id,classroom_id,child_id,requester_id,client_request_id,type,body,created_at)
            VALUES (:org,:class,:child,:parent,:key,'inquiry','[TEST] 누락',now()-interval '10 minutes') RETURNING id"""),
            {
                "org": seed.ORG,
                "class": seed.CLASS_STAR,
                "child": seed.CHILD,
                "parent": seed.PARENT,
                "key": str(uuid4()),
            },
        )
    sweep_missing_cards(datetime.now(KST))
    with seeded_db.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM cards c JOIN requests r ON r.id=c.request_id WHERE r.type IN ('medication','pickup')")) == 0
    rows = db_client.get(BASE + "/cards?filter=unassigned&size=100", headers=auth(seed.DIRECTOR)).json()["items"]
    cid = next(c["id"] for c in rows if c["request_id"] == str(rid))
    result = db_client.post(
        f"{BASE}/cards/{cid}/reassign",
        headers=auth(seed.DIRECTOR),
        json={"assignee_id": str(seed.TEACHER_OTHER), "reason": "[TEST] 수동 인계"},
    )
    assert result.status_code == 200, result.text
    assert db_client.get(f"{BASE}/cards/{cid}", headers=auth(seed.TEACHER_OTHER)).json()["card"]["status"] == "pending"
    response = db_client.post(
        BASE + "/daily-notes/drafts",
        headers=auth(seed.TEACHER),
        json={
            "classroom_id": str(seed.CLASS_STAR),
            "note_date": datetime.now(KST).date().isoformat(),
            "activities": "[TEST] 활동",
            "supplies": "",
        },
    )
    assert response.status_code == 202, response.text
    with seeded_db.connect() as connection:
        card = connection.scalar(text("SELECT id FROM cards WHERE subject_type='daily_note_batch'"))
    saved = db_client.get(f"{BASE}/cards/{card}", headers=auth(seed.TEACHER))
    assert saved.status_code == 200 and saved.json()["request"] is None
    stream = db_client.get(f"{BASE}/cards/{card}/stream", headers=auth(seed.TEACHER))
    assert stream.status_code == 200 and '"request_status": null' in stream.text
    assert db_client.get(BASE + "/cards", headers=auth(seed.TEACHER)).status_code == 200


@pytest.mark.parametrize("target", [seed.PARENT, seed.DIRECTOR, uuid4()])
def test_invalid_reassignment_target_is_404_and_does_not_change_card(db_client, seeded_db, target):
    _, cid = create(db_client)
    result = db_client.post(
        f"{BASE}/cards/{cid}/reassign",
        headers=auth(seed.DIRECTOR),
        json={"assignee_id": str(target), "reason": "[TEST] 배정"},
    )
    assert result.status_code == 404, result.text
    with seeded_db.connect() as connection:
        assert connection.execute(text("SELECT assignee_id,version FROM cards WHERE id=:id"), {"id": cid}).one() == (
            seed.TEACHER,
            1,
        )
