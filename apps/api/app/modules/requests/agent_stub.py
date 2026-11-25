"""모의 분류·카드 만들기를 DB에 옮긴 대역이에요. 실제 요청 그래프로 교체해요.

T29에서 Celery 워커로 옮겨요. 상담 후보는 DB 일정·예약에서 계산해요.
"""

import json
from datetime import datetime

from sqlalchemy import text

from app.core.constants import OUT_OF_SCOPE_MESSAGES
from app.core.db import transaction
from app.core.request_rules import direct_notice_kind
from app.modules.requests.supervisor import classify_request, topic_conflict, validate_proposal
from app.core.schedule import KST, due_at
from app.modules.requests.complaints import repeat_count
from app.modules.requests.events import record, set_status
from app.modules.consultations.slots import propose_slots
from app.modules.documents.answer import answer_for_request, graph_enabled, save_evidence
from app.modules.documents.public_sources import attach_law_evidence, forecast_evidence, prefetch_public


def homeroom_teacher(connection, req):
    return connection.scalar(text("""
        SELECT s.user_id FROM classroom_staff s JOIN users u ON (u.id,u.org_id)=(s.user_id,s.org_id)
        WHERE s.org_id=:org AND s.classroom_id=:class AND u.role='teacher' AND u.is_active
          AND (s.valid_from IS NULL OR s.valid_from<=:today) AND (s.valid_to IS NULL OR s.valid_to>=:today)
        ORDER BY s.is_homeroom DESC,s.created_at,s.user_id LIMIT 1
    """), {"org": req["org_id"], "class": req["classroom_id"], "today": datetime.now(KST).date()})


def new_card(connection, req, kind, assignee, draft=None):
    card = dict(connection.execute(text("""
        INSERT INTO cards (org_id,request_id,kind,status,assignee_id,due_at,draft)
        VALUES (:org,:request,:kind,:status,:assignee,:due,CAST(:draft AS jsonb)) RETURNING *
    """), {"org": req["org_id"], "request": req["id"], "kind": kind,
           "status": "pending" if assignee else "unassigned", "assignee": assignee,
           "due": due_at(req["created_at"], req["type"], req["risk_level"], kind),
           "draft": json.dumps(draft or {})}).mappings().one())
    record(connection, req, "created", card=card, actor_type="agent", agent_name="supervisor")
    return card


def draft_outside_lock(initial, first, prefetched):
    """자료·검사 AI(최악 수십 분)를 요청 행 잠금 밖에서 부른다. 저장은 run_request의 짧은 잠금 트랜잭션에서만 한다."""
    if initial["type"] != "inquiry" or not graph_enabled() or first.get("risk_level") in ("urgent", "uncertain"):
        return None
    forecast = None
    day, fetched = prefetched.get("forecast", (None, None))
    if fetched:  # 못 가져온 예보는 여기서 다시 부르지 않는다
        try:
            with transaction() as connection:  # 공공 자료는 같은 내용이면 같은 조각이라, 초안을 버려도 남아서 문제없다
                forecast = forecast_evidence(connection, initial["org_id"], day, forecast=fetched)
        except Exception:
            forecast = None
    return answer_for_request(initial, forecast=forecast)


def run_request(request_id, prepared_answer=None, prepared_fields=None):
    # LLM 호출은 요청 행 잠금 밖에서 한다. 요청 본문·유형은 접수 후 고정이다.
    with transaction() as connection:
        initial = connection.execute(text("""
            SELECT type,body,status,org_id,classroom_id,requester_id FROM requests WHERE id=:id
        """), {"id": request_id}).mappings().one_or_none()
        if initial is None or initial["status"] not in ("received", "classified", "assigned", "needs_info"):
            return
        has_card = connection.scalar(text("SELECT EXISTS (SELECT 1 FROM cards WHERE request_id=:id)"),
                                     {"id": request_id})
        # 기존 규칙대로 needs_info 문의·민원만 카드가 있어도 다시 처리한다.
        if has_card and (initial["status"] != "needs_info" or initial["type"] == "consultation"):
            return
    if initial["type"] not in ("inquiry", "consultation", "complaint"):
        return
    proposal = prepared_fields if prepared_fields is not None else classify_request(initial["type"], initial["body"])
    # 법령·예보 공공 API(법령은 최악 약 20초)는 DB 연결을 잡기 전에 가져와 둔다(T52). 저장만 아래 트랜잭션에서 한다.
    first = prepared_fields if prepared_fields is not None else validate_proposal(initial["type"], initial["body"], proposal)
    notice = direct_notice_kind(initial["type"], initial["body"], first)
    prefetched = {} if notice else prefetch_public(initial["type"], initial["body"], first["topic_key"], datetime.now(KST).date(),
                                 with_forecast=graph_enabled() and prepared_answer is None and prepared_fields is None,
                                 risk_category=first.get("risk_category"))
    drafted = None if notice else (prepared_answer if prepared_answer is not None
                                  else draft_outside_lock(initial, first, prefetched))
    with transaction() as connection:
        row = connection.execute(text("SELECT * FROM requests WHERE id=:id FOR UPDATE"),
                                 {"id": request_id}).mappings().one_or_none()
        if row is None or row["status"] not in ("received", "classified", "assigned", "needs_info"):
            return
        req = dict(row)
        if req["type"] not in ("inquiry", "consultation", "complaint"):
            return
        # 중복 실행은 요청 행 잠금으로 직렬화하고 카드를 늘리지 않아요.
        has_card = connection.scalar(text("SELECT EXISTS (SELECT 1 FROM cards WHERE request_id=:id)"), {"id": request_id})
        if has_card and (req["status"] != "needs_info" or req["type"] == "consultation"):
            return
        fields = (prepared_fields if prepared_fields is not None and req["type"] == initial["type"]
                  and req["body"] == initial["body"] else validate_proposal(req["type"], req["body"],
                  proposal if req["type"] == initial["type"] and req["body"] == initial["body"] else {}))
        if req["type"] == "complaint" and fields["topic_key"] != "other":
            # 서로 다른 요청의 동시 분류도 앞선 커밋을 포함해 세 번째를 셀 수 있어야 해요.
            # FK가 잡는 반 행 잠금과 충돌하지 않도록 묶음별 트랜잭션 자문 잠금을 써요.
            connection.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"), {
                "key": f"complaint:{req['org_id']}:{req['classroom_id']}:{fields['topic_key']}"})
        req.update(fields)
        connection.execute(text("""
            UPDATE requests SET topic_key=:topic_key,urgency=:urgency,risk_level=:risk_level,risk_category=:risk_category
            WHERE id=:id
        """), {"id": request_id, "risk_level": None, "risk_category": None, **fields})
        set_status(connection, req, "classified", action="classified", actor_type="agent", agent_name="supervisor",
                   topic_model_rejected=topic_conflict(req["type"], req["body"], proposal)
                   if req["type"] == initial["type"] and req["body"] == initial["body"] else False)
        teacher = homeroom_teacher(connection, req)
        req["assignee_id"] = teacher
        connection.execute(text("UPDATE requests SET assignee_id=:teacher WHERE id=:id"), {"teacher": teacher, "id": request_id})
        set_status(connection, req, "assigned", action="assigned", actor_type="agent", agent_name="supervisor")
        notice = direct_notice_kind(req["type"], req["body"], fields)
        if notice:
            connection.execute(text("""
                INSERT INTO request_messages (org_id,request_id,sender_type,body)
                VALUES (:org,:request,'agent',:body)
            """), {"org": req["org_id"], "request": request_id, "body": OUT_OF_SCOPE_MESSAGES[notice]})
            if req["type"] == "inquiry":
                set_status(connection, req, "sent_or_booked", action="out_of_scope_answered", kind=notice,
                           actor_type="agent", agent_name="supervisor")
                return
        high_risk = req["risk_level"] in ("urgent", "uncertain")
        director = connection.scalar(text("""
            SELECT id FROM users WHERE org_id=:org AND role='director' AND is_active ORDER BY id LIMIT 1
        """), {"org": req["org_id"]})
        if req["type"] == "consultation":
            card = new_card(connection, req, "consult_slots", teacher)
            propose_slots(connection, req, card, teacher)
            set_status(connection, req, "needs_info", action="info_requested", card=card,
                       actor_type="agent", agent_name="code")
            if high_risk and director:
                # 상담 시간 고르기·확정은 담임 흐름 그대로 두고, 원장에게 보고 카드와 알림만 더해요.
                report = new_card(connection, req, "director_report", director, {"summary": req["body"][:60]})
                record(connection, req, "escalated", card=report, actor_type="agent", agent_name="supervisor", reason="risk")
            return
        draft = {"summary": req["body"][:60], "no_evidence": True}
        answer, check = None, None
        if not high_risk:
            if prepared_answer and prepared_answer.get("handoff"):
                answer = drafted if drafted and req["body"] == initial["body"] else None
                if answer:
                    draft.update({key: answer[key] for key in ("no_evidence", "conflict")})
                draft["text"] = ""
                check = answer.get("check_result") if answer else None
            elif (req["type"] == "inquiry" and graph_enabled()) or (
                    req["type"] == "complaint" and prepared_answer is not None):
                # 잠금 밖에서 만든 초안은 같은 본문일 때만 쓴다. 없으면 모델을 잠금 안에서 다시 부르지 않고 초안 없는 카드로 둔다.
                answer = drafted if drafted and req["body"] == initial["body"] else None
                if answer:
                    draft.update({key: answer[key] for key in ("text", "no_evidence", "conflict")})
                    check = answer.get("check_result")
                if answer is None or answer["no_evidence"] or answer["conflict"]:
                    # API 5.7: 근거 없음·충돌은 초안 없는 카드. 대체 문장이 승인으로 학부모에게 나가면 안 돼요.
                    draft["text"] = ""
            else:
                draft["text"] = "(모의 초안) 말씀해 주셔서 감사합니다. 확인해서 다시 안내드릴게요."
                check = {"passed": True, "issues": [], "attempt": 1}
        card = new_card(connection, req, "reply_draft", teacher, draft)
        if answer:
            save_evidence(connection, card, answer)
        if check is not None:
            card["check_result"] = check
            connection.execute(text("UPDATE cards SET check_result=CAST(:check AS jsonb) WHERE id=:id"),
                               {"id": card["id"], "check": json.dumps(check)})
        if req["type"] == "complaint":
            attach_law_evidence(connection, card, req, prefetched)  # 조건에 맞을 때만 법령 근거를 붙임(T52)
        record(connection, req, "drafted", card=card, actor_type="agent", agent_name="document")
        repeated = (repeat_count(connection, req) or 0) >= 3
        if (high_risk or repeated) and director:
            report = new_card(connection, req, "director_report", director, {"summary": req["body"][:60]})
            set_status(connection, req, "escalated", action="escalated", card=report,
                       actor_type="agent", agent_name="supervisor", reason="risk" if high_risk else "repeat")
        else:
            set_status(connection, req, "awaiting_review", action="checked", card=card,
                       actor_type="agent", agent_name="checker")
