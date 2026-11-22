"""고정 데모 행을 저장소에 채운다."""

from datetime import timedelta
import logging
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

    from app.core.config import settings
    if settings.feature_neighborhood_feed:
        state.organizations[seed.ORG]["region"] = "가상동"
        for org in seed.NEIGHBORHOOD_ORGS:
            state.organizations[org["id"]] = {k: org[k] for k in ("id", "name", "region")}
            state.users[org["parent_id"]] = store.User(org["parent_id"], org["id"], "parent", org["login_id"],
                                                      seed.DEMO_PASSWORD, "가상 보호자")
            state.classrooms[org["classroom_id"]] = store.Classroom(org["classroom_id"], org["id"], "가상반")
            state.children[org["child_id"]] = store.Child(org["child_id"], org["id"], org["classroom_id"],
                                                         "가상 아이", [org["parent_id"]])
    if settings.feature_video_consult or settings.feature_voice_analysis:
        seed_video_consult()

    from app.core import media
    media.reset_mock()
    for child in state.children.values():
        child.photo_scope = seed.PHOTO_SCOPES.get(child.id, "family")
    for data in seed.FEED_POSTS:
        state.feed_posts[data["id"]] = {**data, "org_id": seed.ORG, "status": "published",
                                        "deleted_at": None, "created_at": seed.FEED_CREATED_AT}
    png = seed.feed_png()
    metadata = media.inspect(png)
    for photo_id, post_id, tags in seed.FEED_PHOTOS:
        name = f"mock/{photo_id}.png"
        if not media.path(name).exists():
            media.save(png, metadata, file_id=photo_id, mock=True)
        state.feed_photos[photo_id] = {"id": photo_id, "post_id": post_id, "org_id": seed.ORG, **metadata,
                                       "storage_path": name, "child_ids": tags, "created_at": seed.FEED_CREATED_AT}


def seed_video_consult(now=None):
    from app.mock.records import Booking
    now = now if now is not None else seed.video_now()
    state = store.state()
    booking = state.bookings.get(seed.VIDEO_BOOKING)
    if booking and booking.org_id == seed.ORG:
        if booking.status == "confirmed":
            period = seed.video_period(now=now)
            if any(b.id != booking.id and b.org_id == seed.ORG and b.status == "confirmed"
                   and (b.teacher_id == booking.teacher_id or b.room_id == booking.room_id)
                   and b.period["start"] < period["end"] and period["start"] < b.period["end"]
                   for b in state.bookings.values()):
                logging.getLogger(__name__).warning("가상 화상상담 예약 갱신 생략: 담임·상담실 시간 겹침")
            else:
                booking.period, booking.expected_end_at = period, None
        return
    if any(b.org_id == seed.ORG and b.status == "confirmed" for b in state.bookings.values()):
        return
    period = seed.video_period(now=now)
    req = store.Request(seed.VIDEO_REQUEST, seed.ORG, seed.CLASS_STAR, seed.CHILD, seed.PARENT,
                        "demo-video-consult", "consultation", "가상 화상상담", status="sent_or_booked")
    state.requests[req.id] = req
    state.bookings[seed.VIDEO_BOOKING] = Booking(seed.VIDEO_BOOKING, seed.ORG, req.id, None, seed.TEACHER,
                                               seed.ROOM, period, seed.TEACHER)
    store.add_event(req, "booked", actor_type="user", actor_id=seed.TEACHER)
