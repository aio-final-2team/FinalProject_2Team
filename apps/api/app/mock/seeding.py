"""고정 데모 행을 저장소에 채운다."""

from datetime import timedelta
from hashlib import sha256

from app.core.schedule import due_at
from app.mock import seed, store
from app.mock.records import Document, Rule


def populate():
    from app.mock.documents import add_chunks
    state = store.state()
    for doc_id, title, doc_type, status, content in seed.DEMO_DOCUMENTS:
        doc = Document(doc_id, seed.ORG, title, doc_type, "all", sha256(content.encode()).hexdigest(),
                       store.now().date() - timedelta(days=10), store.now(), status=status)
        state.documents[doc.id] = doc
        state.document_classrooms[doc.id] = []
        add_chunks(doc, content)
    for suffix, request_type, body, target in seed.DEMO_REQUESTS:
        req = store.Request(seed.demo_id(suffix), seed.ORG, seed.CLASS_STAR, seed.CHILD, seed.PARENT,
                            f"demo-{suffix}", request_type, body, title=body)
        state.requests[req.id] = req
        state.messages.append(store.Message(state.next_int(), req.id, "user", seed.PARENT, body))
        store.add_event(req, "created", to_status="received")
        store._run_mock_ai(req, None)
        card = store.cards_of(req.id)[0]
        old_id = card.id
        card.id = seed.demo_id("8" + suffix[1:])
        state.cards.pop(old_id)
        state.cards[card.id] = card
        for collection in (state.slots.values(), state.events, state.evidence, state.notifications.values()):
            for row in collection:
                if row.card_id == old_id:
                    row.card_id = card.id
        if target == "on_hold":
            card.hold_until = store.now().date() + timedelta(days=2)
            card.status = "on_hold"
            store.set_request_status(req, target, action="held", card=card)
        elif target == "completed":
            card.status, card.closed_at = "done", store.now()
            store.set_request_status(req, target, action="completed", card=card)
        elif target == "classified":
            card.status, card.assignee_id, req.assignee_id = "unassigned", None, None
            req.status = target
    for data in seed.DEMO_NOTE_REQUESTS:
        req = store.Request(org_id=seed.ORG, classroom_id=seed.CLASS_STAR,
                            client_request_id=f"demo-{data['id']}", title=data["body"], **data)
        state.requests[req.id] = req
        state.messages.append(store.Message(state.next_int(), req.id, "user", req.requester_id, req.body))
        store.add_event(req, "created", to_status="received", actor_type="user", actor_id=req.requester_id)
    rule = Rule(seed.RULE, seed.ORG, seed.TEACHER, "slot_unavailable", "상담 후보는 오후 시간부터 제안해 주세요.", {"after": "14:00"})
    state.rules[rule.id] = rule
    card = store.Card(seed.demo_id("809"), seed.ORG, None, "rule_proposal", assignee_id=seed.TEACHER,
                      subject_type="memory_rule", subject_id=rule.id, draft={"summary": "상담 시간 규칙 제안"},
                      due_at=due_at(store.now(), kind="rule_proposal"))
    state.cards[card.id] = card
    store.add_event(None, "created", card=card)
