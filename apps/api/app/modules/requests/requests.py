"""학부모 요청·대화·확인. 범위 검사와 SQL 변경을 같은 트랜잭션에서 해요."""

from sqlalchemy import text

from app.api.labels import parent_label, staff_label
from app.core import scope
from app.core.constants import DEFERRED_REQUEST_TYPES
from app.core.db import transaction
from app.core.errors import ApiError
from app.modules.requests.events import record, set_status
from app.modules.requests.runner import run_request


def _readable(req):
    if req["type"] == "medication":
        raise ApiError(501, "NOT_IMPLEMENTED")


def _parent_readable(user, req):
    if user.role == "parent" and req["type"] in DEFERRED_REQUEST_TYPES:
        scope._checked(user, req, False, "request", req["id"], request_id=req["id"])


def _lock(connection, request_id):
    return dict(connection.execute(text("SELECT * FROM requests WHERE id=:id FOR NO KEY UPDATE"),
                                   {"id": request_id}).mappings().one())


def create(user, *, background_tasks, client_request_id, type, body, child_id, previous_request_id, trace_id):
    with transaction() as connection:
        values = {"org": user.org_id, "user": user.id, "key": client_request_id}
        old = connection.execute(text("SELECT * FROM requests WHERE requester_id=:user AND client_request_id=:key"),
                                 values).mappings().one_or_none()
        if old is not None:
            scope.request_in_scope(user, old["id"], connection=connection)
            return old, False
        child = scope.child_in_scope(user, child_id, connection=connection)
        if previous_request_id is not None:
            prev = scope.request_in_scope(user, previous_request_id, connection=connection)
            if prev["status"] not in ("completed", "rejected"):
                raise ApiError(409, "INVALID_TRANSITION")
        row = connection.execute(text("""
            INSERT INTO requests (org_id,classroom_id,child_id,requester_id,client_request_id,type,body,title,previous_request_id)
            VALUES (:org,:class,:child,:user,:key,:type,:body,:title,:previous)
            ON CONFLICT (requester_id,client_request_id) DO NOTHING RETURNING *
        """), {**values, "class": child["classroom_id"], "child": child_id, "type": type, "body": body,
               "title": body.split("\n")[0][:40], "previous": previous_request_id}).mappings().one_or_none()
        if row is None:
            old = connection.execute(text("SELECT * FROM requests WHERE requester_id=:user AND client_request_id=:key"),
                                     values).mappings().one()
            scope.request_in_scope(user, old["id"], connection=connection)
            return old, False
        req = dict(row)
        connection.execute(text("""
            INSERT INTO request_messages (org_id,request_id,sender_type,sender_id,body)
            VALUES (:org,:request,'user',:user,:body)
        """), {**values, "request": req["id"], "body": body})
        record(connection, req, "created", actor_type="user", actor_id=user.id, to_status="received", trace_id=trace_id)
    background_tasks.add_task(run_request, req["id"])
    return req, True


def _expire(connection, req):
    expired = connection.scalar(text("""
        SELECT EXISTS (SELECT 1 FROM cards c WHERE c.request_id=:id AND
          ((c.status='on_hold' AND c.hold_until<=CURRENT_DATE) OR EXISTS (
            SELECT 1 FROM consultation_slots s WHERE s.card_id=c.id AND s.status='chosen_by_parent'
              AND s.chosen_at<=now()-interval '24 hours')))
    """), {"id": req["id"]})
    if not expired:
        return req
    req = _lock(connection, req["id"])
    cards = connection.execute(text("SELECT * FROM cards WHERE request_id=:id ORDER BY id FOR NO KEY UPDATE"),
                               {"id": req["id"]}).mappings().all()
    for row in cards:
        card = dict(row)
        if card["status"] == "on_hold" and connection.scalar(text("SELECT :until<=CURRENT_DATE"), {"until": card["hold_until"]}):
            card = dict(connection.execute(text("""
                UPDATE cards SET status='pending',hold_until=NULL,version=version+1,updated_at=clock_timestamp()
                WHERE id=:id RETURNING *
            """), {"id": card["id"]}).mappings().one())
            set_status(connection, req, "awaiting_review", action="resumed", card=card, automatic=True)
        reset = connection.execute(text("""
            UPDATE consultation_slots SET status='proposed',chosen_at=NULL
            WHERE card_id=:id AND status='chosen_by_parent' AND chosen_at<=now()-interval '24 hours' RETURNING id
        """), {"id": card["id"]}).all()
        if reset:
            set_status(connection, req, "needs_info", action="slot_hold_expired", card=card)
    return req


def _hold_until(connection, req):
    return connection.scalar(text("""
        SELECT hold_until FROM cards WHERE request_id=:id AND org_id=:org AND status='on_hold'
        ORDER BY created_at,id LIMIT 1
    """), {"id": req["id"], "org": req["org_id"]})


def choices(user, request_id, body):
    from app.modules.consultations.slots import propose_slots

    with transaction() as connection:
        scope.request_in_scope(user, request_id, connection=connection)
        req = _expire(connection, _lock(connection, request_id))
        if req["type"] != "consultation" or req["status"] != "needs_info":
            raise ApiError(409, "INVALID_TRANSITION")
        card = connection.execute(text("""
            SELECT * FROM cards WHERE request_id=:id AND kind='consult_slots'
              AND status IN ('pending','in_review') ORDER BY created_at DESC,id DESC
            LIMIT 1 FOR NO KEY UPDATE
        """), {"id": request_id}).mappings().one_or_none()
        if card is None:
            raise ApiError(409, "INVALID_TRANSITION")
        current_round = connection.scalar(text("SELECT coalesce(max(round),0) FROM consultation_slots WHERE card_id=:id"),
                                          {"id": card["id"]})
        slots = connection.execute(text("""
            SELECT id,status FROM consultation_slots WHERE card_id=:id AND round=:round AND status='proposed'
            ORDER BY rank FOR NO KEY UPDATE
        """), {"id": card["id"], "round": current_round}).mappings().all()
        if body.none_fit:
            connection.execute(text("UPDATE consultation_slots SET status='discarded' WHERE card_id=:id"),
                               {"id": card["id"]})
            slots = propose_slots(connection, req, card, card["assignee_id"], current_round + 1)
            record(connection, req, "info_requested", card=card, actor_type="user", actor_id=user.id,
                   preferred_times=body.preferred_times)
        else:
            selected = [row for row in slots if row["id"] in body.slot_ids]
            if len(selected) != len(body.slot_ids):
                scope._checked(user, None, False, "slot", body.slot_ids)
            slots = [dict(connection.execute(text("""
                UPDATE consultation_slots SET status='chosen_by_parent',chosen_at=clock_timestamp()
                WHERE id=:id RETURNING id,status
            """), {"id": row["id"]}).mappings().one()) for row in selected]
            set_status(connection, req, "awaiting_review", action="checked", card=card,
                       actor_type="user", actor_id=user.id)
        return {"slots": [dict(row) for row in slots], "request": {
            key: req[key] for key in ("id", "status", "parent_confirmed_at")}}


def detail(user, request_id):
    with transaction() as connection:
        req = dict(scope.request_in_scope(user, request_id, connection=connection))
        _parent_readable(user, req)
        if req["type"] in DEFERRED_REQUEST_TYPES:
            first = connection.execute(text("""
                SELECT id,sender_type,body,created_at FROM request_messages
                WHERE request_id=:id AND org_id=:org AND sender_type='user' ORDER BY id LIMIT 1
            """), {"id": request_id, "org": user.org_id}).mappings().all()
            return {"request": {**{key: req[key] for key in (
                        "id", "type", "title", "status", "created_at", "updated_at")},
                        "status_label": staff_label(req["status"], req["type"]), "missing_fields": []},
                    "messages": [dict(row) for row in first], "timeline": [], "sources": []}
        req = _expire(connection, req)
        values = {"id": request_id, "org": user.org_id, "parent": user.role == "parent"}
        messages = connection.execute(text("""
            SELECT id,sender_type,body,created_at FROM request_messages
            WHERE request_id=:id AND org_id=:org ORDER BY id
        """), values).mappings().all()
        label = parent_label if user.role == "parent" else staff_label
        timeline = []
        for event in connection.execute(text("""
            SELECT to_status,created_at FROM events WHERE request_id=:id AND org_id=:org AND to_status IS NOT NULL ORDER BY id
        """), values).mappings():
            name = label(event["to_status"], req["type"])
            if not timeline or timeline[-1]["label"] != name:
                timeline.append({"label": name, "at": event["created_at"]})
        consultation = None
        if req["type"] == "consultation":
            slots = connection.execute(text("""
                SELECT s.id,lower(s.period) AS start,upper(s.period) AS end,r.name AS room,s.status
                FROM consultation_slots s JOIN cards c ON (c.id,c.org_id)=(s.card_id,s.org_id)
                JOIN rooms r ON (r.id,r.org_id)=(s.room_id,s.org_id)
                WHERE c.request_id=:id AND c.org_id=:org AND s.status<>'discarded' ORDER BY s.round,s.rank,s.id
            """), values).mappings().all()
            booking = connection.execute(text("""
                SELECT b.id,lower(b.period) AS start,upper(b.period) AS end,r.name AS room
                FROM consultation_bookings b JOIN rooms r ON (r.id,r.org_id)=(b.room_id,b.org_id)
                WHERE b.request_id=:id AND b.org_id=:org AND b.status='confirmed'
            """), values).mappings().one_or_none()
            def period(row):
                return {"id": row["id"], "period": {"start": row["start"], "end": row["end"]}, "room": row["room"]}
            consultation = {"slots": [period(row) | {"status": row["status"]} for row in slots],
                            "booking": period(booking) if booking else None}
        rejection = connection.execute(text("""
            SELECT a.reason_code,a.reason_text FROM approvals a JOIN cards c ON (c.id,c.org_id)=(a.card_id,a.org_id)
            WHERE c.request_id=:id AND c.org_id=:org AND a.decision='dismiss' ORDER BY a.id DESC LIMIT 1
        """), values).mappings().one_or_none() if req["status"] == "rejected" else None
        sources = connection.execute(text("""
            SELECT d.title AS document_title,ch.location,d.effective_from
            FROM cards c JOIN card_evidence e ON (e.card_id,e.org_id)=(c.id,c.org_id)
            JOIN document_chunks ch ON (ch.id,ch.org_id)=(e.chunk_id,e.org_id)
            JOIN documents d ON (d.id,d.org_id)=(ch.document_id,ch.org_id)
            WHERE c.request_id=:id AND c.org_id=:org AND (NOT :parent OR d.visibility IN ('parents','all'))
              AND EXISTS (SELECT 1 FROM approvals a WHERE (a.card_id,a.org_id)=(c.id,c.org_id)
                          AND a.decision IN ('approve','edit_approve'))
            ORDER BY c.created_at,c.id,e.rank,ch.id
        """), values).mappings().all() if req["status"] in ("sent_or_booked", "completed") else []
        return {"request": {**{key: req[key] for key in (
                    "id", "type", "title", "status", "missing_fields", "parent_confirmed_at", "created_at", "updated_at")},
                    "status_label": label(req["status"], req["type"]), "hold_until": _hold_until(connection, req)},
                "messages": [dict(row) for row in messages], "sources": [dict(row) for row in sources],
                "timeline": timeline, "consultation": consultation, "rejection": dict(rejection) if rejection else None}


def listing(user, status, page, size, sort):
    with transaction() as connection:
        # 본인 요청의 만료를 먼저 반영한 뒤 상태·정렬·쪽 나누기를 적용해요.
        rows = connection.execute(text("""
            SELECT * FROM requests WHERE org_id=:org AND requester_id=:user
              AND type IN ('inquiry','consultation','complaint') ORDER BY id
        """), {"org": user.org_id, "user": user.id}).mappings().all()
        requests = [_expire(connection, dict(row)) for row in rows]
        requests = [req for req in requests if status is None or req["status"] == status]
        requests.sort(key=lambda req: (req[sort.lstrip("-")], str(req["id"])), reverse=sort.startswith("-"))
        items = []
        for req in requests[(page-1)*size:page*size]:
            _readable(req)
            action = None
            if req["status"] == "needs_info":
                action = "시간을 골라 주세요" if req["type"] == "consultation" else "정보를 더 알려 주세요"
            if req["type"] == "complaint" and req["status"] == "sent_or_booked" and req["parent_confirmed_at"] is None:
                action = "답변을 확인해 주세요"
            items.append({**{key: req[key] for key in ("id", "type", "title", "status", "updated_at")},
                          "status_label": parent_label(req["status"], req["type"]), "next_action": action,
                          "hold_until": _hold_until(connection, req)})
        return {"items": items, "total": len(requests), "page": page, "size": size}


def message(user, request_id, body, *, background_tasks):
    rerun = False
    with transaction() as connection:
        initial = scope.request_in_scope(user, request_id, connection=connection)
        _parent_readable(user, initial)
        req = _expire(connection, _lock(connection, request_id))
        _readable(req)
        if req["status"] in ("completed", "rejected"):
            raise ApiError(409, "INVALID_TRANSITION")
        msg = dict(connection.execute(text("""
            INSERT INTO request_messages (org_id,request_id,sender_type,sender_id,body)
            VALUES (:org,:id,'user',:user,:body) RETURNING id,sender_type,body,created_at
        """), {"org": user.org_id, "id": request_id, "user": user.id, "body": body}).mappings().one())
        connection.execute(text("UPDATE requests SET updated_at=clock_timestamp() WHERE id=:id"), {"id": request_id})
        record(connection, req, "created", actor_type="user", actor_id=user.id, message_id=msg["id"])
        if req["type"] == "complaint" and req["status"] == "sent_or_booked":
            row = connection.execute(text("""
                SELECT * FROM cards WHERE request_id=:id AND kind='reply_draft' ORDER BY created_at DESC,id DESC LIMIT 1 FOR UPDATE
            """), {"id": request_id}).mappings().one_or_none()
            if row is None:
                raise ApiError(409, "INVALID_TRANSITION")
            card = dict(connection.execute(text("""
                UPDATE cards SET status='pending',closed_at=NULL,version=version+1,updated_at=clock_timestamp()
                WHERE id=:id RETURNING *
            """), {"id": row["id"]}).mappings().one())
            req["parent_confirmed_at"] = None
            connection.execute(text("UPDATE requests SET parent_confirmed_at=NULL WHERE id=:id"), {"id": request_id})
            set_status(connection, req, "awaiting_review", action="returned", card=card, actor_type="user", actor_id=user.id)
        elif req["status"] == "needs_info" and req["type"] != "consultation":
            rerun = True
    if rerun:
        background_tasks.add_task(run_request, request_id)
    return {"message": msg}


def confirm(user, request_id):
    with transaction() as connection:
        initial = scope.request_in_scope(user, request_id, connection=connection)
        _parent_readable(user, initial)
        req = _lock(connection, request_id)
        if req["type"] != "complaint" or req["status"] != "sent_or_booked":
            raise ApiError(409, "INVALID_TRANSITION")
        if req["parent_confirmed_at"] is None:
            req.update(connection.execute(text("""
                UPDATE requests SET parent_confirmed_at=clock_timestamp(),updated_at=clock_timestamp()
                WHERE id=:id RETURNING *
            """), {"id": request_id}).mappings().one())
            record(connection, req, "parent_confirmed", actor_type="user", actor_id=user.id)
        return {"request": {key: req[key] for key in ("id", "status", "parent_confirmed_at")}}


def stream(user, request_id):
    from app.modules.requests.streams import stream_request
    return stream_request(user, request_id)
