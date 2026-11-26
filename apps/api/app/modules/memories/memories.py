import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path

from sqlalchemy import text

from app.core import scope
from app.core.consents import memory_kinds
from app.core.constants import CONSENT_VERSION, REJECTION_RULE_TEXTS, REJECTION_RULE_THRESHOLD, TONE_LIMIT, TONE_READ_LIMIT
from app.core.db import transaction
from app.core.schedule import KST
from app.core.errors import ApiError
from app.core.memory_rules import mask_child_names, validate_rule_json, tone_contents, parent_candidates, memory_page
from agents.llm import OpenAIModel, feature
from agents.guardrails.sensitive import mask_sensitive
from app.modules.requests import events
from app.modules.requests.events import record

from app.modules.memories.saved_answers import set_status as set_saved_status

log = logging.getLogger(__name__)
VISIBLE_MEMORY = """m.org_id=:org AND m.deleted_at IS NULL AND (
    (m.owner_id=:owner AND m.child_id IS NULL AND (NOT :parent OR m.kind='preference'))
    OR (:parent AND m.kind='care_note' AND EXISTS (SELECT 1 FROM child_guardians g
        WHERE (g.child_id,g.org_id,g.user_id)=(m.child_id,m.org_id,:owner))))"""


def load_tones(connection, org_id, owner_id):
    return [dict(row) for row in connection.execute(text("""
        SELECT kind,content FROM memories WHERE org_id=:org AND owner_id=:owner
          AND kind='tone' AND deleted_at IS NULL AND confirm_status='confirmed' ORDER BY created_at DESC,id DESC LIMIT :limit
    """), {"org": org_id, "owner": owner_id, "limit": TONE_READ_LIMIT}).mappings()]


def save_tones(connection, user, card, candidates, names):
    connection.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
                       {"key": f"tone:{user.org_id}:{user.id}"})
    for content in tone_contents(candidates, names):
        connection.execute(text("""
            INSERT INTO memories(org_id,owner_id,kind,content,structured,source_card_id)
            SELECT :org,:owner,'tone',:content,CAST(:data AS jsonb),:card
            WHERE NOT EXISTS (SELECT 1 FROM memories WHERE org_id=:org AND owner_id=:owner
                              AND kind='tone' AND deleted_at IS NULL AND content=:content)
        """), {"org": user.org_id, "owner": user.id, "content": content, "card": card["id"],
               "data": json.dumps({"source": "edit_approve", "card_version": card["version"]})})
    connection.execute(text("""
        UPDATE memories SET deleted_at=now() WHERE org_id=:org AND owner_id=:owner AND id IN (
            SELECT id FROM memories WHERE org_id=:org AND owner_id=:owner AND kind='tone'
              AND deleted_at IS NULL ORDER BY created_at DESC,id DESC OFFSET :limit)
    """), {"org": user.org_id, "owner": user.id, "limit": TONE_LIMIT})


def memory_failed(card, tool, req=None):
    try:
        with transaction() as connection:
            record(connection, req, "tool_failed", card=card, actor_type="agent", agent_name="memory",
                   tool=tool, code="SAVE_FAILED")
    except Exception:
        log.warning("기억 실패 이력 저장 실패 tool=%s", tool)


@feature("담임 말투 기억")
def after_approval(user, card, req, decision, content):
    # API 백그라운드: 승인 커밋 뒤, 덮어쓰기 전 초안 스냅샷과 실제 발송문을 비교해요.
    try:
        from app.modules.memories.saved_answers import remember_answer
        remember_answer(user, card, req, content)
    except Exception:
        memory_failed(card, "save_answer")
    if req["type"] == "inquiry":
        after_request(req["id"])
    if decision != "edit_approve" or user.role != "teacher" or not os.getenv("LLM_MODEL_MEMORY", "").strip():
        return
    try:
        with transaction() as connection:
            names = list(connection.scalars(text("SELECT display_name FROM children WHERE org_id=:org"),
                                            {"org": user.org_id}))
        prompt = (Path(__file__).resolve().parents[5] / "agents/prompts/memory.md").read_text()
        payload = {"original": mask_sensitive(mask_child_names(card["draft"].get("text", ""), names)),
                   "edited": mask_sensitive(mask_child_names(content["text"], names))}
        result = OpenAIModel("MEMORY").json(prompt, json.dumps(payload, ensure_ascii=False))
        if (not isinstance(result, dict) or not isinstance(result.get("tones"), list)
                or len(result["tones"]) > 2 or any(not isinstance(item, dict)
                    or item.get("kind") != "tone" or not isinstance(item.get("content"), str)
                    for item in result["tones"])):
            raise ValueError("말투 후보 형식 오류")
        with transaction() as connection:
            save_tones(connection, user, card, result["tones"], names)
    except Exception:
        memory_failed(card, "extract_tone")


def load_preferences(connection, org_id, owner_id):
    return [dict(row) for row in connection.execute(text("""
        SELECT kind,content,structured FROM memories WHERE org_id=:org AND owner_id=:owner
          AND kind='preference' AND child_id IS NULL AND confirm_status='confirmed' AND deleted_at IS NULL
        ORDER BY created_at DESC,id DESC LIMIT 5
    """), {"org": org_id, "owner": owner_id}).mappings()]


def load_child_notes(connection, org_id, child_id, reader_id):
    return [dict(row) for row in connection.execute(text("""
        SELECT m.kind,m.content FROM memories m JOIN children c ON (c.id,c.org_id)=(m.child_id,m.org_id)
        WHERE m.org_id=:org AND m.child_id=:child AND m.kind='care_note'
          AND m.confirm_status='confirmed' AND m.deleted_at IS NULL
          AND (EXISTS (SELECT 1 FROM child_guardians g WHERE (g.child_id,g.org_id,g.user_id)=(c.id,c.org_id,:reader))
            OR EXISTS (SELECT 1 FROM classroom_staff s JOIN users u ON (u.id,u.org_id)=(s.user_id,s.org_id)
              WHERE s.org_id=c.org_id AND s.classroom_id=c.classroom_id AND s.user_id=:reader
                AND u.role='teacher' AND u.is_active AND (s.valid_from IS NULL OR s.valid_from<=:today)
                AND (s.valid_to IS NULL OR s.valid_to>=:today)))
        ORDER BY m.created_at DESC,m.id DESC LIMIT 5
    """), {"org": org_id, "child": child_id, "reader": reader_id, "today": datetime.now(KST).date()}).mappings()]


def _memory_kinds(connection, req):
    return memory_kinds(set(connection.scalars(text("""
        SELECT item FROM user_consents WHERE org_id=:org AND user_id=:user AND terms_version=:version
    """), {"org": req["org_id"], "user": req["requester_id"], "version": CONSENT_VERSION})))


def save_parent_candidates(connection, req, candidates, names):
    own_name = connection.scalar(text("SELECT display_name FROM children WHERE id=:child AND org_id=:org"),
                                 {"child": req["child_id"], "org": req["org_id"]})
    if mask_child_names(req["body"], [name for name in names if name != own_name]) != req["body"]:
        return
    if not connection.scalar(text("""SELECT EXISTS (SELECT 1 FROM child_guardians
        WHERE (org_id,child_id,user_id)=(:org,:child,:owner))"""),
        {"org": req["org_id"], "child": req["child_id"], "owner": req["requester_id"]}):
        return
    kinds = _memory_kinds(connection, req)
    connection.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
                       {"key": f"parent-memory:{req['org_id']}:{req['requester_id']}"})
    for item in parent_candidates(candidates, req["body"], names):
        if item["kind"] not in kinds:
            continue
        child = req["child_id"] if item["kind"] == "care_note" else None
        memory_id = connection.scalar(text("""
            INSERT INTO memories(org_id,owner_id,kind,content,structured,child_id,confirm_status)
            SELECT :org,:owner,:kind,:content,CAST(:data AS jsonb),:child,:status
            WHERE NOT EXISTS (SELECT 1 FROM memories WHERE org_id=:org AND owner_id=:owner AND kind=:kind
                AND child_id IS NOT DISTINCT FROM CAST(:child AS uuid) AND deleted_at IS NULL
                AND regexp_replace(content,'[[:space:][:punct:]]','','g')=regexp_replace(:content,'[[:space:][:punct:]]','','g')) RETURNING id
        """), {"org": req["org_id"], "owner": req["requester_id"], **item,
               "data": json.dumps({**item["structured"], "request_id": str(req["id"])}), "child": child,
               "status": "pending" if child else "confirmed"})
        if child and memory_id:
            connection.execute(text("""
                INSERT INTO notifications(org_id,recipient_id,request_id,kind,title,body,dedupe_key)
                VALUES (:org,:owner,:request,'memory_candidate','이 내용을 기억해 둘까요?',
                        '요청 상세에서 돌봄 메모를 확인해 주세요.',:key) ON CONFLICT (dedupe_key) DO NOTHING
            """), {"org": req["org_id"], "owner": req["requester_id"], "request": req["id"],
                   "key": f"memory_candidate:{memory_id}"})


@feature("보호자 기억")
def after_request(request_id):
    if not os.getenv("LLM_MODEL_MEMORY", "").strip():
        return
    req = None
    try:
        with transaction() as connection:
            req = dict(connection.execute(text("SELECT * FROM requests WHERE id=:id"), {"id": request_id}).mappings().one())
            if req["status"] not in ("sent_or_booked", "completed"):
                return
            if not re.search(r"선호|항상|보통|평소|매번|평일|매주|알레르기|낮잠|잠들|등원|안아|낯가림|분리불안", req["body"]):
                return
            # 국외 AI 전송에 동의하지 않은 보호자의 글은 기억 추출 모델에 보내지 않아요.
            if not _memory_kinds(connection, req):
                return
            names = list(connection.scalars(text("SELECT display_name FROM children WHERE org_id=:org"), {"org": req["org_id"]}))
        prompt = (Path(__file__).resolve().parents[5] / "agents/prompts/memory.md").read_text()
        reply = OpenAIModel("MEMORY").json(prompt, json.dumps({"parent_body": mask_sensitive(mask_child_names(req["body"], names)),
                                                              "untrusted_data_fields": ["parent_body"]}, ensure_ascii=False))
        with transaction() as connection:
            save_parent_candidates(connection, req, reply["candidates"], names)
    except Exception:
        memory_failed(None, "extract_parent", req)


def propose_rule(connection, owner_id, reason_code, rule_text, rule_json, *, org_id):
    """기억 AI 입구. 호출 쪽 트랜잭션에서 세 건 확인과 제안을 함께 저장해요."""
    validate_rule_json(rule_json)
    # INSERT 전에 직렬화해 서로 다른 요청에서 동시에 거절해도 세 번째를 빠뜨리지 않아요.
    connection.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
                       {"key": f"memory-rule:{org_id}:{owner_id}:{reason_code}"})
    existing = connection.scalar(text("""
        SELECT id FROM memory_rules WHERE org_id=:org AND owner_id=:owner AND reason_code=:code
          AND status IN ('proposed','active')
    """), {"org": org_id, "owner": owner_id, "code": reason_code})
    if existing is not None:
        return existing
    count = connection.scalar(text("""
        SELECT count(*) FROM memories WHERE org_id=:org AND owner_id=:owner
          AND kind='rejection_reason' AND reason_code=:code AND deleted_at IS NULL
          AND created_at>coalesce((
            SELECT max(decided_at) FROM memory_rules WHERE org_id=:org AND owner_id=:owner
              AND reason_code=:code AND status IN ('declined','off')), '-infinity'::timestamptz)
    """), {"org": org_id, "owner": owner_id, "code": reason_code})
    if count < REJECTION_RULE_THRESHOLD:
        return None
    rule_id = connection.scalar(text("""
        INSERT INTO memory_rules (org_id,owner_id,reason_code,rule_text,rule_json)
        VALUES (:org,:owner,:code,:text,CAST(:json AS jsonb))
        ON CONFLICT (owner_id,reason_code) WHERE status IN ('proposed','active') DO NOTHING RETURNING id
    """), {"org": org_id, "owner": owner_id, "code": reason_code, "text": rule_text,
           "json": json.dumps(rule_json)})
    if rule_id is None:
        return connection.scalar(text("""
            SELECT id FROM memory_rules WHERE org_id=:org AND owner_id=:owner AND reason_code=:code
              AND status IN ('proposed','active')
        """), {"org": org_id, "owner": owner_id, "code": reason_code})
    card = dict(connection.execute(text("""
        INSERT INTO cards (org_id,kind,status,assignee_id,subject_type,subject_id,draft)
        VALUES (:org,'rule_proposal','pending',:owner,'memory_rule',:rule,CAST(:draft AS jsonb)) RETURNING *
    """), {"org": org_id, "owner": owner_id, "rule": rule_id,
           "draft": json.dumps({"summary": rule_text})}).mappings().one())
    record(connection, None, "created", card=card, actor_type="agent", agent_name="memory")
    return rule_id


def remember_rejection(connection, user, card, decision, reason_code, reason_text):
    if user.role != "teacher":
        return
    connection.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
                       {"key": f"memory-rule:{user.org_id}:{user.id}:{reason_code}"})
    classroom_id = connection.scalar(text("SELECT classroom_id FROM requests WHERE id=:id AND org_id=:org"),
                                     {"id": card["request_id"], "org": user.org_id})
    name_query = "SELECT display_name FROM children WHERE org_id=:org"
    if classroom_id is not None:
        name_query += " AND classroom_id=:class"
    names = connection.scalars(text(name_query), {"org": user.org_id, "class": classroom_id})
    content = mask_child_names(reason_text or "거절 이유: " + reason_code, names)
    connection.execute(text("""
        INSERT INTO memories (org_id,owner_id,kind,reason_code,content,structured,source_card_id,created_at)
        VALUES (:org,:owner,'rejection_reason',:code,:content,CAST(:structured AS jsonb),:card,clock_timestamp())
    """), {"org": user.org_id, "owner": user.id, "code": reason_code,
           "content": content,
           "structured": json.dumps({"decision": decision, "card_version": card["version"]}), "card": card["id"]})
    # other 자유 글을 같은 선호로 단정하지 않고, 민감한 글을 규칙에 옮기지 않아요.
    if reason_code in REJECTION_RULE_TEXTS:
        for attempt in range(2):
            try:
                with connection.begin_nested():
                    propose_rule(connection, user.id, reason_code, REJECTION_RULE_TEXTS[reason_code],
                                 {"reason_code": reason_code}, org_id=user.org_id)
                break
            except Exception as error:
                invalid = isinstance(error, ApiError) and error.code == "VALIDATION_FAILED"
                if invalid or attempt == 1:
                    events.record(connection, None, "tool_failed", card=card, actor_type="agent", agent_name="memory",
                                  tool="propose_rule", code="VALIDATION_FAILED" if invalid else "SAVE_FAILED")
                    break


def list_memories(user, kind, page, size, sort):
    values = {"org": user.org_id, "owner": user.id, "parent": user.role == "parent"}
    with transaction() as connection:
        items = [dict(row) for row in connection.execute(text("""
            SELECT m.id,m.kind,m.reason_code,m.content,m.structured,m.created_at,m.child_id,
                   c.display_name AS child_name,m.confirm_status,m.confirmed_at
            FROM memories m LEFT JOIN children c ON (c.id,c.org_id)=(m.child_id,m.org_id) WHERE
        """ + VISIBLE_MEMORY), values).mappings()]
        saved, rules = [], []
        if user.role == "teacher":
            saved = [dict(row) for row in connection.execute(text("""
                SELECT id,question,answer,status,created_at AS approved_at FROM saved_answers
                WHERE org_id=:org AND approved_by=:owner ORDER BY created_at DESC,id
            """), values).mappings()]
            rules = [dict(row) for row in connection.execute(text("""
                SELECT id,reason_code,rule_text,rule_json,status,created_at FROM memory_rules
                WHERE org_id=:org AND owner_id=:owner ORDER BY created_at DESC,id
            """), values).mappings()]
    return memory_page(items, saved, rules, kind, page, size, sort)


def delete(user, memory_id):
    with transaction() as connection:
        row = connection.execute(text("""
            UPDATE memories m SET deleted_at=now(),content='',structured='{}'::jsonb
            WHERE m.id=:id AND """ + VISIBLE_MEMORY + " RETURNING id"),
            {"id": memory_id, "org": user.org_id, "owner": user.id, "parent": user.role == "parent"}).one_or_none()
        scope._checked(user, row, row is not None, "memory", memory_id)


def confirm(user, memory_id, decision):
    with transaction() as connection:
        row = connection.execute(text("SELECT m.* FROM memories m WHERE m.id=:id AND " + VISIBLE_MEMORY + " FOR UPDATE"),
                                 {"id": memory_id, "org": user.org_id, "owner": user.id, "parent": user.role == "parent"}).mappings().one_or_none()
        scope._checked(user, row, row is not None and row["kind"] == "care_note" and user.role == "parent",
                       "memory", memory_id)
        if row["confirm_status"] != "pending":
            raise ApiError(409, "INVALID_TRANSITION")
        return dict(connection.execute(text("""
            UPDATE memories SET confirm_status=:status,confirmed_at=CASE WHEN :remember THEN now() END,
                content=CASE WHEN :remember THEN content ELSE '' END,
                structured=CASE WHEN :remember THEN structured ELSE '{}'::jsonb END
            WHERE id=:id RETURNING id,confirm_status,confirmed_at
        """), {"id": memory_id, "status": "confirmed" if decision == "remember" else "discarded",
               "remember": decision == "remember"}).mappings().one())


def candidates_for_request(user, request_id):
    if user.role != "parent":
        return []
    with transaction() as connection:
        return [dict(row) for row in connection.execute(text("""
            SELECT m.id,c.display_name AS child_name,m.content FROM memories m
            JOIN children c ON (c.id,c.org_id)=(m.child_id,m.org_id)
            WHERE m.kind='care_note' AND m.confirm_status='pending' AND m.structured->>'request_id'=:request
              AND """ + VISIBLE_MEMORY), {"request": str(request_id), "org": user.org_id, "owner": user.id, "parent": True}).mappings()]
