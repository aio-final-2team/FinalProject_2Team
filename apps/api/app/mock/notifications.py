"""이력별 알림 생성과 모의 발송기."""

from dataclasses import replace

from app.api.labels import parent_label
from app.core.care import unregistered_pickup_key
from app.core.constants import (CARE_REQUEST_TYPES, CARE_MESSAGE_NOTICE, CARE_UPDATED_NOTICE, UNREGISTERED_PICKUP_CHECK,
                                NOTIFICATION_TITLES as TITLES, consultation_booking_body, notification_title, rejection_body)
from app.core.schedule import deliver_after
from app.core.errors import ApiError
from app.mock import store
from app.mock.records import Notification



def create(ev, recipient_id, kind, body=None, subject_id=None, *, dedupe_key=None):
    state = store.state()
    recipient = state.users.get(recipient_id)
    if recipient is None or recipient.org_id != ev.org_id:
        return
    key = dedupe_key or f"event:{ev.id}:{recipient_id}"
    if any(n.dedupe_key == key for n in state.notifications.values()):
        return
    req = state.requests.get(ev.request_id)
    notification = Notification(
        id=state.next_int(), org_id=ev.org_id, recipient_id=recipient_id, kind=kind,
        title=notification_title(kind, req.type if req else None),
        body=body, dedupe_key=key, request_id=ev.request_id, card_id=ev.card_id,
        subject_type="daily_note" if subject_id else None, subject_id=subject_id, created_at=ev.created_at,
        deliver_after=deliver_after(ev.created_at, recipient.role, req.risk_level if req else None,
                                    req.risk_category if req else None, request_type=req.type if req else None))
    state.notifications[notification.id] = notification


def notify_event(ev, req, card):
    if ev.action == "reassigned":
        create(ev, card.assignee_id, "reassigned")
        return
    if req is None:
        if card and ev.action in ("created", "drafted"):
            create(ev, card.assignee_id, "new_card")
        if ev.action == "daily_note_sent" and ev.daily_note_id:
            note = store.state().notes[ev.daily_note_id]
            for guardian in store.state().children[note.child_id].guardian_ids:
                create(ev, guardian, "note_sent", subject_id=note.id)
        return
    if req.type == "consultation" and (
        (ev.action == "created" and card and card.kind == "consult_slots" and not card.assignee_id)
        or (ev.action == "info_requested" and "preferred_times" in ev.detail)
    ):
        create(ev, card.assignee_id or store.director_of(req.org_id),
               "parent_message" if "preferred_times" in ev.detail else "new_card",
               ev.detail.get("preferred_times"))
        return
    if req.type in CARE_REQUEST_TYPES:
        if ev.action == "cancelled":
            create(ev, req.assignee_id or store.director_of(req.org_id), "cancelled")
        elif ev.detail.get("care_decision") == "reject":
            create(ev, req.requester_id, "care_rejected", ev.detail["reason_text"])
        elif ev.detail.get("unregistered_pickup"):
            create(ev, store.director_of(req.org_id), "care_requested", UNREGISTERED_PICKUP_CHECK,
                   dedupe_key=unregistered_pickup_key(req.id, ev.detail.get("pickup_snapshot", {})))
        elif ev.detail.get("care_message") or ev.action == "care_updated":
            create(ev, req.assignee_id or store.director_of(req.org_id), "care_requested",
                   CARE_UPDATED_NOTICE if ev.action == "care_updated" else CARE_MESSAGE_NOTICE)
        elif ev.action == "created" and ev.to_status == "received":
            create(ev, req.assignee_id or store.director_of(req.org_id), "care_requested")
        elif ev.detail.get("care_decision") in ("confirm", "complete"):
            create(ev, req.requester_id, "care_confirmed" if ev.to_status == "assigned" else "completed",
                   parent_label(ev.to_status, req.type, req.assignee_id))
        return
    if ev.action == "message_added":
        if req.type == "consultation" and req.status in ("needs_info", "sent_or_booked"):
            recipients = {req.assignee_id: None} if req.assignee_id else {}
        elif req.status in ("awaiting_review", "on_hold", "escalated", "needs_info"):
            recipients = {c.assignee_id: c.id for c in sorted(store.cards_of(req.id), key=lambda c: (c.created_at, c.id))
                          if c.status not in ("done", "rejected") and c.assignee_id}
        else:
            return
        if not recipients:
            recipients = {store.director_of(req.org_id): None}
        for recipient, card_id in recipients.items():
            create(replace(ev, card_id=card_id), recipient, "parent_message")
        return
    parent_kinds = {"needs_info": "needs_info", "on_hold": "on_hold", "sent_or_booked": "sent_or_booked",
                    "rejected": "rejected"}
    if ev.to_status == "completed" and req.type == "complaint":
        create(ev, req.requester_id, "completed")
    elif ev.to_status in parent_kinds:
        kind = parent_kinds[ev.to_status]
        body = parent_label(ev.to_status, req.type, req.assignee_id, req.parent_confirmed_at)
        if ev.to_status == "sent_or_booked" and req.type == "consultation":
            kind = "consultation_booked"
            booking = store.confirmed_booking_of(req.id)
            body = consultation_booking_body(booking.period["start"], booking.period["end"])
        if ev.to_status == "on_hold":
            body += f" · 예정일 {card.hold_until}"
        if ev.action == "dismissed":
            body = rejection_body(ev.detail.get("reason_code"), ev.detail.get("reason_text"))
        create(ev, req.requester_id, kind, body)
    if ev.action == "escalated":
        if req.risk_level in ("urgent", "uncertain"):
            kind = "urgent_complaint" if req.risk_level == "urgent" else "uncertain_complaint"
            for recipient in {req.assignee_id, store.director_of(req.org_id)}:
                create(ev, recipient, kind)
        else:
            create(ev, store.director_of(req.org_id), "director_report")
    elif ev.action == "parent_confirmed":
        create(ev, req.assignee_id, "parent_confirmed")
    elif ev.action == "slot_hold_expired":
        create(ev, card.assignee_id, "slot_hold_expired")
    elif (ev.action == "risk_reclassified" and ev.from_status == "escalated"
          and ev.to_status == "awaiting_review" and req.risk_level == "normal"):
        replies = [c for c in store.cards_of(req.id) if c.kind == "reply_draft"
                   and c.status in ("pending", "in_review")]
        if replies:
            reply = max(replies, key=lambda c: (c.created_at, c.id))
            create(replace(ev, card_id=reply.id), reply.assignee_id, "new_card")
    elif ev.to_status == "awaiting_review" and ev.action != "risk_reclassified":
        automatic = ev.action == "resumed" and ev.detail.get("automatic")
        if ev.action != "resumed" or automatic:
            recipient = card.assignee_id if card else req.assignee_id
            if card and card.status == "unassigned" and recipient is None:
                recipient = store.director_of(req.org_id)
            create(ev, recipient, "hold_resumed" if automatic else "new_card")


def visible(user):
    with store._lock:
        items = [n for n in store.state().notifications.values()
                 if n.org_id == user.org_id and n.recipient_id == user.id and n.deliver_after <= store.now()]
        for n in items:
            if n.status == "pending":
                n.status, n.sent_at = "sent", store.now()
        return items


def read(user, notification_id):
    with store._lock:
        notification = next((n for n in visible(user) if n.id == notification_id), None)
        if notification is None:
            store.deny(user)
        notification.read_at = notification.read_at or store.now()
        return notification.__dict__


def listing(user, page, size, sort):
    rows = sorted(visible(user), key=lambda row: row.created_at, reverse=sort.startswith('-'))
    return {'items': [row.__dict__ for row in rows[(page-1)*size:page*size]],
            'total': len(rows), 'page': page, 'size': size}
