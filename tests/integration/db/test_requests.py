"""T27-a: 저장 경계·동시 접수/확인·실패 인계·카드 누락 점검을 실제 PG로 확인해요."""

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta
from uuid import UUID, uuid4

import anyio
import pytest
from fastapi import BackgroundTasks
from sqlalchemy import text

from app.core import users
from app.core.schedule import KST
from app.mock import seed
from app.modules.requests import agent_stub, events, requests, runner, streams


@pytest.fixture
def parent(db_client):
    response = db_client.post("/api/v1/auth/login", json={"login_id": "parent01", "password": "demo1234"})
    assert response.status_code == 200, response.text
    return {"Authorization": "Bearer " + response.json()["access_token"]}


def create(db_client, parent, **over):
    payload = {"client_request_id": str(uuid4()), "type": "inquiry", "body": "[TEST] 식단 문의", "child_id": str(seed.CHILD)}
    payload.update(over)
    return db_client.post("/api/v1/requests", headers={**parent, "X-Request-ID": "request-trace"}, json=payload)


def rows(engine, table, request_id):
    with engine.connect() as connection:
        # 표는 이 파일의 고정 호출에서만 받아요.
        column = "id" if table == "requests" else "request_id"
        return [dict(row) for row in connection.execute(text(f"SELECT * FROM {table} WHERE {column}=:id ORDER BY id"),
                                                        {"id": request_id}).mappings()]


def test_saved_before_background_dispatch_and_event_order(seeded_db):
    tasks = BackgroundTasks()
    req, created = requests.create(users.get_user(seed.PARENT), background_tasks=tasks, client_request_id=str(uuid4()),
                                   type="inquiry", body="[TEST] 식단 문의", child_id=seed.CHILD,
                                   previous_request_id=None, trace_id="before-dispatch")
    assert created and req["status"] == "received"
    assert rows(seeded_db, "requests", req["id"])[0]["status"] == "received"
    assert len(rows(seeded_db, "request_messages", req["id"])) == 1
    assert rows(seeded_db, "cards", req["id"]) == []
    assert len(tasks.tasks) == 1
    anyio.run(tasks)
    history = rows(seeded_db, "events", req["id"])
    assert [e["action"] for e in history] == ["created", "classified", "assigned", "created", "drafted", "checked"]
    assert [(e["from_status"], e["to_status"]) for e in history if e["to_status"]] == [
        (None, "received"), ("received", "classified"), ("classified", "assigned"), ("assigned", "awaiting_review")]
    assert history[0]["detail"]["trace_id"] == "before-dispatch"
    card = rows(seeded_db, "cards", req["id"])[0]
    assert card["draft"]["no_evidence"] is True and card["check_result"]["passed"] is True
    with seeded_db.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM card_evidence WHERE card_id=:id"), {"id": card["id"]}) == 0
    notices = rows(seeded_db, "notifications", req["id"])
    assert len(notices) == 1 and notices[0]["kind"] == "new_card" and notices[0]["status"] == "pending"
    assert notices[0]["dedupe_key"] == f"event:{history[-1]['id']}:{seed.TEACHER}"


def test_concurrent_same_key_creates_one_request_message_and_agent_run(db_client, parent, seeded_db):
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: create(db_client, parent, client_request_id="same-concurrent-key"), range(2)))
    assert sorted(r.status_code for r in responses) == [200, 202]
    ids = {r.json()["request"]["id"] for r in responses}
    assert len(ids) == 1
    rid = ids.pop()
    assert len(rows(seeded_db, "request_messages", rid)) == 1 and len(rows(seeded_db, "cards", rid)) == 1
    assert sum(e["action"] == "classified" for e in rows(seeded_db, "events", rid)) == 1


@pytest.mark.parametrize("prepared", [False, True])
def test_out_of_scope_model_notice_skips_draft_and_duplicate_workers(seeded_db, monkeypatch, prepared):
    from app.modules.requests.supervisor import validate_proposal

    body = "[TEST] 대신 송금해 줄 수 있나요?"
    req, _ = requests.create(users.get_user(seed.PARENT), background_tasks=BackgroundTasks(),
                             client_request_id=str(uuid4()), type="inquiry", body=body, child_id=seed.CHILD,
                             previous_request_id=None, trace_id="scope-model")
    proposal = {"out_of_scope_kind": "payment"}
    fields = validate_proposal("inquiry", body, proposal)
    assert fields["out_of_scope_kind"] == "payment"
    monkeypatch.setattr(agent_stub, "classify_request", lambda *args: proposal)

    def no_draft(*args, **kwargs):
        pytest.fail("[TEST] 고정 안내에 자료·검사 AI나 공공 조회를 호출하면 안 돼요")

    monkeypatch.setattr(agent_stub, "prefetch_public", no_draft)
    monkeypatch.setattr(agent_stub, "draft_outside_lock", no_draft)
    args = {"prepared_fields": fields, "prepared_answer": {"text": "[TEST] 내보내면 안 되는 초안"}} if prepared else {}
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: agent_stub.run_request(req["id"], **args), range(2)))
    agent_stub.run_request(req["id"], **args)
    assert rows(seeded_db, "requests", req["id"])[0]["status"] == "sent_or_booked"
    assert rows(seeded_db, "cards", req["id"]) == []
    messages = rows(seeded_db, "request_messages", req["id"])
    assert len(messages) == 2 and messages[-1]["sender_type"] == "agent" and messages[-1]["sender_id"] is None
    assert messages[-1]["body"] == "유치온에서는 원비 결제를 하지 않아요. 원비는 원에서 안내한 기존 방법으로 문의해 주세요."
    history = rows(seeded_db, "events", req["id"])
    assert [e["action"] for e in history] == ["created", "classified", "assigned", "out_of_scope_answered"]
    assert history[-1]["detail"]["kind"] == "payment"
    notifications = rows(seeded_db, "notifications", req["id"])
    assert len(notifications) == 1 and notifications[0]["kind"] == "sent_or_booked"
    assert notifications[0]["recipient_id"] == seed.PARENT and notifications[0]["card_id"] is None


def test_out_of_scope_notice_state_failure_rolls_back_message_and_notification(seeded_db, monkeypatch):
    req, _ = requests.create(users.get_user(seed.PARENT), background_tasks=BackgroundTasks(),
                             client_request_id=str(uuid4()), type="inquiry", body="[TEST] 원비 결제해 주세요.",
                             child_id=seed.CHILD, previous_request_id=None, trace_id="scope-rollback")
    before = {table: rows(seeded_db, table, req["id"])
              for table in ("requests", "request_messages", "events", "notifications", "cards")}
    original = agent_stub.set_status

    def fail_notice(connection, req, status, **kwargs):
        if kwargs["action"] == "out_of_scope_answered":
            original(connection, req, status, **kwargs)
            raise RuntimeError("[TEST] 안내 상태·알림 저장 뒤 실패")
        return original(connection, req, status, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(agent_stub, "set_status", fail_notice)
        with pytest.raises(RuntimeError, match=r"\[TEST\]"):
            agent_stub.run_request(req["id"])
    assert before == {table: rows(seeded_db, table, req["id"]) for table in before}
    agent_stub.run_request(req["id"])
    assert rows(seeded_db, "requests", req["id"])[0]["status"] == "sent_or_booked"
    assert len(rows(seeded_db, "request_messages", req["id"])) == 2
    assert len(rows(seeded_db, "notifications", req["id"])) == 1


def test_concurrent_confirmation_keeps_one_timestamp_event_and_notice(db_client, parent, seeded_db):
    rid = create(db_client, parent, type="complaint").json()["request"]["id"]
    with seeded_db.begin() as connection:
        connection.execute(text("UPDATE requests SET status='sent_or_booked' WHERE id=:id"), {"id": rid})
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: db_client.post(f"/api/v1/requests/{rid}/confirm", headers=parent), range(2)))
    assert all(r.status_code == 200 for r in responses) and responses[0].json() == responses[1].json()
    assert sum(e["action"] == "parent_confirmed" for e in rows(seeded_db, "events", rid)) == 1
    assert sum(n["kind"] == "parent_confirmed" for n in rows(seeded_db, "notifications", rid)) == 1


def test_message_failure_rolls_back_message_event_and_timestamp(db_client, parent, seeded_db, monkeypatch):
    rid = create(db_client, parent).json()["request"]["id"]
    before = {table: rows(seeded_db, table, rid) for table in ("requests", "events", "request_messages")}
    def fail(*args, **kwargs):
        raise RuntimeError("[TEST] 저장 중 실패")
    monkeypatch.setattr(requests, "record", fail)
    response = db_client.post(f"/api/v1/requests/{rid}/messages", headers=parent, json={"body": "[TEST] 저장하면 안 됨"})
    assert response.status_code == 500
    assert before == {table: rows(seeded_db, table, rid) for table in before}


@pytest.mark.parametrize("staff", ["active", "missing", "inactive", "expired", "future"])
def test_agent_failure_preserves_request_and_hands_off_without_private_error(
    db_client, parent, seeded_db, monkeypatch, staff
):
    with seeded_db.begin() as connection:
        if staff == "missing":
            connection.execute(text("DELETE FROM classroom_staff WHERE classroom_id=:id"), {"id": seed.CLASS_STAR})
        elif staff == "inactive":
            connection.execute(text("UPDATE users SET is_active=false WHERE id=:id"), {"id": seed.TEACHER})
        elif staff in ("expired", "future"):
            today = datetime.now(KST).date()
            connection.execute(text("""
                UPDATE classroom_staff SET valid_from=:start,valid_to=:end WHERE classroom_id=:id
            """), {"id": seed.CLASS_STAR, "start": today+timedelta(days=1) if staff == "future" else None,
                   "end": today-timedelta(days=1) if staff == "expired" else None})
    monkeypatch.setattr(runner, "settings", replace(runner.settings, request_agent="missing_private_module:run"))
    response = create(db_client, parent)
    assert response.status_code == 202
    rid = response.json()["request"]["id"]
    req = rows(seeded_db, "requests", rid)[0]
    teacher = seed.TEACHER if staff == "active" else None
    assert req["status"] == "awaiting_review" and req["assignee_id"] == teacher
    assert (req["topic_key"], req["urgency"], req["risk_level"], req["risk_category"]) == ("meal", "normal", "normal", None)
    card = rows(seeded_db, "cards", rid)[0]
    assert card["status"] == ("pending" if teacher else "unassigned")
    assert card["assignee_id"] == teacher and card["draft"] == {} and card["check_result"] is None
    history = rows(seeded_db, "events", rid)
    assert any(e["detail"].get("handoff_reason") == "ai_failed" for e in history)
    assert "missing_private_module" not in str(history)
    detail = db_client.get(f"/api/v1/requests/{rid}", headers=parent)
    assert detail.status_code == 200 and "ai_failed" not in detail.text
    assert detail.json()["request"]["status_label"] == ("선생님 확인 중" if teacher else "담당 선생님 배정 중")
    assert len(rows(seeded_db, "request_messages", rid)) == 1
    notices = rows(seeded_db, "notifications", rid)
    assert len(notices) == 1 and notices[0]["recipient_id"] == (teacher or seed.DIRECTOR)
    assert notices[0]["kind"] == "new_card" and notices[0]["card_id"] == card["id"]
    runner.run_request(UUID(rid))
    assert rows(seeded_db, "notifications", rid) == notices


@pytest.mark.parametrize("body,risk", [("[TEST] 상담하고 싶어요", "normal"), ("[TEST] 아이가 다쳤어요 상담", "urgent")])
def test_consultation_handoff_keeps_slot_flow_and_adds_report_only_for_risk(seeded_db, monkeypatch, body, risk):
    req, _ = requests.create(users.get_user(seed.PARENT), background_tasks=BackgroundTasks(),
                             client_request_id=str(uuid4()), type="consultation", body=body, child_id=seed.CHILD,
                             previous_request_id=None, trace_id="[TEST]-consult-handoff")
    rid = req["id"]

    def fail(*args):
        raise RuntimeError("[TEST] private model failure")
    monkeypatch.setattr(agent_stub, "classify_request", fail)
    runner.run_request(rid)
    saved = rows(seeded_db, "requests", rid)[0]
    # 상담은 AI가 실패해도 시간 고르기 흐름으로 넘겨요. 회신 카드로 넘기면 원장 지시·예약 알림이 막혀요.
    assert saved["status"] == "needs_info" and saved["assignee_id"] == seed.TEACHER and saved["risk_level"] == risk
    cards = {c["kind"]: c for c in rows(seeded_db, "cards", rid)}
    assert set(cards) == ({"consult_slots", "director_report"} if risk == "urgent" else {"consult_slots"})
    with seeded_db.connect() as connection:
        assert connection.scalar(text("""
            SELECT count(*) FROM consultation_slots WHERE card_id=:id AND status='proposed'
        """), {"id": cards["consult_slots"]["id"]}) >= 1
    history = rows(seeded_db, "events", rid)
    moved = [e for e in history if e["to_status"] and e["detail"].get("handoff_reason") == "ai_failed"]
    assert len(moved) == 1 and moved[0]["action"] == "info_requested"
    assert "private model failure" not in str(history)


def test_text_reply_on_consultation_without_booking_sends_plain_reply_notice(db_client, parent, seeded_db):
    """예전 인계로 남은 상담 회신 카드를 승인해도 예약 알림을 찾다 500이 나지 않아요."""
    req, _ = requests.create(users.get_user(seed.PARENT), background_tasks=BackgroundTasks(),
                             client_request_id=str(uuid4()), type="consultation", body="[TEST] 상담 글 회신",
                             child_id=seed.CHILD, previous_request_id=None, trace_id="[TEST]-consult-reply")
    rid = req["id"]
    with seeded_db.begin() as connection:
        row = dict(connection.execute(text("SELECT * FROM requests WHERE id=:id FOR UPDATE"), {"id": rid}).mappings().one())
        connection.execute(text("UPDATE requests SET assignee_id=:teacher WHERE id=:id"), {"id": rid, "teacher": seed.TEACHER})
        row["assignee_id"] = seed.TEACHER
        card = agent_stub.new_card(connection, row, "reply_draft", seed.TEACHER)
        events.set_status(connection, row, "awaiting_review", action="checked", card=card)
    login = db_client.post("/api/v1/auth/login", json={"login_id": "teacher01", "password": "demo1234"})
    teacher = {"Authorization": "Bearer " + login.json()["access_token"]}
    response = db_client.post(f"/api/v1/cards/{card['id']}/decisions", headers=teacher, json={
        "version": 1, "decision": "edit_approve", "edited_content": {"text": "[TEST] 글로 답해요"}})
    assert response.status_code == 200, response.text
    assert rows(seeded_db, "requests", rid)[0]["status"] == "sent_or_booked"
    sent = [n for n in rows(seeded_db, "notifications", rid) if n["recipient_id"] == seed.PARENT]
    assert [n["kind"] for n in sent] == ["sent_or_booked"]


@pytest.mark.parametrize("reason", ["ai_failed", "ai_timeout", "card_missing"])
@pytest.mark.parametrize("request_type,body,risk,has_teacher", [
    ("inquiry", "[TEST] 아이가 다쳤어요", "urgent", True),
    ("complaint", "[TEST] 아이가 다쳤어요", "urgent", True),
    ("inquiry", "[TEST] 판단 필요 문의예요", "uncertain", True),
    ("complaint", "[TEST] 판단 필요 민원이에요", "uncertain", True),
    ("inquiry", "[TEST] 식단 문의예요", "normal", True),
    ("complaint", "[TEST] 식단 민원이에요", "normal", True),
    ("inquiry", "[TEST] 아이가 다쳤어요", "urgent", False),
])
def test_handoff_keeps_code_risk_assignment_and_notifications(
    seeded_db, monkeypatch, reason, request_type, body, risk, has_teacher
):
    req, _ = requests.create(users.get_user(seed.PARENT), background_tasks=BackgroundTasks(),
                             client_request_id=str(uuid4()), type=request_type, body=body, child_id=seed.CHILD,
                             previous_request_id=None, trace_id="[TEST]-handoff")
    rid = req["id"]
    with seeded_db.begin() as connection:
        # 이미 저장된 분류가 있어도 인계 직전에 원문으로 다시 판단해요.
        connection.execute(text("""
            UPDATE requests SET topic_key='other',urgency='normal',risk_level='normal',risk_category=NULL WHERE id=:id
        """), {"id": rid})
        if not has_teacher:
            connection.execute(text("DELETE FROM classroom_staff WHERE classroom_id=:id"), {"id": seed.CLASS_STAR})
    if reason == "ai_failed":
        def fail(*args):
            raise RuntimeError("[TEST] private model failure")
        monkeypatch.setattr(agent_stub, "classify_request", fail)
        runner.run_request(rid)
    elif reason == "ai_timeout":
        monkeypatch.setattr(runner, "_start_agent", lambda _: Future())
        monkeypatch.setattr(runner, "AI_TIMEOUT_SECONDS", 0)
        runner.run_request(rid)
    else:
        monkeypatch.setattr(runner, "run_request", lambda _: None)
        now = datetime.now(KST)
        with seeded_db.begin() as connection:
            connection.execute(text("UPDATE requests SET created_at=:at WHERE id=:id"),
                               {"id": rid, "at": now-timedelta(minutes=6)})
        runner.sweep_missing_cards(now)
        runner.sweep_missing_cards(now+timedelta(minutes=5))
        runner.sweep_missing_cards(now+timedelta(minutes=10))
    saved = rows(seeded_db, "requests", rid)[0]
    high_risk = risk in ("urgent", "uncertain")
    teacher = seed.TEACHER if has_teacher else None
    assert saved["assignee_id"] == teacher and saved["risk_level"] == risk
    assert saved["topic_key"] == ("safety" if risk == "urgent" else "meal" if risk == "normal" else "other")
    assert saved["urgency"] == ("urgent" if risk == "urgent" else "normal")
    assert saved["risk_category"] == ("child_safety" if risk == "urgent" else None)
    assert saved["status"] == ("escalated" if high_risk else "awaiting_review")
    cards = {c["kind"]: c for c in rows(seeded_db, "cards", rid)}
    assert set(cards) == ({"reply_draft", "director_report"} if high_risk else {"reply_draft"})
    reply = cards["reply_draft"]
    assert reply["assignee_id"] == teacher and reply["status"] == ("pending" if teacher else "unassigned")
    assert reply["draft"] == {} and reply["check_result"] is None
    if high_risk:
        report = cards["director_report"]
        assert report["assignee_id"] == seed.DIRECTOR and report["status"] == "pending"
        assert not report["draft"].get("text") and report["check_result"] is None
        assert all(c["due_at"] == saved["created_at"]+timedelta(hours=2) for c in cards.values())
    history = rows(seeded_db, "events", rid)
    changes = [e for e in history if e["to_status"] and e["detail"].get("handoff_reason") == reason]
    assert len(changes) == 1 and changes[0]["action"] == ("escalated" if high_risk else "checked")
    if high_risk:
        assert changes[0]["detail"]["reason"] == "risk"
    assert "private model failure" not in str(history)
    assert len(rows(seeded_db, "request_messages", rid)) == 1
    notices = rows(seeded_db, "notifications", rid)
    if high_risk:
        kind = "urgent_complaint" if risk == "urgent" else "uncertain_complaint"
        recipients = {seed.DIRECTOR, teacher} - {None}
        assert len(notices) == len(recipients)
        assert {(n["recipient_id"], n["kind"], n["card_id"]) for n in notices} == {
            (recipient, kind, cards["director_report"]["id"]) for recipient in recipients}
        if risk == "urgent":
            assert all(n["deliver_after"] == n["created_at"] for n in notices)
    else:
        assert len(notices) == 1 and notices[0]["recipient_id"] == teacher and notices[0]["kind"] == "new_card"


def test_stub_transaction_rolls_back_then_handoff_once(db_client, parent, seeded_db, monkeypatch):
    def fail(*args):
        raise RuntimeError("[TEST] 분류 뒤 실패")
    monkeypatch.setattr(agent_stub, "propose_slots", fail)
    monkeypatch.setattr(runner, "propose_slots", fail)
    rid = create(db_client, parent, type="consultation").json()["request"]["id"]
    # 후보 계산까지 실패하면 인계는 글로 답하는 카드로 넘겨요.
    assert [e["action"] for e in rows(seeded_db, "events", rid)] == ["created", "tool_failed", "created", "checked"]
    assert [c["kind"] for c in rows(seeded_db, "cards", rid)] == ["reply_draft"]
    runner.run_request(UUID(rid))
    assert len(rows(seeded_db, "cards", rid)) == 1


def test_needs_info_inquiry_with_existing_card_can_be_reprocessed(db_client, parent, seeded_db, monkeypatch):
    rid = create(db_client, parent).json()["request"]["id"]
    calls = []
    monkeypatch.setattr(agent_stub, "classify_request", lambda *args: calls.append(args) or {})
    # 이미 카드가 있는 완료 요청은 모델에 보내지 않는다.
    agent_stub.run_request(UUID(rid))
    assert calls == []
    with seeded_db.begin() as connection:
        connection.execute(text("UPDATE requests SET status='needs_info' WHERE id=:id"), {"id": rid})
    agent_stub.run_request(UUID(rid))
    assert len(calls) == 1
    assert len(rows(seeded_db, "cards", rid)) == 2
    assert rows(seeded_db, "requests", rid)[0]["status"] == "awaiting_review"


def test_custom_entrypoint_is_selected(db_client, parent, seeded_db, monkeypatch):
    import sys
    from types import SimpleNamespace
    seen = []
    def custom(request_id):
        seen.append(request_id)
        agent_stub.run_request(request_id)
    monkeypatch.setitem(sys.modules, "test_request_entry", SimpleNamespace(run=custom))
    monkeypatch.setattr(runner, "settings", replace(runner.settings, request_agent="test_request_entry:run"))
    rid = create(db_client, parent).json()["request"]["id"]
    assert seen == [UUID(rid)] and rows(seeded_db, "requests", rid)[0]["status"] == "awaiting_review"


def test_sweep_exact_age_states_card_exclusion_and_concurrent_idempotency(seeded_db, monkeypatch):
    monkeypatch.setattr(runner, "run_request", lambda request_id: None)
    now = datetime.now(KST)
    ids = {}
    with seeded_db.begin() as connection:
        for name, state, minutes in (("old", "received", 6), ("classified", "classified", 6),
                                     ("assigned", "assigned", 6), ("boundary", "received", 5),
                                     ("new", "received", 4), ("closed", "completed", 6),
                                     ("has_card", "received", 6)):
            rid = uuid4()
            ids[name] = rid
            connection.execute(text("""
                INSERT INTO requests (id,org_id,classroom_id,requester_id,client_request_id,type,body,status,created_at)
                VALUES (:id,:org,:class,:parent,:key,'inquiry','[TEST] 누락',:status,:at)
            """), {"id": rid, "org": seed.ORG, "class": seed.CLASS_STAR, "parent": seed.PARENT,
                   "key": str(rid), "status": state, "at": now-timedelta(minutes=minutes)})
        connection.execute(text("""
            INSERT INTO cards (org_id,request_id,kind) VALUES (:org,:id,'reply_draft')
        """), {"org": seed.ORG, "id": ids["has_card"]})
    # 시드의 문의도 점검 대상이에요. 투약·귀가는 아래 별도 시험에서 제외를 확인해요.
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: runner.sweep_missing_cards(now), range(2)))
    assert runner.sweep_missing_cards(now) == 0
    for name in ("old", "classified", "assigned"):
        assert rows(seeded_db, "cards", ids[name]) == []
        assert [e["action"] for e in rows(seeded_db, "events", ids[name])] == ["agent_requeued"]
    runner.sweep_missing_cards(now+timedelta(minutes=5))
    assert runner.sweep_missing_cards(now+timedelta(minutes=5)) == 0
    for name in ("old", "classified", "assigned"):
        card = rows(seeded_db, "cards", ids[name])
        assert len(card) == 1 and card[0]["status"] == "pending" and card[0]["draft"] == {}
        assert card[0]["assignee_id"] == seed.TEACHER
        assert rows(seeded_db, "requests", ids[name])[0]["status"] == "awaiting_review"
        changes = [e for e in rows(seeded_db, "events", ids[name]) if e["to_status"]]
        assert len(changes) == 1 and changes[0]["detail"]["handoff_reason"] == "card_missing"
        assert changes[0]["actor_type"] == "system"
        agent_stub.run_request(ids[name])
        assert len(rows(seeded_db, "cards", ids[name])) == 1
    for name in ("boundary", "new", "closed"):
        assert rows(seeded_db, "cards", ids[name]) == []
    assert len(rows(seeded_db, "cards", ids["has_card"])) == 1


def test_expiry_read_once_and_private_hold_reason_is_hidden(db_client, parent, seeded_db):
    rid = create(db_client, parent).json()["request"]["id"]
    with seeded_db.begin() as connection:
        connection.execute(text("UPDATE requests SET status='on_hold' WHERE id=:id"), {"id": rid})
        connection.execute(text("UPDATE cards SET status='on_hold',hold_until=CURRENT_DATE WHERE request_id=:id"), {"id": rid})
        connection.execute(text("""
            INSERT INTO events (org_id,request_id,actor_type,action,detail)
            VALUES (:org,:id,'system','held','{"reason_text":"[TEST] 내부 보류 이유"}')
        """), {"org": seed.ORG, "id": rid})
    for _ in range(2):
        response = db_client.get("/api/v1/requests?status=awaiting_review", headers=parent)
        assert rid in [row["id"] for row in response.json()["items"]]
        detail = db_client.get(f"/api/v1/requests/{rid}", headers=parent)
        assert "[TEST] 내부 보류 이유" not in detail.text and detail.json()["request"]["hold_until"] is None
    resumed = [e for e in rows(seeded_db, "events", rid) if e["action"] == "resumed"]
    assert len(resumed) == 1 and resumed[0]["actor_type"] == "system"
    assert sum(n["kind"] == "hold_resumed" for n in rows(seeded_db, "notifications", rid)) == 1


def test_consult_slot_expiry_and_full_rejection_detail(db_client, parent, seeded_db):
    rid = create(db_client, parent, type="consultation").json()["request"]["id"]
    with seeded_db.begin() as connection:
        connection.execute(text("UPDATE requests SET status='awaiting_review' WHERE id=:id"), {"id": rid})
        connection.execute(text("""
            UPDATE consultation_slots SET status='chosen_by_parent',chosen_at=now()-interval '25 hours'
            WHERE card_id IN (SELECT id FROM cards WHERE request_id=:id)
        """), {"id": rid})
    for _ in range(2):
        data = db_client.get(f"/api/v1/requests/{rid}", headers=parent).json()
        assert data["request"]["status"] == "needs_info"
        assert len(data["consultation"]["slots"]) == 3 and all(s["status"] == "proposed" for s in data["consultation"]["slots"])
    assert sum(e["action"] == "slot_hold_expired" for e in rows(seeded_db, "events", rid)) == 1
    with seeded_db.begin() as connection:
        card_id = connection.scalar(text("SELECT id FROM cards WHERE request_id=:id"), {"id": rid})
        connection.execute(text("UPDATE requests SET status='rejected' WHERE id=:id"), {"id": rid})
        connection.execute(text("""
            INSERT INTO approvals (org_id,card_id,card_version,decided_by,decision,reason_code,reason_text)
            VALUES (:org,:card,1,:teacher,'dismiss','other','[TEST] 원 업무가 아니에요')
        """), {"org": seed.ORG, "card": card_id, "teacher": seed.TEACHER})
    data = db_client.get(f"/api/v1/requests/{rid}", headers=parent).json()
    assert data["rejection"] == {"reason_code": "other", "reason_text": "[TEST] 원 업무가 아니에요"}


def test_sse_waits_for_persisted_completion_and_has_safe_timeout(db_client, parent, seeded_db, monkeypatch):
    monkeypatch.setattr(streams, "MAX_SECONDS", 0)
    response = db_client.get(f"/api/v1/requests/{seed.REQUEST_COUGH}/stream",
                             headers={**parent, "X-Request-ID": "stream-timeout"})
    assert response.status_code == 200 and "event: error" in response.text and "event: done" not in response.text
    assert '"trace_id": "stream-timeout"' in response.text and "UPSTREAM_UNAVAILABLE" in response.text
    monkeypatch.setattr(streams, "MAX_SECONDS", 5)
    async def finish(_):
        with seeded_db.begin() as connection:
            req = dict(connection.execute(text("SELECT * FROM requests WHERE id=:id FOR UPDATE"),
                                           {"id": seed.REQUEST_COUGH}).mappings().one())
            events.set_status(connection, req, "awaiting_review", action="checked", actor_type="agent", agent_name="checker")
    monkeypatch.setattr(streams.anyio, "sleep", finish)
    response = db_client.get(f"/api/v1/requests/{seed.REQUEST_COUGH}/stream", headers=parent)
    assert "event: stage" in response.text and "event: done" in response.text
    assert '"request_status": "awaiting_review"' in response.text


def test_seed_sweep_only_inquiries_and_one_assignee_notice_per_handoff(seeded_db, monkeypatch):
    monkeypatch.setattr(runner, "run_request", lambda request_id: None)
    # 날짜와 무관하게 모든 시드가 5분을 넘긴 시점에서 검사해요.
    with seeded_db.connect() as connection:
        now = connection.scalar(text("SELECT max(created_at)+interval '6 minutes' FROM requests"))
    assert runner.sweep_missing_cards(now) == 9
    with seeded_db.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM cards")) == 0
        assert connection.scalar(text("SELECT count(*) FROM events WHERE action='agent_requeued'")) == 9
        assert connection.scalar(text("SELECT count(*) FROM notifications")) == 0
    assert runner.sweep_missing_cards(now+timedelta(minutes=5)) == 9
    with seeded_db.connect() as connection:
        counts = dict(connection.execute(text("""
            SELECT r.type,count(*) FROM cards c JOIN requests r ON r.id=c.request_id GROUP BY r.type
        """)).all())
        assert counts == {"inquiry": 9}
        notices = connection.execute(text("SELECT * FROM notifications")).mappings().all()
        assert len(notices) == 9
        assert all(n["recipient_id"] == seed.TEACHER and n["kind"] == "new_card" for n in notices)
        assert len({n["card_id"] for n in notices}) == 9
    assert runner.sweep_missing_cards(now) == 0
    with seeded_db.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM notifications")) == 9


def test_waiting_streams_leave_threads_available_for_me(db_client, parent, seeded_db, monkeypatch):
    from httpx import ASGITransport, AsyncClient
    from app.main import app

    monkeypatch.setattr(streams, "MAX_SECONDS", 10)

    async def exercise():
        # 기본 40개 풀의 포화를 작은 풀로 재현해요. 스트림은 풀 크기의 두 배예요.
        limiter = anyio.to_thread.current_default_thread_limiter()
        previous = limiter.total_tokens
        limiter.total_tokens = 4
        started = 0
        all_started = anyio.Event()

        async def observed(scope, receive, send):
            async def observed_send(message):
                nonlocal started
                if scope["path"].endswith("/stream") and message["type"] == "http.response.start":
                    assert message["status"] == 200
                    started += 1
                    if started == 8:
                        all_started.set()
                await send(message)
            await app(scope, receive, observed_send)

        try:
            async with AsyncClient(transport=ASGITransport(app=observed), base_url="http://test") as client:
                async def stream():
                    response = await client.get(f"/api/v1/requests/{seed.REQUEST_COUGH}/stream", headers=parent)
                    assert response.status_code == 200 and "event: done" in response.text
                async with anyio.create_task_group() as group:
                    for _ in range(8):
                        group.start_soon(stream)
                    with anyio.fail_after(3):
                        await all_started.wait()
                    # 열려 있는 스트림이 실제 poll 대기에 들어갈 시간을 줘요.
                    await anyio.sleep(0.1)
                    with anyio.fail_after(2):
                        response = await client.get("/api/v1/me", headers=parent)
                    assert response.status_code == 200
                    def finish():
                        with seeded_db.begin() as connection:
                            connection.execute(text("UPDATE requests SET status='awaiting_review' WHERE id=:id"),
                                               {"id": seed.REQUEST_COUGH})
                    await anyio.to_thread.run_sync(finish)
        finally:
            limiter.total_tokens = previous

    anyio.run(exercise)
