"""모의 API 저장소. 메모리 안에서만 살고, 서버를 다시 켜거나 reset()하면 데모 데이터로 돌아간다.

칸 이름은 DB 설계서(db_schema_draft.sql)의 컬럼 이름을 그대로 쓴다. T19부터 이 자리를 실제 DB 구현으로 바꾼다.
모의 AI는 요청을 받는 즉시 결과(분류·카드·상담 후보)를 만들어 두고, 스트림은 단계만 흉내 낸다.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any
from uuid import UUID, uuid4

from app.core.errors import ApiError
from app.core.consents import require_complete
from app.core.constants import CARE_REQUEST_TYPES, OUT_OF_SCOPE_MESSAGES
from app.mock import seed
from app.core.schedule import KST, due_at
from app.mock.records import Approval, Booking, Notification, Document, Chunk, Evidence, Rule, NoteInput, Note


def now() -> datetime:
    return datetime.now(KST)


@dataclass
class User:
    id: UUID
    org_id: UUID
    role: str
    login_id: str
    password: str
    display_name: str
    token_version: int = 0
    is_active: bool = True


@dataclass
class Classroom:
    id: UUID
    org_id: UUID
    name: str


@dataclass
class ClassroomStaff:
    classroom_id: UUID
    user_id: UUID
    valid_from: date | None = None
    valid_to: date | None = None


@dataclass
class Child:
    id: UUID
    org_id: UUID
    classroom_id: UUID
    display_name: str
    guardian_ids: list[UUID]
    photo_scope: str = "family"


@dataclass
class Room:
    id: UUID
    org_id: UUID
    name: str


@dataclass
class Request:
    id: UUID
    org_id: UUID
    classroom_id: UUID
    child_id: UUID
    requester_id: UUID
    client_request_id: str
    type: str
    body: str
    title: str | None = None
    status: str = "received"
    urgency: str | None = None
    risk_level: str | None = None
    risk_category: str | None = None
    topic_key: str | None = None
    parent_confirmed_at: datetime | None = None
    missing_fields: list[str] = field(default_factory=list)
    care_detail: dict = field(default_factory=dict)
    assignee_id: UUID | None = None
    previous_request_id: UUID | None = None
    created_at: datetime = field(default_factory=lambda: now())
    updated_at: datetime = field(default_factory=lambda: now())
    closed_at: datetime | None = None


@dataclass
class Message:
    id: int
    request_id: UUID
    sender_type: str            # user · agent · system
    sender_id: UUID | None
    body: str
    created_at: datetime = field(default_factory=lambda: now())

    @property
    def sender_role(self) -> str | None:
        # DB 모드처럼 사람이 쓴 글만 쓴 사람의 역할을 붙여요.
        user = _state.users.get(self.sender_id) if self.sender_type == "user" else None
        return user.role if user else None


@dataclass
class Card:
    id: UUID
    org_id: UUID
    request_id: UUID | None
    kind: str                   # reply_draft · consult_slots · director_report · needs_info · daily_note · rule_proposal
    status: str = "pending"
    assignee_id: UUID | None = None
    due_at: datetime | None = None
    hold_until: date | None = None
    draft: dict[str, Any] = field(default_factory=dict)
    check_result: dict[str, Any] | None = None
    check_attempts: int = 0
    version: int = 1
    subject_type: str | None = None
    subject_id: UUID | None = None
    created_at: datetime = field(default_factory=lambda: now())
    updated_at: datetime = field(default_factory=lambda: now())
    closed_at: datetime | None = None


@dataclass
class Slot:
    id: int
    card_id: UUID
    org_id: UUID
    teacher_id: UUID
    room_id: UUID
    period: dict
    round: int = 1
    rank: int = 1
    status: str = "proposed"    # proposed · chosen_by_parent · confirmed · discarded
    chosen_at: datetime | None = None


@dataclass
class Event:
    id: int
    org_id: UUID
    action: str
    request_id: UUID | None = None
    card_id: UUID | None = None
    daily_note_id: UUID | None = None
    actor_type: str = "system"  # user · agent · system
    actor_id: UUID | None = None
    agent_name: str | None = None
    from_status: str | None = None
    to_status: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: now())


class _State:
    def __init__(self) -> None:
        org = seed.ORG
        self.users = {u["id"]: User(org_id=org, password=seed.DEMO_PASSWORD, **u) for u in seed.USERS}
        self.classrooms = {c["id"]: Classroom(org_id=org, **c) for c in seed.CLASSROOMS}
        self.classroom_staff = [ClassroomStaff(**s) for s in seed.CLASSROOM_STAFF]
        self.children = {c["id"]: Child(org_id=org, **{**c, "guardian_ids": list(c["guardian_ids"])}) for c in seed.CHILDREN}
        self.rooms = {r["id"]: Room(org_id=org, **r) for r in seed.ROOMS}
        self.requests: dict[UUID, Request] = {}
        self.messages: list[Message] = []
        self.cards: dict[UUID, Card] = {}
        self.slots: dict[int, Slot] = {}
        self.events: list[Event] = []
        self.approvals: list[Approval] = []
        self.bookings: dict[UUID, Booking] = {}
        self.staff_busy_blocks: list[dict] = []
        self.notifications: dict[int, Notification] = {}
        self.documents: dict[UUID, Document] = {}
        self.document_classrooms: dict[UUID, list[UUID]] = {}
        self.chunks: dict[int, Chunk] = {}
        self.evidence: list[Evidence] = []
        self.rules: dict[UUID, Rule] = {}
        self.note_inputs: dict[UUID, NoteInput] = {}
        self.notes: dict[UUID, Note] = {}
        self.feed_posts = {}
        self.feed_photos = {}
        self.memories = {}
        self.consents = {}
        self._seq = 1000

    def next_int(self) -> int:
        self._seq += 1
        return self._seq


_lock = threading.RLock()
_state = _State()


def reset() -> None:
    """데모 데이터로 되돌린다. 시험마다 부른다."""
    global _state
    with _lock:
        _state = _State()
        from app.mock.seeding import populate
        populate()


def state() -> _State:
    return _state


# ---------- 사람·범위 ----------

def get_user(user_id: UUID) -> User | None:
    return _state.users.get(user_id)


def find_user_by_login(login_id: str) -> User | None:
    return next((u for u in _state.users.values() if u.login_id == login_id), None)


def authenticate(login_id: str, password: str) -> User | None:
    user = find_user_by_login(login_id)
    return user if user and user.is_active and user.password == password else None


def children_of(parent_id: UUID) -> list[Child]:
    return [c for c in _state.children.values() if parent_id in c.guardian_ids]


def classroom_ids_of(teacher_id: UUID, on: date | None = None) -> list[UUID]:
    """오늘 볼 수 있는 반. 대체 담임은 valid_from~valid_to 안에서만(T04 7.1)."""
    on = on or now().date()
    out = []
    for s in _state.classroom_staff:
        if s.user_id != teacher_id:
            continue
        if (s.valid_from and on < s.valid_from) or (s.valid_to and on > s.valid_to):
            continue
        out.append(s.classroom_id)
    return out


def homeroom_teacher(classroom_id: UUID) -> UUID | None:
    return next((s.user_id for s in _state.classroom_staff if s.classroom_id == classroom_id
                 and classroom_id in classroom_ids_of(s.user_id)), None)


def director_of(org_id: UUID) -> UUID | None:
    return next((u.id for u in _state.users.values() if u.org_id == org_id and u.role == "director"), None)


def request_in_scope(user, request_id: UUID) -> Request:
    """범위 밖이면 있는지도 알리지 않고 404(API 설계 문서 4.2)."""
    req = _state.requests.get(request_id)
    if req is None or req.org_id != user.org_id:
        deny(user, req=req if req and req.org_id == user.org_id else None)
    if user.role == "parent" and req.requester_id != user.id:
        deny(user, req=req if req and req.org_id == user.org_id else None)
    if user.role == "teacher":
        reassigned = any(c.request_id == req.id and c.assignee_id == user.id for c in _state.cards.values())
        if req.classroom_id not in classroom_ids_of(user.id) and not reassigned:
            deny(user, req=req if req and req.org_id == user.org_id else None)
    expire(req.id)
    return req


# ---------- 이력 ----------

def add_event(req: Request | None, action: str, *, card: Card | None = None, actor_type: str = "system",
              actor_id: UUID | None = None, agent_name: str | None = None, from_status: str | None = None,
              to_status: str | None = None, daily_note_id: UUID | None = None, **detail) -> Event:
    ev = Event(id=_state.next_int(), org_id=(req.org_id if req else card.org_id if card else detail.pop("org_id")), action=action,
               request_id=req.id if req else None, card_id=card.id if card else None,
               actor_type=actor_type, actor_id=actor_id, agent_name=agent_name,
               from_status=from_status, to_status=to_status, detail=detail)
    ev.daily_note_id = daily_note_id
    from app.core.request_id import active_trace_id
    if ev.detail.get("trace_id") is None:
        ev.detail["trace_id"] = active_trace_id.get()
    _state.events.append(ev)
    from app.mock.notifications import notify_event
    notify_event(ev, req, card)
    return ev


def set_request_status(req: Request, to: str, **event_kw) -> None:
    frm, req.status, req.updated_at = req.status, to, now()
    if to in ("completed", "rejected"):
        req.closed_at = req.updated_at
    add_event(req, event_kw.pop("action", "classified"), from_status=frm, to_status=to, **event_kw)


# ---------- 요청 만들기 ----------

def create_request(user, *, client_request_id: str, type: str, body: str, child_id: UUID,
                   previous_request_id: UUID | None, trace_id: str | None,
                   pickup_guardian_id: UUID | None = None, **care_fields) -> tuple[Request, bool]:
    """(요청, 새로 만들었는지). 같은 client_request_id면 처음 요청을 돌려준다(6.4)."""
    with _lock:
        for r in _state.requests.values():
            if r.requester_id == user.id and r.client_request_id == client_request_id:
                require_complete(user)
                return r, False
        child = _state.children.get(child_id)
        if child is None or child.org_id != user.org_id or user.id not in child.guardian_ids:
            raise ApiError(404, "NOT_FOUND")
        from app.core.care import input_detail
        from app.core.constants import MEDICATION_FIELDS
        detail = input_detail(type, pickup_guardian_id=pickup_guardian_id, **care_fields)
        if type == "pickup" and pickup_guardian_id is not None:
            from app.mock.care import validate_guardian
            detail = validate_guardian(user, child_id, pickup_guardian_id)
        if previous_request_id is not None:
            prev = request_in_scope(user, previous_request_id)
            if prev.status not in ("completed", "rejected"):
                raise ApiError(409, "INVALID_TRANSITION")
        require_complete(user)
        req = Request(id=uuid4(), org_id=user.org_id, classroom_id=child.classroom_id, child_id=child.id,
                      requester_id=user.id, client_request_id=client_request_id, type=type, body=body,
                      title=body.split("\n")[0][:40], previous_request_id=previous_request_id, care_detail=detail)
        if type == "medication":
            req.missing_fields = [key for key in MEDICATION_FIELDS if not (detail.get(key) or "").strip()]
        _state.requests[req.id] = req
        _state.messages.append(Message(id=_state.next_int(), request_id=req.id, sender_type="user",
                                       sender_id=user.id, body=body))
        if type in CARE_REQUEST_TYPES:
            req.assignee_id = homeroom_teacher(req.classroom_id)
        event = add_event(req, "created", actor_type="user", actor_id=user.id, to_status="received", trace_id=trace_id,
                  **({"fields": list(detail)} if type in CARE_REQUEST_TYPES else {}))
        from app.mock.notes import request_received
        request_received(req, event)
        if type not in CARE_REQUEST_TYPES:
            _run_mock_ai(req, trace_id)
        return req, True


# 모의 AI 분류 규칙. 실제 분류는 감독 AI(T14)가 한다. 화면 시연용으로 낱말만 본다.
def _classify(req: Request) -> dict:
    from app.modules.requests.supervisor import validate_proposal
    fields = validate_proposal(req.type, req.body, {})
    for key in ("topic_key", "urgency", "risk_level", "risk_category"):
        setattr(req, key, fields.get(key))
    return fields


def _run_mock_ai(req: Request, trace_id: str | None) -> None:
    if req.type in CARE_REQUEST_TYPES:
        return
    from app.core.request_rules import direct_notice_kind
    fields = _classify(req)
    set_request_status(req, "classified", action="classified", actor_type="agent", agent_name="supervisor",
                       trace_id=trace_id)
    teacher = homeroom_teacher(req.classroom_id)
    req.assignee_id = teacher
    set_request_status(req, "assigned", action="assigned", actor_type="agent", agent_name="supervisor",
                       trace_id=trace_id)
    notice = direct_notice_kind(req.type, req.body, fields)
    if notice:
        _state.messages.append(Message(id=_state.next_int(), request_id=req.id, sender_type="agent",
                                       sender_id=None, body=OUT_OF_SCOPE_MESSAGES[notice]))
        if req.type == "inquiry":
            set_request_status(req, "sent_or_booked", action="out_of_scope_answered", kind=notice,
                               actor_type="agent", agent_name="supervisor", trace_id=trace_id)
            return
    summary = req.body[:60]
    high_risk = req.risk_level in ("urgent", "uncertain")
    if req.type == "consultation":
        card = _new_card(req, "consult_slots", teacher)
        _propose_slots(card, teacher)
        set_request_status(req, "needs_info", action="info_requested", card=card, actor_type="agent",
                           agent_name="code", trace_id=trace_id)
        director = director_of(req.org_id)
        if high_risk and director:
            # DB 백엔드와 같이 상담 흐름은 두고 원장 보고 카드와 알림만 더해요.
            report = _new_card(req, "director_report", director, draft={"summary": summary})
            add_event(req, "escalated", card=report, actor_type="agent", agent_name="supervisor", trace_id=trace_id, reason="risk")
        return
    card = _new_card(req, "reply_draft", teacher, draft={
        "summary": summary,
        **({} if high_risk else {"text": "(모의 초안) 말씀해 주셔서 감사합니다. 확인해서 다시 안내드릴게요."}),
    })
    if not high_risk:
        from app.mock.documents import attach_evidence
        attach_evidence(card)
        card.check_result = {"passed": True, "issues": [], "attempt": 1}
    add_event(req, "drafted", card=card, actor_type="agent", agent_name="document", trace_id=trace_id)
    if high_risk or (req.type == "complaint" and (repeat_count(req) or 0) >= 3):
        report = _new_card(req, "director_report", director_of(req.org_id), draft={"summary": summary})
        set_request_status(req, "escalated", action="escalated", card=report, actor_type="agent",
                           agent_name="supervisor", trace_id=trace_id, reason="risk" if high_risk else "repeat")
        return
    set_request_status(req, "awaiting_review", action="checked", card=card, actor_type="agent",
                       agent_name="checker", trace_id=trace_id)


def _new_card(req: Request, kind: str, assignee: UUID | None, draft: dict | None = None) -> Card:
    card = Card(id=uuid4(), org_id=req.org_id, request_id=req.id, kind=kind,
                status="pending" if assignee else "unassigned", assignee_id=assignee, draft=draft or {},
                due_at=due_at(req.created_at, req.type, req.risk_level, kind))
    _state.cards[card.id] = card
    add_event(req, "created", card=card, actor_type="agent", agent_name="supervisor")
    return card


def _next_weekday(d: date) -> date:
    d += timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def slot_conflicts(org_id, teacher, room, period):
    start, end = period["start"], period["end"]
    return any(b["org_id"] == org_id and b["user_id"] == teacher
               and start < b["period"]["end"] and b["period"]["start"] < end
               for b in _state.staff_busy_blocks) or any(
        b.org_id == org_id and b.status == "confirmed" and (b.teacher_id == teacher or b.room_id == room)
        and start < (b.expected_end_at or b.period["end"]) and b.period["start"] < end
        for b in _state.bookings.values())


def _propose_slots(card: Card, teacher: UUID | None, round_no: int = 1, *, preferred_times=None, count=3) -> list[Slot]:
    """평일 15:00·16:00 중 확정·살아 있는 체크와 겹치지 않는 세 칸을 골라요."""
    from app.modules.consultations.slots import preference_key
    if preferred_times is None:
        preferred_times = next((e.detail["preferred_times"] for e in reversed(events_of(card.request_id))
                                if "preferred_times" in e.detail), None)
    first = _next_weekday(now().date())
    room = next(iter(_state.rooms))
    teacher = teacher or seed.TEACHER
    candidates = []
    day = first
    while day <= now().date()+timedelta(days=14):
        for hour in (15, 16):
            start = datetime.combine(day, time(hour), KST)
            end = start + timedelta(minutes=30)

            def overlaps(period):
                return start < period["end"] and period["start"] < end

            if slot_conflicts(card.org_id, teacher, room, {"start": start, "end": end}):
                continue
            if any(s.org_id == card.org_id and overlaps(s.period) and (
                    _state.cards[s.card_id].request_id == card.request_id
                    or (s.status == "chosen_by_parent" and s.chosen_at > now()-timedelta(hours=24)
                        and (s.teacher_id == teacher or s.room_id == room))) for s in _state.slots.values()):
                continue
            candidates.append({"start": start, "end": end})
        day = _next_weekday(day)
    out = []
    for rank, period in enumerate(sorted(candidates, key=preference_key(preferred_times, now()))[:count], 1):
        slot = Slot(id=_state.next_int(), card_id=card.id, org_id=card.org_id, teacher_id=teacher,
                    room_id=room, period=period, round=round_no, rank=rank)
        _state.slots[slot.id] = slot
        out.append(slot)
    return out


# ---------- 조회 ----------

def get_request(request_id: UUID | None) -> Request | None:
    """이미 범위를 확인한 카드가 가리키는 요청. 요청 없는 카드면 None."""
    return _state.requests.get(request_id)


def requests_of(user, status=None) -> list[Request]:
    return [r for r in _state.requests.values() if r.org_id == user.org_id and r.requester_id == user.id
            and (status is None or r.status == status)]


def room_name(room_id: UUID) -> str:
    return _state.rooms[room_id].name


def confirmed_booking_of(request_id: UUID) -> Booking | None:
    return next((b for b in _state.bookings.values() if b.request_id == request_id and b.status == "confirmed"), None)


def rejection_of(request_id: UUID) -> dict | None:
    return next(({"reason_code": a.reason_code, "reason_text": a.reason_text}
                 for a in reversed(_state.approvals) if a.decision == "dismiss"
                 and _state.cards[a.card_id].request_id == request_id), None)


def approved_cards_of(request_id: UUID) -> list[Card]:
    return [card for card in cards_of(request_id)
            if any(a.card_id == card.id and a.decision in ("approve", "edit_approve") for a in _state.approvals)]


def messages_of(request_id: UUID) -> list[Message]:
    return [m for m in _state.messages if m.request_id == request_id]


def events_of(request_id: UUID) -> list[Event]:
    return [e for e in _state.events if e.request_id == request_id]


def cards_of(request_id: UUID) -> list[Card]:
    return [c for c in _state.cards.values() if c.request_id == request_id]


def slots_of_request(request_id: UUID) -> list[Slot]:
    card_ids = {c.id for c in cards_of(request_id) if c.kind == "consult_slots"}
    return sorted((s for s in _state.slots.values() if s.card_id in card_ids), key=lambda s: (s.round, s.rank))


def hold_until_of(request_id: UUID) -> date | None:
    return next((c.hold_until for c in cards_of(request_id) if c.status == "on_hold"
                 and not (c.kind == "director_report" and _state.requests[request_id].type == "consultation")), None)


def repeat_count(req):
    if req.type != "complaint" or req.topic_key in (None, "other"):
        return None
    return sum(r.org_id == req.org_id and r.classroom_id == req.classroom_id and r.type == "complaint"
               and r.topic_key == req.topic_key and r.created_at >= now() - timedelta(days=30)
               for r in _state.requests.values())


def expire(request_id=None):
    """읽을 때 기한이 지난 보류와 상담 후보를 한 번만 되돌린다."""
    with _lock:
        for card in list(_state.cards.values()):
            if request_id is not None and card.request_id != request_id:
                continue
            req = _state.requests.get(card.request_id)
            if card.status == "on_hold" and card.hold_until <= now().date():
                card.status, card.hold_until = "pending", None
                card.version += 1
                card.updated_at = now()
                if req and card.kind == "director_report" and req.type == "consultation":
                    add_event(req, "resumed", card=card, automatic=True)
                elif req:
                    set_request_status(req, "awaiting_review", action="resumed", card=card, automatic=True)
            if req is None or req.status != "awaiting_review":
                continue
            expired = [s for s in _state.slots.values() if s.card_id == card.id
                       and s.status == "chosen_by_parent" and s.chosen_at + timedelta(hours=24) <= now()]
            for slot in expired:
                slot.status, slot.chosen_at = "proposed", None
            if expired:
                set_request_status(req, "needs_info", action="slot_hold_expired", card=card)


def deny(user, req=None, card=None):
    add_event(req, "permission_denied", card=card, org_id=user.org_id, actor_type="user", actor_id=user.id)
    raise ApiError(404, "NOT_FOUND")


def classroom_in_scope(user, classroom_id):
    classroom = _state.classrooms.get(classroom_id)
    if classroom is None or classroom.org_id != user.org_id or (user.role == "teacher"
            and classroom_id not in classroom_ids_of(user.id)):
        deny(user)
    return classroom


def classroom_children(user, classroom_id):
    classroom_in_scope(user, classroom_id)
    return [child for child in _state.children.values()
            if child.org_id == user.org_id and child.classroom_id == classroom_id]


reset()
