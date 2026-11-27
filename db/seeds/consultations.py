"""상담 요청부터 확정·완료까지 이어진 가상 사례. 날짜는 최초 적재일 기준이에요."""

import json
from datetime import datetime, time, timedelta

from sqlalchemy import text

from app.core.schedule import KST
from app.mock import seed
from app.modules.consultations.bookings import lock_resources
from app.modules.notifications.notifications import notify_event


def seed_consultations(connection, *, on=None):
    """오늘·내일 15시 예약과 어제 완료 사례를 넣고, 이미 있는 사례는 보존해요."""
    on = on or datetime.now(KST).date()
    for key, offset, classroom, child, parent, teacher in (
        ("b1", 0, seed.CLASS_STAR, seed.CHILD, seed.PARENT, seed.TEACHER),
        ("b2", 1, seed.CLASS_SUN, seed.CHILD_OTHER, seed.PARENT_OTHER, seed.TEACHER_OTHER),
        ("b3", -1, seed.CLASS_STAR, seed.demo_id("503"), seed.PARENT_OTHER, seed.TEACHER),
    ):
        request_id, card_id, booking_id = (seed.demo_id(prefix + key) for prefix in ("7", "8", "9"))
        if connection.scalar(text("SELECT EXISTS (SELECT 1 FROM requests WHERE id=:id)"), {"id": request_id}):
            continue
        # 퇴소로 끊긴 보호자 연결이나 사용자가 잡은 일정은 시연 데이터로 덮지 않아요.
        if not connection.scalar(text("""
            SELECT EXISTS (SELECT 1 FROM child_guardians g JOIN users u ON (u.id,u.org_id)=(g.user_id,g.org_id)
              WHERE g.org_id=:org AND g.child_id=:child AND g.user_id=:parent AND u.is_active)
        """), {"org": seed.ORG, "child": child, "parent": parent}):
            continue
        start = datetime.combine(on + timedelta(days=offset), time(15), KST)
        created = datetime.combine(on - timedelta(days=2), time(9), KST)
        values = {"org": seed.ORG, "request": request_id, "card": card_id, "booking": booking_id,
                  "classroom": classroom, "child": child, "parent": parent, "teacher": teacher, "room": seed.ROOM,
                  "start": start, "end": start + timedelta(minutes=30), "created": created,
                  "chosen": created + timedelta(minutes=3), "booked": created + timedelta(minutes=5),
                  "body": "아이의 놀이와 친구 관계를 상담하고 싶어요. (가상)", "key": f"demo:consultation:{key}"}
        lock_resources(connection, [{"teacher_id": teacher, "room_id": seed.ROOM}])
        if connection.scalar(text("""
            SELECT EXISTS (SELECT 1 FROM staff_busy_blocks WHERE org_id=:org AND user_id=:teacher
              AND period && tstzrange(:start,:end,'[)'))
            OR EXISTS (SELECT 1 FROM consultation_bookings WHERE org_id=:org AND status='confirmed'
              AND (teacher_id=:teacher OR room_id=:room)
              AND tstzrange(lower(period),coalesce(expected_end_at,upper(period)),'[)') && tstzrange(:start,:end,'[)'))
        """), values):
            continue
        req = connection.execute(text("""
            INSERT INTO requests(id,org_id,classroom_id,child_id,requester_id,client_request_id,type,title,body,
                                 status,assignee_id,created_at,updated_at)
            VALUES (:request,:org,:classroom,:child,:parent,:key,'consultation','아이 생활 상담 (가상)',:body,
                    'sent_or_booked',:teacher,:created,:booked)
            ON CONFLICT DO NOTHING RETURNING *
        """), values).mappings().one_or_none()
        if req is None:
            continue
        connection.execute(text("""
            INSERT INTO request_messages(org_id,request_id,sender_type,sender_id,body,created_at)
            VALUES (:org,:request,'user',:parent,:body,:created)
        """), values)
        card = connection.execute(text("""
            INSERT INTO cards(id,org_id,request_id,kind,status,assignee_id,draft,version,created_at,updated_at,closed_at)
            VALUES (:card,:org,:request,'consult_slots','done',:teacher,'{"summary":"가상 상담 예약"}',
                    2,:created,:booked,:booked) RETURNING *
        """), values).mappings().one()
        slot_id = connection.scalar(text("""
            INSERT INTO consultation_slots(org_id,card_id,teacher_id,room_id,period,rank,status,chosen_at,created_at)
            VALUES (:org,:card,:teacher,:room,tstzrange(:start,:end,'[)'),1,'confirmed',:chosen,:created) RETURNING id
        """), values)
        connection.execute(text("""
            INSERT INTO consultation_bookings(id,org_id,request_id,slot_id,teacher_id,room_id,period,confirmed_by,created_at)
            VALUES (:booking,:org,:request,:slot,:teacher,:room,tstzrange(:start,:end,'[)'),:teacher,:booked)
        """), {**values, "slot": slot_id})
        connection.execute(text("""
            INSERT INTO approvals(org_id,card_id,card_version,decided_by,decision,created_at)
            VALUES (:org,:card,1,:teacher,'approve',:booked)
        """), values)
        steps = [
            ("created", None, "received", parent),
            ("classified", "received", "classified", None),
            ("info_requested", "classified", "needs_info", None),
            ("checked", "needs_info", "awaiting_review", parent),
            ("approved", "awaiting_review", "approved", teacher),
            ("booked", "approved", "sent_or_booked", teacher),
        ]
        if offset < 0:
            steps.append(("completed", "sent_or_booked", "completed", teacher))
        for minute, (action, before, after, actor) in enumerate(steps):
            at = values["end"] if action == "completed" else created + timedelta(minutes=minute)
            event = connection.execute(text("""
                INSERT INTO events(org_id,request_id,card_id,actor_type,actor_id,action,from_status,to_status,detail,created_at)
                VALUES (:org,:request,:card,:actor_type,:actor,:action,:before,:after,CAST(:detail AS jsonb),:at)
                RETURNING *
            """), {**values, "actor_type": "user" if actor else "system", "actor": actor, "action": action,
                   "before": before, "after": after, "at": at,
                   "detail": json.dumps({"is_virtual": True, "slot_id": slot_id})}).mappings().one()
            notify_event(connection, event, req, card)
            # 과거의 시연 알림은 이미 앱에 전달된 상태예요. 외부 발송은 하지 않아요.
            connection.execute(text("""
                UPDATE notifications SET status='sent',attempts=1,created_at=:at,sent_at=deliver_after,
                                         next_attempt_at=deliver_after
                WHERE org_id=:org AND request_id=:request AND status='pending'
            """), {**values, "at": at})
        if offset < 0:
            connection.execute(text("UPDATE consultation_bookings SET status='done' WHERE id=:booking"), values)
            connection.execute(text("""
                UPDATE requests SET status='completed',closed_at=:end,updated_at=:end WHERE id=:request
            """), values)
