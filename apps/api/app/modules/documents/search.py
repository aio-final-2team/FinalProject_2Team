"""`search_documents` 도구(DB): 원 자료에서 근거 조각을 찾는다 (T20 → T33, 계약표 4장, API 5.4).

입력: `kindergarten_id`(문맥의 기관 ID 그대로), `doc_type`(notice·schedule·menu·policy 중 하나), `query`,
백엔드 값 `classroom_id`(학부모 아이의 반; 원 전체 + 그 반 자료만. 교직원은 비움), `top_k`(기본 5).
출력: `chunks[] { chunk_id, document_title, location, effective_from, content, score }`.

지금은 **낱말 검색**이에요(11/23 결정). 질문을 낱말로 나눠(조사 떼기) 조각·제목·위치에 몇 개가 나오는지로
점수(0~1)를 매겨요. 벡터 검색(bge-m3, `document_chunks.embedding`)은 T33에서 같은 함수 뒤에 붙여요.
사용 중(`status = active`)이고 적재가 끝난(`ingest_status = succeeded`) 문서만, 적용 기간 안의 판만 찾아요.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from uuid import UUID

from sqlalchemy import text

from app.core.db import transaction
from app.core.errors import ApiError
from app.core.schedule import KST
from agents.guardrails.injection import suspicious_chunk
from . import embedding

DOC_TYPES = ("notice", "schedule", "menu", "policy")
# 낱말 끝에 붙는 조사·어미. 긴 것부터 떼요
_TAILS = sorted(["은", "는", "이", "가", "을", "를", "에", "에서", "에게", "도", "의", "와", "과", "로", "으로", "까지", "부터",
                 "요", "나요", "까요", "인가요", "인지", "해요", "하나요", "있나요", "없나요", "언제", "뭐예요", "이에요", "예요"],
                key=len, reverse=True)
_STOP = {"언제", "언제부터", "언제까지", "어떻게", "무엇", "뭐", "어디", "알려", "주세요", "궁금", "있어요", "해요",
         "하나", "있나", "되나", "우리", "아이"}


def terms(query: str) -> list[str]:
    """질문을 검색 낱말로. 2글자 이상, 조사를 떼고, 묻는 말은 뺀다. 숫자(12월·24일)는 남긴다."""
    out = []
    for word in re.findall(r"[0-9A-Za-z가-힣]+", query):
        for tail in _TAILS:
            if len(word) > len(tail) + 1 and word.endswith(tail):
                word = word[: -len(tail)]
                break
        if (len(word) >= 2 or word.isdigit()) and word not in _STOP and word not in out:
            out.append(word)
    return out


def score(words: list[str], title: str, location: str, content: str) -> float:
    """찾은 낱말 비율(0~1). 제목·위치에 있으면 조금 더 쳐요."""
    if not words:
        return 0.0
    hay = f"{title}\n{location}\n{content}"
    found = [w for w in words if w in hay]
    bonus = 0.1 * sum(1 for w in found if w in title or w in location)
    return round(min(1.0, len(found) / len(words) + bonus), 3)


def search_documents(user, kindergarten_id: str, doc_type: str, query: str, classroom_id=None, top_k: int = 5,
                     on_date: date | None = None) -> dict:
    if str(kindergarten_id) != str(user.org_id):
        raise ApiError(404, "NOT_FOUND")  # 다른 기관 자료는 있다고도 알리지 않는다
    if doc_type not in DOC_TYPES or not query.strip() or not 1 <= top_k <= 20:
        raise ApiError(422, "VALIDATION_FAILED")
    words = terms(query)
    today = on_date or datetime.now(KST).date()
    parent = user.role == "parent"
    query_vector = embedding.embed([query]) if embedding.enabled() else []
    vector = "[" + ",".join(map(str, query_vector[0])) + "]" if query_vector and len(query_vector[0]) == 1024 else None
    with transaction() as connection:
        if parent:
            if classroom_id is not None:
                try:
                    classroom_id = UUID(str(classroom_id))
                except ValueError as error:
                    raise ApiError(404, "NOT_FOUND") from error
            allowed_classes = set(connection.scalars(text("""
                SELECT c.classroom_id FROM child_guardians cg
                JOIN children c ON (c.id, c.org_id)=(cg.child_id, cg.org_id)
                WHERE cg.org_id=:org AND cg.user_id=:user
            """), {"org": user.org_id, "user": user.id}))
            if classroom_id is not None and classroom_id not in allowed_classes:
                raise ApiError(404, "NOT_FOUND")
        rows = connection.execute(text("""
            SELECT ch.id AS chunk_id, d.title AS document_title, ch.location, d.effective_from, ch.content,
                   CASE WHEN CAST(:vector AS vector) IS NOT NULL AND ch.embedding_version = :version
                        THEN 1 - (ch.embedding <=> CAST(:vector AS vector)) ELSE NULL END AS vector_score
            FROM document_chunks ch JOIN documents d ON (d.id, d.org_id) = (ch.document_id, ch.org_id)
            WHERE d.org_id = :org AND d.doc_type = :doc_type AND d.status = 'active' AND d.ingest_status = 'succeeded'
              -- 시행 전 문서(미리 공지한 12월 일정 등)도 찾는다. 기간이 끝난 문서만 뺀다. 같은 점수면 지금 시행 중인 문서가 앞.
              AND (d.effective_to IS NULL OR d.effective_to >= :today)
              AND (NOT :parent OR d.visibility IN ('parents', 'all'))
              AND (NOT :parent OR NOT EXISTS (SELECT 1 FROM document_classrooms dc
                                  WHERE (dc.document_id, dc.org_id) = (d.id, d.org_id))
                   OR EXISTS (SELECT 1 FROM document_classrooms dc
                              WHERE (dc.document_id, dc.org_id) = (d.id, d.org_id)
                                AND dc.classroom_id = ANY(CAST(:allowed_classes AS uuid[]))))
              AND (CAST(:classroom AS uuid) IS NULL
                   OR NOT EXISTS (SELECT 1 FROM document_classrooms dc
                                  WHERE (dc.document_id, dc.org_id) = (d.id, d.org_id))
                   OR EXISTS (SELECT 1 FROM document_classrooms dc
                              WHERE (dc.document_id, dc.org_id) = (d.id, d.org_id)
                                AND dc.classroom_id = CAST(:classroom AS uuid)))
        """), {"org": user.org_id, "doc_type": doc_type, "today": today, "parent": parent,
               "allowed_classes": list(allowed_classes) if parent else [],
               "classroom": str(classroom_id) if classroom_id else None,
               "vector": vector, "version": embedding.VERSION}).mappings().all()
    ranked = []
    for row in rows:
        if suspicious_chunk(row["content"]):
            continue
        lexical = score(words, row["document_title"], row["location"] or "", row["content"])
        value = round(0.5 * lexical + 0.5 * max(0.0, row["vector_score"]), 3) if row["vector_score"] is not None else lexical
        if value > 0:
            ranked.append({key: row[key] for key in ("chunk_id", "document_title", "location", "effective_from", "content")}
                          | {"location": row["location"] or "본문", "score": value})
    def order(row):
        # 점수가 같으면 지금 시행 중인 문서, 제목·위치에 낱말이 있는 조각, 낱말이 더 많이 나오는 조각, 새 판 순서
        heads = sum((w in row["document_title"]) + (w in row["location"]) for w in words)
        upcoming = row["effective_from"] is not None and row["effective_from"] > today
        return (-row["score"], upcoming, -heads, -sum(row["content"].count(w) for w in words),
                -(row["effective_from"] or date.min).toordinal(), row["chunk_id"])

    ranked.sort(key=order)
    return {"chunks": ranked[:top_k]}
