"""카드 결정은 요청 → 같은 요청의 카드 순서로 잠그고 한 번에 저장해요."""

import json
import logging
from contextlib import contextmanager

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core import scope
from app.core.db import transaction
from app.core.errors import ApiError
from app.core.request_rules import RECLASSIFY_TYPES
from app.core.schedule import due_at
from app.modules.requests.agent_stub import new_card
from app.modules.consultations.slots import propose_slots
from app.modules.consultations.bookings import book_slot
from app.modules.requests.events import record, set_status
from app.modules.requests.requests import _expire, _lock
from app.modules.memories.memories import remember_rejection

log = logging.getLogger(__name__)


@contextmanager
def locked(user, card_id, *, decision=None):
    try:
        with transaction() as connection:
            initial = scope.card_in_scope(user, card_id, decision=decision, connection=connection)
            req = None
            if initial["request_id"]:
                req = _expire(connection, _lock(connection, initial["request_id"]))
                # 대화·자동 만료와 같은 잠금 순서예요. 서로 다른 카드 결정도 직렬화해요.
                connection.execute(
                    text("SELECT id FROM cards WHERE request_id=:id ORDER BY id FOR NO KEY UPDATE"), {"id": req["id"]}
                ).all()
            card = dict(
                connection.execute(text("SELECT * FROM cards WHERE id=:id FOR NO KEY UPDATE"), {"id": card_id})
                .mappings()
                .one()
            )
            card["classroom_id"] = initial["classroom_id"]
            yield connection, card, req
    except IntegrityError as error:
        if error.orig.sqlstate == "23505" and error.orig.diag.constraint_name == "approvals_card_id_card_version_key":
            raise ApiError(409, "ALREADY_DECIDED") from error
        if error.orig.sqlstate == "23514" and "complete without parent confirmation" in str(error.orig):
            raise ApiError(409, "REASON_REQUIRED") from error
        raise


def version(connection, card, value, approval=True):
    if approval and connection.scalar(
        text("SELECT EXISTS (SELECT 1 FROM approvals WHERE card_id=:id AND card_version=:v)"),
        {"id": card["id"], "v": value},
    ):
        raise ApiError(409, "ALREADY_DECIDED")
    if value != card["version"]:
        raise ApiError(409, "CARD_VERSION_CONFLICT", current_version=card["version"])


def touch(connection, card, status=None):
    card.update(
        connection.execute(
            text("""
        UPDATE cards SET status=:status,version=version+1,updated_at=clock_timestamp(),
            closed_at=CASE WHEN :status IN ('done','rejected') THEN clock_timestamp() ELSE NULL END,
            hold_until=:hold,draft=CAST(:draft AS jsonb) WHERE id=:id RETURNING *
    """),
            {
                "id": card["id"],
                "status": status or card["status"],
                "hold": card["hold_until"],
                "draft": json.dumps(card["draft"]),
            },
        )
        .mappings()
        .one()
    )


def approval(connection, card, user, decision, reason_code=None, reason_text=None, edited_content=None):
    connection.execute(
        text("""
        INSERT INTO approvals (card_id,org_id,card_version,decided_by,decision,reason_code,reason_text,edited_content)
        VALUES (:id,:org,:v,:user,:decision,:code,:reason,CAST(:edited AS jsonb))
    """),
        {
            "id": card["id"],
            "org": card["org_id"],
            "v": card["version"],
            "user": user.id,
            "decision": decision,
            "code": reason_code,
            "reason": reason_text,
            "edited": json.dumps(edited_content) if edited_content is not None else None,
        },
    )


def result(card, req, next_card=None):
    return {
        "card": {k: card[k] for k in ("id", "status", "version")},
        "request": {k: req[k] for k in ("id", "status", "parent_confirmed_at")} if req else None,
        "next_card_id": next_card["id"] if next_card else None,
    }


def _resume_graph_after_commit(card):
    if not card.get("graph_thread_id") or card["status"] not in ("done", "rejected"):
        return
    try:
        from app.modules.requests.graph_agent import try_resume
        try_resume(card["id"])
    except Exception as error:  # noqa: BLE001 - 승인 커밋은 유지하고 주기 점검에서 다시 전달한다
        log.warning("승인 뒤 그래프 전달 실패 error_type=%s", type(error).__name__)


def report(connection, req):
    existing = (
        connection.execute(
            text("""
        SELECT * FROM cards WHERE request_id=:id AND kind='director_report' AND status NOT IN ('done','rejected')
        ORDER BY created_at,id LIMIT 1
    """),
            {"id": req["id"]},
        )
        .mappings()
        .one_or_none()
    )
    if existing:
        return dict(existing)
    director = connection.scalar(
        text("SELECT id FROM users WHERE org_id=:org AND role='director' AND is_active ORDER BY id LIMIT 1"),
        {"org": req["org_id"]},
    )
    if director is None:
        raise ApiError(409, "INVALID_TRANSITION")
    return new_card(connection, req, "director_report", director, {"summary": req["body"][:60]})


def close_reports(connection, req):
    """위험 상담의 원장 보고 카드는 원장 지시(escalated만 받음)로 닫을 수 없어서, 요청이 끝날 때(예약 확정·반려) 같이 닫아요."""
    for report_card in connection.execute(text("""
        SELECT * FROM cards WHERE request_id=:id AND kind='director_report' AND status NOT IN ('done','rejected')
    """), {"id": req["id"]}).mappings().all():
        touch(connection, dict(report_card), "done")


def decide(user, card_id, body):
    with locked(user, card_id, decision=body.decision) as (connection, card, req):
        version(connection, card, body.version)
        choice = body.decision
        valid = req is not None and req["status"] not in ("completed", "rejected")
        if choice == "complete":
            valid = (
                valid
                and card["kind"] == "reply_draft"
                and card["status"] == "done"
                and req["type"] == "complaint"
                and req["status"] == "sent_or_booked"
            )
        elif choice == "resume":
            valid = valid and card["status"] == "on_hold" and req["status"] == "on_hold"
        else:
            valid = valid and card["status"] in ("pending", "in_review") and req["status"] == "awaiting_review"
        if card["kind"] == "director_report" and choice not in ("hold", "resume"):
            valid = False
        if choice in ("approve", "edit_approve") and card["kind"] != "reply_draft":
            valid = False
        # 판단 필요는 재분류로 풀 수 있는 문의·민원만 막아요. 상담은 시간 확정 흐름 그대로예요.
        if (req and req["risk_level"] == "uncertain" and req["type"] in RECLASSIFY_TYPES
                and choice not in ("hold", "resume", "escalate")):
            valid = False
        if not valid:
            raise ApiError(409, "INVALID_TRANSITION")
        if choice == "complete" and req["parent_confirmed_at"] is None and not body.reason_text:
            raise ApiError(409, "REASON_REQUIRED")
        content = body.edited_content if choice == "edit_approve" else card["draft"]
        if choice in ("approve", "edit_approve") and (
            not isinstance(content.get("text"), str) or not content["text"].strip()
        ):
            raise ApiError(409, "INVALID_TRANSITION")
        approval(connection, card, user, choice, body.reason_code, body.reason_text, body.edited_content)
        if choice in ("reject", "dismiss"):
            remember_rejection(connection, user, card, choice, body.reason_code, body.reason_text)
        actor = {"card": card, "actor_type": "user", "actor_id": user.id}
        next_card = None
        if choice in ("approve", "edit_approve"):
            card["draft"] = content
            card["status"] = "approved"
            set_status(connection, req, "approved", action="approved", **actor)
            connection.execute(
                text("""INSERT INTO request_messages (org_id,request_id,sender_type,sender_id,body)
                VALUES (:org,:id,'user',:user,:body)"""),
                {"org": req["org_id"], "id": req["id"], "user": user.id, "body": content["text"]},
            )
            set_status(connection, req, "sent_or_booked", action="sent", **actor)
            touch(connection, card, "done")
        elif choice == "complete":
            set_status(connection, req, "completed", action="completed", reason_text=body.reason_text, **actor)
            touch(connection, card, "done")
        elif choice == "hold":
            card["hold_until"] = body.hold_until
            set_status(connection, req, "on_hold", action="held", reason_text=body.reason_text, **actor)
            touch(connection, card, "on_hold")
        elif choice == "resume":
            card["hold_until"] = None
            set_status(connection, req, "awaiting_review", action="resumed", **actor)
            touch(connection, card, "pending")
            req = _expire(connection, req)
        elif choice == "dismiss":
            set_status(
                connection,
                req,
                "rejected",
                action="dismissed",
                reason_code=body.reason_code,
                reason_text=body.reason_text,
                **actor,
            )
            touch(connection, card, "rejected")
            close_reports(connection, req)
        elif choice == "escalate":
            next_card = report(connection, req)
            set_status(connection, req, "escalated", action="escalated", **actor)
            touch(connection, card)
        elif choice == "reject":
            touch(connection, card, "rejected")
            set_status(
                connection,
                req,
                "assigned",
                action="rejected",
                reason_code=body.reason_code,
                reason_text=body.reason_text,
                **actor,
            )
            draft = dict(card["draft"])
            draft["no_evidence"] = True
            check = card["check_result"]
            if card["kind"] == "reply_draft":
                # 거절 뒤 재초안은 초안 없는 카드(API 5.7, T47 결정 4). 앞 카드의 검사 통과를 물려받지 않아
                # 일반 승인은 409로 막히고 담임이 직접 쓴 글(edit_approve)만 나간다.
                draft["text"] = ""
                check = None
            next_card = new_card(connection, req, card["kind"], card["assignee_id"], draft)
            connection.execute(
                text("UPDATE cards SET check_result=CAST(:check AS jsonb) WHERE id=:id"),
                {"id": next_card["id"], "check": json.dumps(check) if check is not None else None},
            )
            if card["kind"] == "consult_slots":
                connection.execute(
                    text(
                        "UPDATE consultation_slots SET status='discarded' WHERE card_id IN (SELECT id FROM cards WHERE request_id=:id)"
                    ),
                    {"id": req["id"]},
                )
                propose_slots(connection, req, next_card, next_card["assignee_id"])
                set_status(connection, req, "needs_info", action="info_requested", card=next_card)
            else:
                set_status(connection, req, "awaiting_review", action="drafted", card=next_card)
        response = result(card, req, next_card)
    _resume_graph_after_commit(card)
    return response


def rule_decision(user, rule_id, body):
    with transaction() as connection:
        values = {"id": rule_id, "org": user.org_id, "owner": user.id}
        rule = connection.execute(text("""
            SELECT * FROM memory_rules WHERE id=:id AND org_id=:org AND owner_id=:owner
        """), values).mappings().one_or_none()
        scope._checked(user, rule, rule is not None, "memory_rule", rule_id)
        connection.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
                           {"key": f"memory-rule:{user.org_id}:{user.id}:{rule['reason_code']}"})
        # 일반 카드 결정·재배정과 같은 카드 → 규칙 순서예요. 범위 밖 행은 잠그지 않아요.
        card = connection.execute(text("""
            SELECT * FROM cards WHERE subject_type='memory_rule' AND subject_id=:id AND org_id=:org
              AND kind='rule_proposal' ORDER BY created_at,id LIMIT 1 FOR NO KEY UPDATE
        """), values).mappings().one_or_none()
        rule = connection.execute(text("""
            SELECT * FROM memory_rules WHERE id=:id AND org_id=:org AND owner_id=:owner FOR NO KEY UPDATE
        """), values).mappings().one()
        if rule["status"] != "proposed" or card is None or card["status"] not in ("pending", "in_review"):
            raise ApiError(409, "INVALID_TRANSITION")
        card = dict(card)
        action = "approve" if body.decision == "activate" else "reject"
        status = "active" if body.decision == "activate" else "declined"
        approval(connection, card, user, action, reason_code=rule["reason_code"])
        connection.execute(text("UPDATE memory_rules SET status=:status,decided_at=clock_timestamp() WHERE id=:id"),
                           {"id": rule_id, "status": status})
        touch(connection, card, "done")
        record(connection, None, "approved" if action == "approve" else "rejected", card=card,
               actor_type="user", actor_id=user.id)
        return {"rule": {"id": rule_id, "status": status}}


def book(user, card_id, body):
    with locked(user, card_id) as (connection, card, req):
        # 재배정만 받은 다른 반 교사는 조회할 수 있어도 대신 확정하지 못해요.
        if user.role != "teacher" or not scope._classroom(connection, user, card["classroom_id"]):
            raise ApiError(403, "FORBIDDEN_ROLE")
        version(connection, card, body.version)
        slot = connection.execute(text("""
            SELECT s.*,r.name AS room FROM consultation_slots s JOIN rooms r
              ON (r.id,r.org_id)=(s.room_id,s.org_id)
            WHERE s.id=:id AND s.card_id=:card AND s.org_id=:org FOR NO KEY UPDATE OF s
        """), {"id": body.slot_id, "card": card_id, "org": user.org_id}).mappings().one_or_none()
        if slot is None:
            scope._checked(user, None, False, "slot", body.slot_id)
        if req is None or card["kind"] != "consult_slots" or req["status"] == "escalated":
            raise ApiError(409, "INVALID_TRANSITION")
        if slot["status"] != "chosen_by_parent":
            raise ApiError(409, "SLOT_NOT_CHOSEN")
        if req["status"] != "awaiting_review" or card["status"] != "pending":
            raise ApiError(409, "INVALID_TRANSITION")
        booking_id = book_slot(connection, slot, request_id=req["id"], confirmed_by=user.id)
        approval(connection, card, user, "approve")
        connection.execute(text("""
            UPDATE consultation_slots SET status=CASE WHEN id=:slot THEN 'confirmed' ELSE 'discarded' END
            WHERE card_id=:card
        """), {"slot": slot["id"], "card": card_id})
        actor = {"card": card, "actor_type": "user", "actor_id": user.id}
        set_status(connection, req, "approved", action="approved", **actor)
        set_status(connection, req, "sent_or_booked", action="booked", **actor)
        touch(connection, card, "done")
        close_reports(connection, req)
        response = {"booking": {"id": booking_id, "room": slot["room"],
                                "period": {"start": slot["period"].lower, "end": slot["period"].upper}},
                    "request": result(card, req)["request"]}
    _resume_graph_after_commit(card)
    return response


def reclassify(user, card_id, body):
    with locked(user, card_id, decision="reclassify") as (connection, card, req):
        version(connection, card, body.version, approval=False)
        if req is None or req["type"] not in RECLASSIFY_TYPES or req["status"] not in ("awaiting_review", "escalated"):
            raise ApiError(409, "INVALID_TRANSITION")
        previous = req["risk_level"]
        req["risk_level"], req["risk_category"] = (
            body.risk_level,
            body.risk_category if body.risk_level == "urgent" else None,
        )
        connection.execute(
            text("UPDATE requests SET risk_level=:risk,risk_category=:category WHERE id=:id"),
            {"id": req["id"], "risk": req["risk_level"], "category": req["risk_category"]},
        )
        for related in connection.execute(
            text("SELECT id,kind FROM cards WHERE request_id=:id"), {"id": req["id"]}
        ).mappings():
            connection.execute(
                text("UPDATE cards SET due_at=:due WHERE id=:id"),
                {
                    "id": related["id"],
                    "due": due_at(req["created_at"], req["type"], req["risk_level"], related["kind"]),
                },
            )
        reports = [dict(row) for row in connection.execute(text("""
            SELECT * FROM cards WHERE request_id=:id AND kind='director_report'
              AND status NOT IN ('done','rejected') ORDER BY id
        """), {"id": req["id"]}).mappings()]
        closed_target = False
        if user.role == "director" and body.risk_level == "normal":
            for report_card in reports:
                touch(connection, report_card, "done")
                if report_card["id"] == card["id"]:
                    card.update(report_card)
                    closed_target = True
                # 닫은 보고 카드에도 같은 재분류 이유와 연결 이력을 남겨요.
                if report_card["id"] != card["id"]:
                    record(connection, req, "risk_reclassified", card=report_card,
                           actor_type="user", actor_id=user.id, reason=body.reason,
                           previous_risk_level=previous)
            reports = []
        if not closed_target:
            touch(connection, card)
        set_status(
            connection,
            req,
            "escalated" if reports else "awaiting_review",
            action="risk_reclassified",
            card=card,
            actor_type="user",
            actor_id=user.id,
            reason=body.reason,
            previous_risk_level=previous,
        )
        if body.risk_level == "urgent":
            report_card = report(connection, req)
            set_status(
                connection, req, "escalated", action="escalated", card=report_card, actor_type="user", actor_id=user.id
            )
        from app.modules.cards.card_views import staff_request

        return {"request": staff_request(connection, req)}


def instruct(user, card_id, body):
    if user.role != "director":
        raise ApiError(403, "FORBIDDEN_ROLE")
    with locked(user, card_id) as (connection, card, req):
        version(connection, card, body.version)
        if (
            req is None
            or card["kind"] != "director_report"
            or card["status"] not in ("pending", "in_review")
            or req["status"] != "escalated"
        ):
            raise ApiError(409, "INVALID_TRANSITION")
        reply = (
            connection.execute(
                text(
                    "SELECT * FROM cards WHERE request_id=:id AND kind=:kind AND status IN ('pending','in_review') "
                    "ORDER BY created_at DESC,id DESC LIMIT 1"
                ),
                {"id": req["id"], "kind": "consult_slots" if req["type"] == "consultation" else "reply_draft"},
            )
            .mappings()
            .one_or_none()
        )
        if reply is None:
            raise ApiError(409, "INVALID_TRANSITION")
        approval(connection, card, user, "instruct", reason_text=body.instruction)
        touch(connection, card, "done")
        set_status(
            connection, req, "awaiting_review", action="instructed", card=reply, actor_type="user", actor_id=user.id
        )
        return result(card, req)


def reassign(user, card_id, body):
    if user.role != "director":
        raise ApiError(403, "FORBIDDEN_ROLE")
    with locked(user, card_id) as (connection, card, req):
        target = (
            connection.execute(
                text("SELECT id,display_name FROM users WHERE id=:id AND org_id=:org AND role='teacher' AND is_active"),
                {"id": body.assignee_id, "org": user.org_id},
            )
            .mappings()
            .one_or_none()
        )
        if target is None:
            scope._checked(user, None, False, "assignee", body.assignee_id)
        if card["kind"] in ("director_report", "rule_proposal") or card["status"] in ("done", "rejected"):
            raise ApiError(409, "INVALID_TRANSITION")
        previous = card["assignee_id"]
        card["assignee_id"] = target["id"]
        connection.execute(
            text("UPDATE cards SET assignee_id=:target WHERE id=:id"), {"id": card["id"], "target": target["id"]}
        )
        if req:
            req["assignee_id"] = target["id"]
            connection.execute(
                text("UPDATE requests SET assignee_id=:target WHERE id=:id"), {"id": req["id"], "target": target["id"]}
            )
        touch(connection, card, "pending" if card["status"] == "unassigned" else None)
        record(
            connection,
            req,
            "reassigned",
            card=card,
            actor_type="user",
            actor_id=user.id,
            **{"from": str(previous) if previous else None, "to": str(target["id"]), "reason": body.reason},
        )
        return {"card": {"assignee": dict(target), "version": card["version"]}}


def stream(user, card_id):
    from app.modules.cards.streams import stream as replay

    return replay(user, card_id)
