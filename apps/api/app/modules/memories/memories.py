import json

from sqlalchemy import text

from app.core import scope
from app.core.constants import REJECTION_RULE_TEXTS, REJECTION_RULE_THRESHOLD
from app.core.db import transaction
from app.core.errors import ApiError
from app.core.memory_rules import mask_child_names, validate_rule_json
from app.modules.requests import events
from app.modules.requests.events import record


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
              AND reason_code=:code AND status='declined'), '-infinity'::timestamptz)
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
    condition = "org_id=:org AND owner_id=:owner AND deleted_at IS NULL"
    if kind is not None:
        condition += " AND kind=:kind"
    values = {"org": user.org_id, "owner": user.id, "kind": kind, "limit": size, "offset": (page-1)*size}
    direction = "DESC" if sort.startswith("-") else "ASC"
    with transaction() as connection:
        total = connection.scalar(text("SELECT count(*) FROM memories WHERE " + condition), values)
        if values["offset"] >= total:
            return {"items": [], "total": total, "page": page, "size": size}
        items = connection.execute(text("""
            SELECT id, kind, reason_code, content, structured, created_at FROM memories WHERE
        """ + condition + f" ORDER BY created_at {direction}, id {direction} LIMIT :limit OFFSET :offset"),
                                   values).mappings().all()
    return {"items": [dict(row) for row in items], "total": total, "page": page, "size": size}


def delete(user, memory_id):
    with transaction() as connection:
        row = connection.execute(text("""
            UPDATE memories SET deleted_at=now(),content='',structured='{}'::jsonb
            WHERE id=:id AND org_id=:org AND owner_id=:owner AND deleted_at IS NULL RETURNING id
        """), {"id": memory_id, "org": user.org_id, "owner": user.id}).mappings().one_or_none()
    scope._checked(user, row, row is not None, "memory", memory_id)
