from copy import deepcopy
from uuid import uuid4

from app.core.constants import REJECTION_RULE_TEXTS, REJECTION_RULE_THRESHOLD
from app.mock import store
from app.mock.records import Memory, Rule


def propose_rule(owner_id, reason_code, rule_text, rule_json, *, org_id):
    with store._lock:
        existing = next((r.id for r in store.state().rules.values() if r.org_id == org_id
                         and r.owner_id == owner_id and r.reason_code == reason_code
                         and r.status in ("proposed", "active")), None)
        if existing is not None:
            return existing
        count = sum(m.org_id == org_id and m.owner_id == owner_id and m.kind == "rejection_reason"
                    and m.reason_code == reason_code and m.deleted_at is None for m in store.state().memories.values())
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
        memory = Memory(store.state().next_int(), user.org_id, user.id, "rejection_reason",
                        reason_text or "거절 이유: " + reason_code, reason_code=reason_code,
                        structured={"decision": decision, "card_version": card.version},
                        source_card_id=card.id, created_at=store.now())
        store.state().memories[memory.id] = memory
        if reason_code in REJECTION_RULE_TEXTS:
            propose_rule(user.id, reason_code, REJECTION_RULE_TEXTS[reason_code],
                         {"reason_code": reason_code}, org_id=user.org_id)


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
