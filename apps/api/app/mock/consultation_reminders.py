"""모의 시연도 같은 T48 규칙을 써요. 주기 실행은 DB 워커만 맡아요."""

from datetime import datetime, time, timedelta

from app.core.consultation_alerts import DELAYED, ENDING, alerts, message, notification_key, valid_delay
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
        store.classroom_in_scope(user, req.classroom_id)
        if booking.status != "confirmed" or req.status != "sent_or_booked":
            raise ApiError(409, "INVALID_TRANSITION")
        if not valid_delay(booking.period["start"], booking.period["end"], expected_end_at, now):
            raise ApiError(422, "VALIDATION_FAILED")
        expected_end_at = expected_end_at.astimezone(KST)
        if booking.expected_end_at != expected_end_at:
            booking.expected_end_at = expected_end_at
            store.add_event(req, "consultation_delay_reported", actor_type="user", actor_id=user.id,
                            booking_id=str(booking_id), expected_end_at=expected_end_at.isoformat())
            current = {**booking.__dict__, "end": expected_end_at}
            supersede(current, ENDING, [notification_key(current, ENDING, None, user.id)])
        affected = sum(b.status == "confirmed" and b.org_id == booking.org_id and b.id != booking.id
                       and state_req.status == "sent_or_booked" and state_req.type == "consultation"
                       and booking.period["end"] <= b.period["start"] < expected_end_at
                       and (b.expected_end_at or b.period["end"]) > now
                       and (b.teacher_id == booking.teacher_id or b.room_id == booking.room_id)
                       for b in store.state().bookings.values()
                       for state_req in [store.state().requests[b.request_id]])
        return {"booking": {"id": booking_id, "period": booking.period, "status": booking.status,
                            "expected_end_at": expected_end_at}, "affected_bookings": affected}


def supersede(booking, kind, keys):
    state = store.state()
    for n in list(state.notifications.values()):
        if (n.request_id != booking["request_id"] or n.kind != kind
                or not n.dedupe_key.startswith(f"consultation:{booking['id']}:{kind}:") or n.dedupe_key in keys
                or any(e.action == "consultation_reminded" and e.detail.get("outcome") == "superseded"
                       and e.detail.get("notification_id") == n.id for e in state.events)):
            continue
        if n.status == "pending":
            n.status = "held"
        store.add_event(state.requests[booking["request_id"]], "consultation_reminded",
                        booking_id=str(booking["id"]), kind=kind, notification_id=n.id, outcome="superseded")


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
        due = list(alerts(rows, now))
        delayed = {b["id"]: [notification_key(b, kind, until, recipient)
                              for recipient in (b["teacher_id"], b["requester_id"])]
                   for b, kind, until in due if kind == DELAYED}
        for row in rows:
            supersede(row, DELAYED, delayed.get(row["id"], []))
        for booking, kind, until in due:
            recipients = [booking["teacher_id"]] if kind == ENDING else [booking["teacher_id"], booking["requester_id"]]
            keys = [notification_key(booking, kind, until, recipient) for recipient in recipients]
            if all(any(n.dedupe_key == key for n in state.notifications.values()) for key in keys):
                continue
            supersede(booking, kind, keys)
            saved, candidates = 0, alternatives(booking, until, now) if until else []
            for recipient, key in zip(recipients, keys):
                user = state.users.get(recipient)
                if (user is None or not user.is_active or user.org_id != booking["org_id"]
                        or any(n.dedupe_key == key for n in state.notifications.values())):
                    continue
                after = now if kind == ENDING else deliver_after(now, user.role)
                if after >= booking["end"]:
                    continue
                row = Notification(id=state.next_int(), org_id=booking["org_id"], recipient_id=recipient,
                                   request_id=booking["request_id"], kind=kind, title=NOTIFICATION_TITLES[kind],
                                   body=message(booking, kind, candidates), dedupe_key=key, created_at=now, deliver_after=after)
                state.notifications[row.id] = row
                saved += 1
            if saved:
                store.add_event(state.requests[booking["request_id"]], "consultation_reminded",
                                booking_id=str(booking["id"]), kind=kind, until=(until or booking["end"]).isoformat(),
                                candidates=[{k: v.isoformat() for k, v in candidate.items()} for candidate in candidates])
                count += saved
    return count
