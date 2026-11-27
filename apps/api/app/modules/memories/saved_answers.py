"""승인 답은 작성 표현의 참고 자료예요. 근거 목록에는 넣지 않아요."""

import json
import logging
from datetime import datetime

from sqlalchemy import text

from agents.guardrails.sensitive import mask_sensitive
from app.core.constants import SAVED_ANSWER_MIN_SIMILARITY
from app.core.db import transaction
from app.core.memory_rules import mask_child_names
from app.core.schedule import KST
from app.modules.documents import embedding

log = logging.getLogger(__name__)


def masked(org_id, value):
    with transaction() as connection:
        names = list(connection.scalars(text("SELECT display_name FROM children WHERE org_id=:org"),
                                        {"org": org_id}))
    return mask_sensitive(mask_child_names(value, names))


def masked_question(req):
    return masked(req["org_id"], req["body"])


def remember_answer(user, card, req, content):
    if (req["type"] != "inquiry" or card["draft"].get("no_evidence") or card["draft"].get("conflict")
            or not embedding.enabled()):
        return
    with transaction() as connection:
        sources = list(connection.scalars(text("""
            SELECT DISTINCT ch.document_id FROM card_evidence e JOIN document_chunks ch
              ON (ch.id,ch.org_id)=(e.chunk_id,e.org_id)
            WHERE e.org_id=:org AND e.card_id=:card
        """), {"org": user.org_id, "card": card["id"]}))
    if not sources:
        return
    question = masked_question(req)
    # 다른 가정 질문의 초안 참고로 쓰이므로 답도 아이 이름·민감정보 형식을 가려 저장해요.
    answer = masked(req["org_id"], content["text"])
    vectors = embedding.embed([question])
    if len(vectors) != 1 or len(vectors[0]) != 1024:
        return
    with transaction() as connection:
        # 문서 변경 트리거와 직렬화해 무효화 직전에 저장한 답도 놓치지 않아요.
        active = connection.scalars(text("""
            SELECT id FROM documents WHERE org_id=:org AND id=ANY(CAST(:sources AS uuid[]))
              AND status='active' FOR SHARE
        """), {"org": user.org_id, "sources": sources}).all()
        if len(active) != len(sources):
            return
        saved_id = connection.scalar(text("""
            INSERT INTO saved_answers(org_id,classroom_id,question,question_embedding,embedding_model,
                embedding_version,answer,source_card_id,approved_by,created_at)
            SELECT :org,:class,:question,CAST(:vector AS vector),:model,:version,:answer,:card,:owner,a.created_at
            FROM approvals a WHERE a.org_id=:org AND a.card_id=:card AND a.card_version=:card_version
              AND a.decided_by=:owner AND a.decision IN ('approve','edit_approve') RETURNING id
        """), {"org": user.org_id, "class": req["classroom_id"], "question": question,
               "vector": json.dumps(vectors[0]), "model": embedding.MODEL, "version": embedding.VERSION,
               "answer": answer, "card": card["id"], "owner": user.id, "card_version": card["version"]})
        if saved_id is not None:
            for source in sources:
                connection.execute(text("""
                    INSERT INTO saved_answer_sources(saved_answer_id,org_id,document_id) VALUES (:id,:org,:doc)
                """), {"id": saved_id, "org": user.org_id, "doc": source})


def find_saved_answer(req):
    if req["type"] != "inquiry" or not embedding.enabled():
        return None
    try:
        vectors = embedding.embed([masked_question(req)])
        if len(vectors) != 1 or len(vectors[0]) != 1024:
            return None
        with transaction() as connection:
            row = connection.execute(text("""
                SELECT sa.question,sa.answer,sa.created_at AS approved_at FROM saved_answers sa
                WHERE sa.org_id=:org AND (sa.classroom_id IS NULL OR sa.classroom_id=CAST(:class AS uuid))
                  AND sa.status='active' AND sa.embedding_model=:model AND sa.embedding_version=:version
                  AND 1-(sa.question_embedding <=> CAST(:vector AS vector))>=:threshold
                  AND EXISTS (SELECT 1 FROM saved_answer_sources s WHERE s.org_id=:org AND s.saved_answer_id=sa.id)
                  AND NOT EXISTS (
                    SELECT 1 FROM saved_answer_sources s JOIN documents d ON (d.id,d.org_id)=(s.document_id,s.org_id)
                    WHERE s.org_id=:org AND s.saved_answer_id=sa.id AND (
                      d.status<>'active' OR d.ingest_status<>'succeeded' OR d.visibility NOT IN ('parents','all')
                      OR d.effective_from>:today OR d.effective_to<:today
                      OR (EXISTS (SELECT 1 FROM document_classrooms dc WHERE dc.org_id=:org AND dc.document_id=d.id)
                          AND NOT EXISTS (SELECT 1 FROM document_classrooms dc WHERE dc.org_id=:org
                                          AND dc.document_id=d.id AND dc.classroom_id=CAST(:class AS uuid)))))
                ORDER BY sa.question_embedding <=> CAST(:vector AS vector),sa.created_at DESC,sa.id LIMIT 1
            """), {"org": req["org_id"], "class": req["classroom_id"], "model": embedding.MODEL,
                   "version": embedding.VERSION, "vector": json.dumps(vectors[0]),
                   "today": datetime.now(KST).date(), "threshold": SAVED_ANSWER_MIN_SIMILARITY}).mappings().one_or_none()
        return dict(row) if row else None
    except Exception:
        log.warning("승인 답 검색 실패. 이번 자료만으로 작성해요.")
        return None
