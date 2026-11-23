"""예약 시간과 담임이 기록한 지연만 읽어요. 시간이 지났다고 지연을 추측하지 않아요."""

from datetime import timezone, timedelta

from app.core.schedule import KST

ENDING = "consultation_ending"
DELAYED = "consultation_delayed"
KINDS = (ENDING, DELAYED)


def valid_delay(start, scheduled_end, expected_end, now):
    return (expected_end.tzinfo is not None and start <= now
            and expected_end > max(scheduled_end, now)
            and expected_end <= scheduled_end + timedelta(hours=3)
            and expected_end.astimezone(KST).date() == start.astimezone(KST).date())


def notification_key(booking, kind, until, recipient):
    revision = (until or booking["end"]).astimezone(timezone.utc).isoformat()
    return f"consultation:{booking['id']}:{kind}:{revision}:{recipient}"


def alerts(bookings, now):
    for booking in bookings:
        if booking["status"] != "confirmed" or booking["end"] <= now:
            continue
        if booking["start"] <= now and booking["end"] - timedelta(minutes=10) <= now:
            yield booking, ENDING, None
        until = max((prior["expected_end_at"] for prior in bookings
                     if prior["status"] == "confirmed" and prior["org_id"] == booking["org_id"]
                     and prior["id"] != booking["id"] and prior["start"] <= now
                     and prior["scheduled_end"] <= booking["start"] and prior["expected_end_at"]
                     and prior["expected_end_at"] > max(now, booking["start"])
                     and (prior["teacher_id"] == booking["teacher_id"]
                          or prior["room_id"] == booking["room_id"])), default=None)
        if until:
            yield booking, DELAYED, until


def message(booking, kind, candidates):
    if kind == ENDING:
        return f"상담 예정 종료 {booking['end']:%m/%d %H:%M}까지 10분 이내예요. 마무리를 준비해 주세요."
    prefix = "앞 상담이 늦어져 예약 시간에 영향이 있어요. "
    if not candidates:
        return prefix + "가능한 대체 시간이 없어 선생님과 다른 날짜를 확인해 주세요."
    times = ", ".join(f"{s['start']:%m/%d %H:%M}~{s['end']:%H:%M}" for s in candidates)
    return prefix + f"대체 시간 제안: {times}. 확정된 시간이 아니에요. 선생님과 확인해 주세요."
