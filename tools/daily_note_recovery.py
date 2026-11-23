"""알림장 초안 incident 집계: 반 묶음 카드 이력을 Auto-Healing incident 기록 칸으로 모아 센다.

    PYTHONPATH=apps/api:. python tools/daily_note_recovery.py --since 2026-12-01 --until 2026-12-18

판정 규칙은 DB 스키마 설계서 2.6 '초안 실패와 복구 기록'과 같다. 이력의 칸만 읽고 메모 원문은 읽지 않는다.
"""

import argparse
import os
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from statistics import median

from sqlalchemy import create_engine, text

KST = timezone(timedelta(hours=9))
COLUMNS = ("incident_id", "detected_failure", "selected_strategy", "retry_count", "fallback_used",
           "recovery_status", "validation_result", "duration_ms")
EVENTS = """
    SELECT e.card_id, e.action, e.detail FROM events e
    JOIN cards c ON (c.id, c.org_id) = (e.card_id, e.org_id)
    WHERE c.subject_type = 'daily_note_batch' AND e.action IN ('tool_failed', 'agent_requeued', 'drafted')
      AND e.created_at >= :since AND e.created_at < :until
    ORDER BY e.card_id, e.id
"""


def summarize(connection, since, until):
    jobs = {}
    for row in connection.execute(text(EVENTS), {"since": since, "until": until}).mappings():
        jobs.setdefault(row["card_id"], []).append(row)
    incidents, handed_children = [], 0
    for events in jobs.values():
        drafted = [e["detail"] for e in events if e["action"] == "drafted"]
        # 마지막 저장에서 템플릿으로 남은 아이는 담임이 직접 쓴다.
        handed_children += drafted[-1]["draft_failed"] if drafted else 0
        first = next((i for i, e in enumerate(events) if e["action"] == "tool_failed"), None)
        if first is None:
            continue
        after = events[first:]
        closing = [e["detail"] for e in after if e["action"] != "agent_requeued"][-1]
        strategies = sorted({e["detail"]["selected_strategy"] for e in after if e["action"] == "agent_requeued"})
        incidents.append({
            "incident_id": closing["incident_id"], "detected_failure": events[first]["detail"]["detected_failure"],
            "selected_strategy": "+".join(strategies + ["template_fallback"] * closing["fallback_used"]) or "none",
            "retry_count": max(e["detail"]["retry_count"] for e in after), "fallback_used": closing["fallback_used"],
            # 다시 넣은 뒤 아직 끝나지 않았으면 대기로 센다.
            "recovery_status": "pending" if after[-1]["action"] == "agent_requeued" else closing["recovery_status"],
            "validation_result": closing["validation_result"], "duration_ms": closing.get("duration_ms"),
            "detection_ms": events[first]["detail"]["detection_ms"]})
    counts = Counter(i["recovery_status"] for i in incidents)
    target = counts["recovered"] + counts["fallback"] + counts["handed_off"]
    detection = [i["detection_ms"] for i in incidents]
    duration = [i["duration_ms"] for i in incidents if i["duration_ms"] is not None]
    return {"incidents": incidents, "recovered": counts["recovered"], "fallback": counts["fallback"],
            "handed_off": counts["handed_off"], "pending": counts["pending"], "handed_children": handed_children,
            "recovery_rate": counts["recovered"] / target if target else None,
            "detection_ms": (median(detection), max(detection)) if detection else None,
            "duration_ms": (median(duration), max(duration)) if duration else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db-url", default=os.getenv("DATABASE_URL"))
    parser.add_argument("--since", type=date.fromisoformat, required=True, help="KST 날짜, 이날 0시부터")
    parser.add_argument("--until", type=date.fromisoformat, default=datetime.now(KST).date(), help="KST 날짜, 이날까지")
    args = parser.parse_args()
    if not args.db_url:
        parser.error("--db-url이나 DATABASE_URL이 필요해요.")
    with create_engine(args.db_url).connect() as connection:
        result = summarize(connection, datetime.combine(args.since, time.min, KST),
                           datetime.combine(args.until + timedelta(days=1), time.min, KST))
    rate, detection, duration = result["recovery_rate"], result["detection_ms"], result["duration_ms"]
    print(f"기간: {args.since} ~ {args.until} (KST)\n\n| 항목 | 값 |\n| --- | --- |")
    for label, value in (("감지한 incident", len(result["incidents"])), ("정상 복구", result["recovered"]),
                         ("대체 응답", result["fallback"]), ("사람 이관", result["handed_off"]),
                         ("다시 시도 전·진행 중", result["pending"]),
                         ("복구율(정상 복구 ÷ 다시 시도해 끝난 incident)", "-" if rate is None else f"{rate:.0%}"),
                         ("감지 시간 중앙값·최대(ms)", "-" if detection is None else "%d · %d" % detection),
                         ("복구 시간 중앙값·최대(ms)", "-" if duration is None else "%d · %d" % duration),
                         ("담임이 직접 쓴 아이(템플릿)", result["handed_children"])):
        print(f"| {label} | {value} |")
    print("\n| " + " | ".join(COLUMNS) + " |\n|" + " --- |" * len(COLUMNS))
    for incident in result["incidents"]:
        print("| " + " | ".join("-" if incident[c] is None else str(incident[c]) for c in COLUMNS) + " |")


if __name__ == "__main__":
    main()
