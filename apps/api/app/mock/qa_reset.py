"""DB와 같은 범위·개수·연결 해제 규칙의 QA 대역이에요."""

from app.mock import store


def reset(user, classroom_id, note_date):
    with store._lock:
        store.classroom_in_scope(user, classroom_id)
        state = store.state()
        inputs = {i.id for i in state.note_inputs.values()
                  if (i.org_id, i.classroom_id, i.note_date) == (user.org_id, classroom_id, note_date)}
        notes = {n.id for n in state.notes.values() if n.org_id == user.org_id and n.input_id in inputs}
        cards = {c.id for c in state.cards.values() if c.org_id == user.org_id
                 and c.subject_type == "daily_note_batch" and c.subject_id in inputs}
        replies = [r for r in state.requests.values() if r.org_id == user.org_id and r.source_note_id in notes]
        for reply in replies:
            reply.source_note_id = None
        notices = {n.id for n in state.notifications.values() if n.org_id == user.org_id
                   and (n.card_id in cards or (n.subject_type == "daily_note" and n.subject_id in notes))}
        events = [e for e in state.events if e.org_id == user.org_id
                  and (e.daily_note_id in notes or e.card_id in cards)]
        deleted = {"inputs": len(inputs), "notes": len(notes), "cards": len(cards),
                   "notifications": len(notices), "events": len(events)}
        for rows, ids in ((state.notifications, notices), (state.cards, cards),
                          (state.notes, notes), (state.note_inputs, inputs)):
            for row_id in ids:
                del rows[row_id]
        state.events = [e for e in state.events if not (e.org_id == user.org_id
                        and (e.daily_note_id in notes or e.card_id in cards))]
        state.approvals = [a for a in state.approvals if a.card_id not in cards]
        state.evidence = [e for e in state.evidence if e.card_id not in cards]
        state.slots = {key: slot for key, slot in state.slots.items() if slot.card_id not in cards}
        for memory in state.memories.values():
            if memory.org_id == user.org_id and memory.source_card_id in cards:
                memory.source_card_id = None
        store.add_event(None, "tool_called", org_id=user.org_id, actor_type="user", actor_id=user.id,
                        tool="qa_daily_note_reset", classroom_id=str(classroom_id),
                        note_date=note_date.isoformat(), deleted=deleted)
        return {"classroom_id": classroom_id, "note_date": note_date,
                "deleted": deleted, "unlinked_replies": len(replies)}
