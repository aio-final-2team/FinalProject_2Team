"""모의 시연도 같은 T48 규칙을 써요. 주기 실행은 DB 워커만 맡아요."""

from datetime import datetime, time, timedelta

from app.core.consultation_alerts import ENDING, alerts, message
from app.core.constants import NOTIFICATION_TITLES
from app.core.errors import ApiError
from app.core.schedule import KST, deliver_after, working_day
from app.mock import store
from app.mock.records import Notification


def report_delay(user, booking_id, expected_end_at, *, now=None):
    now = now or store.now()
    with store._lock:
        booking = store.state().bookings.get(booking_id)
        if booking is None or booking.org_id != user.org_id:
            store.deny(user)
        req = store.request_in_scope(user, booking.request_id)
        if user.role != "teacher" or booking.teacher_id != user.id:
            raise ApiError(403, "FORBIDDEN_ROLE")
        if booking.status != "confirmed" or req.status != "sent_or_booked":
            raise ApiError(409, "INVALID_TRANSITION")
        if (expected_end_at.tzinfo is None or booking.period["start"] > now
                or expected_end_at <= max(booking.period["end"], now)):
            raise ApiError(422, "VALIDATION_FAILED")
        expected_end_at = expected_end_at.astimezone(KST)
        if booking.expected_end_at != expected_end_at:
            booking.expected_end_at = expected_end_at
            store.add_event(req, "consultation_delay_reported", actor_type="user", actor_id=user.id,
                            booking_id=str(booking_id), expected_end_at=expected_end_at.isoformat())


def alternatives(booking, until, now):
    # 모의 후보는 기존 대역과 같은 평일 15시·16시예요. 실제 빈 시간·개인 규칙은 DB가 계산해요.
    state, result = store.state(), []
    for offset in range(14):
        day = now.date()+timedelta(days=offset)
        if not working_day(day):
            continue
        for hour in (15, 16):
            start = datetime.combine(day, time(hour), KST)
            end = start+timedelta(minutes=30)
            if start <= now or start < until or deliver_after(start, "teacher") != start:
                continue
            for room in state.rooms.values():
                if room.org_id != booking["org_id"]:
                    continue
                if any(b.org_id == booking["org_id"] and b.status == "confirmed"
                       and (b.teacher_id == booking["teacher_id"] or b.room_id == room.id)
                       and start < (b.expected_end_at or b.period["end"]) and b.period["start"] < end
                       for b in state.bookings.values()):
                    continue
                if any(s.org_id == booking["org_id"] and s.status == "chosen_by_parent"
                       and s.chosen_at > now-timedelta(hours=24)
                       and (s.teacher_id == booking["teacher_id"] or s.room_id == room.id)
                       and start < s.period["end"] and s.period["start"] < end for s in state.slots.values()):
                    continue
                result.append({"start": start, "end": end})
                break
            if len(result) == 3:
                return result
    return result


def sweep_consultation_notifications(now=None):
    now = (now or store.now()).astimezone(KST)
    count = 0
    with store._lock:
        state = store.state()
        rows = [{**b.__dict__, "start": b.period["start"], "scheduled_end": b.period["end"],
                 "end": b.expected_end_at or b.period["end"], "requester_id": state.requests[b.request_id].requester_id}
                for b in state.bookings.values() if state.requests[b.request_id].status == "sent_or_booked"
                and state.requests[b.request_id].type == "consultation"]
        for booking, kind, until in alerts(rows, now):
            recipients = [booking["teacher_id"]] if kind == ENDING else [booking["teacher_id"], booking["requester_id"]]
            saved, candidates = 0, alternatives(booking, until, now) if until else []
            for recipient in recipients:
                key = f"consultation:{booking['id']}:{kind}:{recipient}"
                user = state.users.get(recipient)
                if (user is None or not user.is_active or user.org_id != booking["org_id"]
                        or any(n.dedupe_key == key for n in state.notifications.values())):
                    continue
                after = deliver_after(now, user.role)
                if after >= booking["end"]:
                    continue
                row = Notification(id=state.next_int(), org_id=booking["org_id"], recipient_id=recipient,
                                   request_id=booking["request_id"], kind=kind, title=NOTIFICATION_TITLES[kind],
                                   body=message(booking, kind, candidates), dedupe_key=key, created_at=now, deliver_after=after)
                state.notifications[row.id] = row
                saved += 1
            if saved:
                store.add_event(state.requests[booking["request_id"]], "consultation_reminded",
                                booking_id=str(booking["id"]), kind=kind)
                count += saved
    return count
