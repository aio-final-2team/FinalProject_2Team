from copy import deepcopy
from uuid import uuid4
import os
from math import sqrt

from app.core.constants import (REJECTION_RULE_TEXTS, REJECTION_RULE_THRESHOLD, TONE_LIMIT, TONE_READ_LIMIT,
                                SAVED_ANSWER_MIN_SIMILARITY)
from app.core.errors import ApiError
from app.core.memory_rules import mask_child_names, validate_rule_json, tone_contents
from app.mock import store
from app.mock.records import Memory, Rule
from agents.guardrails.sensitive import mask_sensitive
from app.modules.documents.embedding import MODEL, VERSION


def remember_answer(user, card, req, content):
    if (os.getenv("EMBEDDING_MODEL", "") != MODEL or req.type != "inquiry"
            or card.draft.get("no_evidence") or card.draft.get("conflict")):
        return
    sources = {store.state().chunks[e.chunk_id].document_id for e in store.state().evidence
               if e.org_id == user.org_id and e.card_id == card.id}
    if not sources or any(store.state().documents[doc].status != "active" for doc in sources):
        return
    names = [c.display_name for c in store.state().children.values() if c.org_id == user.org_id]
    saved_id = uuid4()
    store.state().saved_answers[saved_id] = {
        "id": saved_id, "org_id": user.org_id, "classroom_id": req.classroom_id,
        "question": mask_sensitive(mask_child_names(req.body, names)), "answer": content["text"],
        "source_card_id": card.id, "approved_by": user.id, "status": "active",
        # 모의 고정 벡터. 모델 호출·질문 의미 판정은 하지 않아요.
        "question_embedding": [1.0] + [0.0] * 1023, "embedding_model": MODEL, "embedding_version": VERSION,
        "created_at": store.state().approvals[-1].created_at}
    store.state().saved_answer_sources[saved_id] = sources


def find_saved_answer(req, vector):
    if req.type != "inquiry" or os.getenv("EMBEDDING_MODEL", "") != MODEL:
        return None
    today, rows = store.now().date(), []
    for row in store.state().saved_answers.values():
        sources = store.state().saved_answer_sources.get(row["id"], set())
        docs = [store.state().documents[d] for d in sources]
        if (row["org_id"] != req.org_id or row["classroom_id"] not in (None, req.classroom_id)
                or row["status"] != "active" or not sources or row["embedding_model"] != MODEL
                or row["embedding_version"] != VERSION or any(d.org_id != req.org_id or d.status != "active"
                    or d.ingest_status != "succeeded" or d.visibility not in ("parents", "all")
                    or (d.effective_from and d.effective_from > today) or (d.effective_to and d.effective_to < today)
                    or (store.state().document_classrooms.get(d.id)
                        and req.classroom_id not in store.state().document_classrooms[d.id]) for d in docs)):
            continue
        norm = sqrt(sum(v*v for v in vector) * sum(v*v for v in row["question_embedding"]))
        similarity = sum(a*b for a, b in zip(vector, row["question_embedding"])) / norm if norm else 0
        if similarity >= SAVED_ANSWER_MIN_SIMILARITY:
            rows.append((similarity, row))
    if not rows:
        return None
    row = max(rows, key=lambda item: (item[0], item[1]["created_at"], item[1]["id"]))[1]
    return {"question": row["question"], "answer": row["answer"], "approved_at": row["created_at"]}


def load_tones(org_id, owner_id):
    rows = sorted((m for m in store.state().memories.values() if m.org_id == org_id and m.owner_id == owner_id
                   and m.kind == "tone" and m.deleted_at is None), key=lambda m: (m.created_at, m.id), reverse=True)
    return [{"kind": m.kind, "content": m.content} for m in rows[:TONE_READ_LIMIT]]


def save_tones(user, card, candidates, names):
    # 모의는 저장만 흉내 내고 모델로 후보를 만들지 않아요.
    with store._lock:
        for content in tone_contents(candidates, names):
            if any(m.org_id == user.org_id and m.owner_id == user.id and m.kind == "tone"
                   and m.deleted_at is None and m.content == content for m in store.state().memories.values()):
                continue
            row = Memory(store.state().next_int(), user.org_id, user.id, "tone", content,
                         structured={"source": "edit_approve", "card_version": card["version"]}, source_card_id=card["id"])
            store.state().memories[row.id] = row
        rows = sorted((m for m in store.state().memories.values() if m.org_id == user.org_id and m.owner_id == user.id
                       and m.kind == "tone" and m.deleted_at is None), key=lambda m: (m.created_at, m.id), reverse=True)
        for row in rows[TONE_LIMIT:]:
            row.deleted_at = store.now()


def propose_rule(owner_id, reason_code, rule_text, rule_json, *, org_id):
    validate_rule_json(rule_json)
    with store._lock:
        existing = next((r.id for r in store.state().rules.values() if r.org_id == org_id
                         and r.owner_id == owner_id and r.reason_code == reason_code
                         and r.status in ("proposed", "active")), None)
        if existing is not None:
            return existing
        declined_at = max((r.decided_at for r in store.state().rules.values() if r.org_id == org_id
                           and r.owner_id == owner_id and r.reason_code == reason_code
                           and r.status == "declined" and r.decided_at is not None), default=None)
        count = sum(m.org_id == org_id and m.owner_id == owner_id and m.kind == "rejection_reason"
                    and m.reason_code == reason_code and m.deleted_at is None
                    and (declined_at is None or m.created_at > declined_at) for m in store.state().memories.values())
        if count < REJECTION_RULE_THRESHOLD:
            return None
        rule = Rule(uuid4(), org_id, owner_id, reason_code, rule_text, deepcopy(rule_json))
        store.state().rules[rule.id] = rule
        card = store.Card(uuid4(), org_id, None, "rule_proposal", assignee_id=owner_id,
                          subject_type="memory_rule", subject_id=rule.id, draft={"summary": rule_text})
        store.state().cards[card.id] = card
        store.add_event(None, "created", card=card, actor_type="agent", agent_name="memory")
        return rule.id


def remember_rejection(user, card, decision, reason_code, reason_text):
    if user.role != "teacher":
        return
    with store._lock:
        req = store.state().requests.get(card.request_id)
        classroom_id = req.classroom_id if req else None
        content = mask_child_names(reason_text or "거절 이유: " + reason_code,
                                  (c.display_name for c in store.state().children.values() if c.org_id == user.org_id
                                   and (classroom_id is None or c.classroom_id == classroom_id)))
        memory = Memory(store.state().next_int(), user.org_id, user.id, "rejection_reason",
                        content, reason_code=reason_code,
                        structured={"decision": decision, "card_version": card.version},
                        source_card_id=card.id, created_at=store.now())
        store.state().memories[memory.id] = memory
        if reason_code in REJECTION_RULE_TEXTS:
            state = store.state()
            for attempt in range(2):
                saved = (dict(state.rules), dict(state.cards), list(state.events), dict(state.notifications), state._seq)
                try:
                    propose_rule(user.id, reason_code, REJECTION_RULE_TEXTS[reason_code],
                                 {"reason_code": reason_code}, org_id=user.org_id)
                    break
                except Exception as error:
                    state.rules, state.cards, state.events, state.notifications, state._seq = saved
                    invalid = isinstance(error, ApiError) and error.code == "VALIDATION_FAILED"
                    if invalid or attempt == 1:
                        store.add_event(None, "tool_failed", card=card, actor_type="agent", agent_name="memory",
                                        tool="propose_rule", code="VALIDATION_FAILED" if invalid else "SAVE_FAILED")
                        break


def list_memories(user, kind, page, size, sort):
    with store._lock:
        items = [m for m in store.state().memories.values() if m.org_id == user.org_id and m.owner_id == user.id
                 and m.deleted_at is None and (kind is None or m.kind == kind)]
        items.sort(key=lambda m: (m.created_at, m.id), reverse=sort.startswith("-"))
        return {"items": [{key: deepcopy(getattr(m, key)) for key in
                           ("id", "kind", "reason_code", "content", "structured", "created_at")}
                          for m in items[(page-1)*size:page*size]], "total": len(items), "page": page, "size": size}


def delete(user, memory_id):
    with store._lock:
        memory = store.state().memories.get(memory_id)
        if memory is None or memory.org_id != user.org_id or memory.owner_id != user.id or memory.deleted_at is not None:
            store.deny(user)
        memory.deleted_at = store.now()
        memory.content, memory.structured = "", {}
