"""가상 기억·규칙·승인 답. demo → documents 뒤에 실행하며 기존 결정·삭제는 보존해요."""

import json
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid5

from sqlalchemy import text

from app.core.schedule import KST
from app.mock import seed
from app.modules.documents import embedding
from app.modules.documents.parsing import parse_document
from app.modules.memories.memories import propose_rule

FIXTURES = Path(__file__).resolve().parents[2] / "data/fixtures/kg-demo-01"
DATA = json.loads((FIXTURES / "memories/memories.json").read_text(encoding="utf-8"))
USERS = {user["login_id"]: user["id"] for user in seed.USERS}


def seed_memories(connection):
    # 예약한 양수 ID는 DELETE API의 ge=1을 지키고, 본문·structured가 지워져도 같은 행을 찾아요.
    connection.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('kg-demo-01:memory-seed',0))"))
    now, pending = datetime.now(KST), []
    for index, answer in enumerate(DATA["saved_answers"]):
        parsed = parse_document((FIXTURES / answer["document"]).read_text(encoding="utf-8"))
        source = connection.execute(text("""
            SELECT d.id AS document, c.id AS chunk FROM documents d JOIN document_chunks c
              ON (c.document_id,c.org_id)=(d.id,d.org_id)
            WHERE d.org_id=:org AND d.content_sha256=:sha AND d.status='active'
              AND position(:quote in c.content)>0 ORDER BY c.id LIMIT 1
        """), {"org": seed.ORG, "sha": parsed.content_sha256, "quote": answer["quote"]}).mappings().first()
        if source is None:
            print(f"경고: 근거 문서가 없어 승인 답 건너뜀: {answer['key']}")
            continue
        values = {**answer, **source, "org": seed.ORG, "teacher": seed.TEACHER, "parent": seed.PARENT,
                  "class": seed.CLASS_STAR, "child": seed.CHILD,
                  "scope": seed.CLASS_STAR if answer["classroom"] == "C4" else None,
                  "request": uuid5(seed.ORG, answer["key"] + ":request"),
                  "card": uuid5(seed.ORG, answer["key"] + ":card"),
                  "id": uuid5(seed.ORG, answer["key"] + ":answer"),
                  "created": now-timedelta(days=20-index % 20, minutes=index),
                  "sent": now-timedelta(days=20-index % 20, minutes=index-10),
                  "draft": json.dumps({"text": answer["answer"]}),
                  "edited": json.dumps({"text": answer["answer"]}) if answer["edit"] else None,
                  "decision": "edit_approve" if answer["edit"] else "approve"}
        values["created"] = max(values["created"], datetime.combine(parsed.meta.effective_from, now.time(), KST))
        values["sent"] = values["created"] + timedelta(minutes=10)
        inserted = connection.scalar(text("""
            INSERT INTO requests(id,org_id,classroom_id,child_id,requester_id,client_request_id,type,title,body,
                                 status,assignee_id,created_at,updated_at,closed_at)
            VALUES (:request,:org,:class,:child,:parent,:key,'inquiry',:question,:question,'completed',:teacher,
                    :created,:sent,:sent) ON CONFLICT DO NOTHING RETURNING id
        """), values)
        if inserted:
            connection.execute(text("""
                INSERT INTO cards(id,org_id,request_id,kind,status,assignee_id,draft,version,created_at,updated_at,closed_at)
                VALUES (:card,:org,:request,'reply_draft','done',:teacher,CAST(:draft AS jsonb),3,:created,:sent,:sent)
            """), values)
            connection.execute(text("""
                INSERT INTO approvals(card_id,org_id,card_version,decided_by,decision,edited_content,created_at)
                VALUES (:card,:org,1,:teacher,:decision,CAST(:edited AS jsonb),:sent)
            """), values)
            connection.execute(text("""
                INSERT INTO request_messages(org_id,request_id,sender_type,sender_id,body,created_at)
                VALUES (:org,:request,'user',:parent,:question,:created),(:org,:request,'user',:teacher,:answer,:sent)
            """), values)
            connection.execute(text("""
                INSERT INTO card_evidence(card_id,org_id,chunk_id,rank,quote) VALUES (:card,:org,:chunk,1,:quote)
            """), values)
            for action, actor, at in (("created", seed.PARENT, values["created"]),
                                      ("drafted", seed.TEACHER, values["created"]),
                                      ("approved", seed.TEACHER, values["sent"]),
                                      ("sent", seed.TEACHER, values["sent"]),
                                      ("completed", seed.TEACHER, values["sent"])):
                connection.execute(text("""
                    INSERT INTO events(org_id,request_id,card_id,actor_type,actor_id,action,detail,created_at)
                    VALUES (:org,:request,:card,'user',:actor,:action,CAST(:detail AS jsonb),:at)
                """), {**values, "actor": actor, "action": action, "at": at,
                       "detail": json.dumps({"is_virtual": True, "seed_key": answer["key"],
                                             "decision": values["decision"],
                                             "text": answer["answer"].removesuffix(" 궁금한 점은 언제든 알려 주세요.")
                                             if action == "drafted" and answer["edit"] else answer["answer"]})})
        if not connection.scalar(text("SELECT EXISTS(SELECT 1 FROM saved_answers WHERE id=:id)"), values):
            pending.append(values)
    for index, memory in enumerate(DATA["memories"]):
        source = uuid5(seed.ORG, memory["source_answer"] + ":card") if memory.get("source_answer") else None
        if source and not connection.scalar(text("SELECT EXISTS(SELECT 1 FROM cards WHERE id=:id)"), {"id": source}):
            source = None
        connection.execute(text("""
            INSERT INTO memories(id,org_id,owner_id,kind,reason_code,content,structured,source_card_id,created_at)
            OVERRIDING SYSTEM VALUE
            VALUES (:id,:org,:owner,:kind,:reason_code,:content,CAST(:structured AS jsonb),:source,:at)
            ON CONFLICT (id) DO UPDATE SET source_card_id=coalesce(memories.source_card_id,EXCLUDED.source_card_id)
            WHERE memories.deleted_at IS NULL
        """), {**memory, "id": 990200001+index, "org": seed.ORG, "owner": USERS[memory["owner"]],
               "reason_code": memory.get("reason_code"), "source": source,
               "structured": json.dumps({**memory["structured"], "is_virtual": True}),
               "at": connection.scalar(text("SELECT closed_at+interval '1 minute' FROM cards WHERE id=:id"),
                                        {"id": source}) if source else now-timedelta(days=20-index % 20)})
    for rule in DATA["rules"]:
        values = {**rule, "id": uuid5(seed.ORG, rule["key"]), "org": seed.ORG, "owner": USERS[rule["owner"]],
                  "json": json.dumps({**rule["rule_json"], "seed_key": rule["key"]}),
                  "created": now-timedelta(days=2), "decided": now-timedelta(days=1)}
        if rule["status"] == "proposed":
            if not connection.scalar(text("SELECT EXISTS(SELECT 1 FROM memory_rules WHERE org_id=:org "
                                          "AND owner_id=:owner AND rule_json->>'seed_key'=:key)"), values):
                propose_rule(connection, values["owner"], rule["reason_code"], rule["rule_text"],
                             json.loads(values["json"]), org_id=seed.ORG)
        else:
            connection.execute(text("""
                INSERT INTO memory_rules(id,org_id,owner_id,reason_code,rule_text,rule_json,status,created_at,decided_at)
                VALUES (:id,:org,:owner,:reason_code,:rule_text,CAST(:json AS jsonb),:status,:created,:decided)
                ON CONFLICT DO NOTHING
            """), values)
    vectors = embedding.embed([answer["question"] for answer in pending]) if pending else []
    if len(vectors) != len(pending) or any(len(vector) != 1024 for vector in vectors):
        print("경고: EMBEDDING_MODEL=BAAI/bge-m3 또는 실제 모델을 사용할 수 없어 saved_answers는 건너뜀")
        return 0
    for values, vector in zip(pending, vectors, strict=True):
        connection.execute(text("""
            INSERT INTO saved_answers(id,org_id,classroom_id,question,question_embedding,embedding_model,
                                      embedding_version,answer,source_card_id,approved_by,created_at)
            VALUES (:id,:org,:scope,:question,CAST(:vector AS vector),:model,:version,:answer,:card,:teacher,:sent)
            ON CONFLICT DO NOTHING
        """), {**values, "vector": str(vector), "model": embedding.MODEL, "version": embedding.VERSION})
        connection.execute(text("""
            INSERT INTO saved_answer_sources(saved_answer_id,org_id,document_id)
            VALUES (:id,:org,:document) ON CONFLICT DO NOTHING
        """), values)
    return len(pending)


if __name__ == "__main__":
    from app.core.db import transaction

    with transaction() as connection:
        count = seed_memories(connection)
    print(f"가상 기억 시드 완료: 기억 {len(DATA['memories'])}개·규칙 {len(DATA['rules'])}개, 새 승인 답 {count}개")
