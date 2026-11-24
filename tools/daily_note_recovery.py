"""알림장 초안 incident 집계: 반 묶음 카드 이력을 Auto-Healing incident 기록 칸으로 모아 센다.

    PYTHONPATH=apps/api:. python tools/daily_note_recovery.py --since 2026-12-01 --until 2026-12-18

판정 규칙은 DB 스키마 설계서 2.6 '초안 실패와 복구 기록'과 같다. 이력의 칸만 읽고 메모 원문은 읽지 않는다.
"""

import argparse
import os
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from statistics import mean, median

from sqlalchemy import create_engine, text

KST = timezone(timedelta(hours=9))
COLUMNS = ("incident_id", "detected_failure", "selected_strategy", "retry_count", "fallback_used",
           "recovery_status", "validation_result", "duration_ms", "trigger", "queue_wait_ms")
EVENTS = """
    SELECT e.id, e.created_at, e.card_id, c.subject_id AS input_id, e.action, e.actor_type, e.detail FROM events e
    JOIN cards c ON (c.id, c.org_id) = (e.card_id, e.org_id)
    WHERE c.subject_type = 'daily_note_batch' AND e.action IN ('tool_failed', 'agent_requeued', 'drafted')
      AND e.created_at >= :since AND e.created_at < :until
    ORDER BY e.card_id, e.created_at, e.id
"""


def child_recovery(connection, since, until, jobs):
    """draft_failed를 실제 기록한 아이만 추적한다. 교사 수정·확인은 AI 복구로 세지 않는다."""
    histories = {}
    for row in connection.execute(text("""
        SELECT n.input_id,n.child_id,e.created_at,e.to_status,e.detail FROM events e
        JOIN daily_notes n ON (n.id,n.org_id)=(e.daily_note_id,e.org_id)
        WHERE e.action='daily_note_drafted' AND e.actor_type='agent'
          AND e.created_at>=:since AND e.created_at<:until ORDER BY e.created_at,e.id
    """), {"since": since, "until": until}).mappings():
        histories.setdefault((row["input_id"], row["child_id"]), []).append(row)
    batches = {events[0]["input_id"]: events for events in jobs.values()}
    children, unmeasurable = [], 0
    for (input_id, child_id), events in histories.items():
        first = next((i for i, e in enumerate(events) if e["detail"].get("draft_failed") is True), None)
        if first is None:
            unmeasurable += int(any(e["to_status"] == "needs_check" and "draft_failed" not in e["detail"] for e in events))
            continue
        failure, later = events[first], events[first + 1:]
        success = next((e for e in later if e["to_status"] == "draft" and
                        e["detail"].get("open_check_count", 0) == 0), None)
        closing = success or (later[-1] if later else failure)
        trigger = closing["detail"].get("trigger", "teacher_regenerate" if closing["detail"].get("regenerated_by") else "unknown")
        if not later:
            attempts = [e for e in batches.get(input_id, []) if e["created_at"] > failure["created_at"]
                        and e["action"] == "agent_requeued"]
            if attempts:
                trigger = attempts[-1]["detail"].get("trigger", "teacher_regenerate" if attempts[-1]["actor_type"] == "user" else "auto_retry")
        waits = sum(e["detail"].get("queue_wait_ms", 0) for e in batches.get(input_id, [])
                    if failure["created_at"] < e["created_at"] <= closing["created_at"]
                    and e["action"] in ("drafted", "tool_failed"))
        duration = max(0, round((success["created_at"] - failure["created_at"]).total_seconds()*1000) - waits) if success else None
        children.append({"input_id": str(input_id), "child_id": str(child_id), "trigger": trigger,
                         "recovery_status": "recovered" if success else "handed_off",
                         "failed_at": failure["created_at"].isoformat(),
                         "recovered_at": success["created_at"].isoformat() if success else None,
                         "duration_ms": duration})
    durations = [c["duration_ms"] for c in children if c["duration_ms"] is not None]
    # 아직 재시도에 진입하지 못한 실패도 자동 복구 분모에서 빼지 않는다. 담임 경로는 별도다.
    automatic = [c for c in children if c["trigger"] in ("initial", "auto_retry")]
    recovered = sum(c["recovery_status"] == "recovered" for c in children)
    return {"children": children, "targets": len(children), "recovered": recovered,
            "handed_off": len(children)-recovered, "unmeasurable": unmeasurable,
            "not_retried": sum(c["trigger"] == "initial" for c in children),
            "teacher_regenerate": sum(c["trigger"] == "teacher_regenerate" for c in children),
            "recovery_rate": recovered/len(children) if children else None,
            "automatic_targets": len(automatic),
            "automatic_recovery_rate": sum(c["recovery_status"] == "recovered" for c in automatic)/len(automatic) if automatic else None,
            "duration_ms": {"mean": mean(durations), "median": median(durations), "max": max(durations)} if durations else None}


def summarize(connection, since, until):
    jobs = {}
    for row in connection.execute(text(EVENTS), {"since": since, "until": until}).mappings():
        jobs.setdefault(row["card_id"], []).append(row)
    incidents, handed_children = [], 0
    for events in jobs.values():
        drafted = [e["detail"] for e in events if e["action"] == "drafted"]
        # 마지막 저장에서 템플릿으로 남은 아이는 담임이 직접 쓴다.
        handed_children += drafted[-1]["draft_failed"] if drafted else 0
        first = next((i for i, e in enumerate(events) if e["action"] == "tool_failed" or
                      e["detail"].get("validation_result") == "all_children_template"), None)
        if first is None:
            continue
        after = events[first:]
        closing = [e["detail"] for e in after if e["action"] != "agent_requeued"][-1]
        failure = events[first]["detail"]
        strategies = sorted({e["detail"]["selected_strategy"] for e in after if e["action"] == "agent_requeued"})
        incidents.append({
            "incident_id": closing["incident_id"], "detected_failure": failure.get("detected_failure", "all_children_template"),
            "selected_strategy": "+".join(strategies + ["template_fallback"] * closing["fallback_used"]) or "none",
            "retry_count": sum(e["action"] == "agent_requeued" and e["actor_type"] == "system" for e in events),
            "fallback_used": closing["fallback_used"],
            # 다시 넣은 뒤 아직 끝나지 않았으면 대기로 센다.
            "recovery_status": "pending" if after[-1]["action"] == "agent_requeued" else closing.get("recovery_status",
                {"all_children_passed": "recovered", "some_children_template": "fallback"}.get(closing["validation_result"], "handed_off")),
            "validation_result": closing["validation_result"], "duration_ms": closing.get("duration_ms"),
            "queue_wait_ms": sum(e["detail"].get("queue_wait_ms", 0) for e in after[1:] if e["action"] in ("drafted", "tool_failed")),
            "trigger": after[-1]["detail"].get("trigger", "unknown"),
            "detection_ms": failure.get("detection_ms")})
    counts = Counter(i["recovery_status"] for i in incidents)
    # 결과서에서 다른 분모(예: 담임 다시 만들기만)로도 계산할 수 있게 전략별로도 나눠 센다.
    by_strategy = {}
    for incident in incidents:
        by_strategy.setdefault(incident["selected_strategy"], Counter())[incident["recovery_status"]] += 1
    target = counts["recovered"] + counts["fallback"] + counts["handed_off"]
    detection = [i["detection_ms"] for i in incidents if i["detection_ms"] is not None]
    duration = [i["duration_ms"] for i in incidents if i["duration_ms"] is not None]
    return {"incidents": incidents, "recovered": counts["recovered"], "fallback": counts["fallback"],
            "handed_off": counts["handed_off"], "pending": counts["pending"], "handed_children": handed_children,
            "by_strategy": {name: dict(c) for name, c in sorted(by_strategy.items())},
            "recovery_rate": counts["recovered"] / target if target else None,
            "child_recovery": child_recovery(connection, since, until, jobs),
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
    statuses = ("recovered", "fallback", "handed_off", "pending")
    print("\n| selected_strategy | incident | 정상 복구 | 대체 응답 | 사람 이관 | 대기 |\n|" + " --- |" * 6)
    for name, c in result["by_strategy"].items():
        print(f"| {name} | {sum(c.values())} | " + " | ".join(str(c.get(k, 0)) for k in statuses) + " |")
    print("\n| " + " | ".join(COLUMNS) + " |\n|" + " --- |" * len(COLUMNS))
    for incident in result["incidents"]:
        print("| " + " | ".join("-" if incident[c] is None else str(incident[c]) for c in COLUMNS) + " |")
    children = result["child_recovery"]
    print("\n아이별 draft_failed 복구(교사 다시 만들기 포함; 자동 경로는 별도):")
    print(f"대상 {children['targets']} · 검사 통과 {children['recovered']} · 사람 이관 {children['handed_off']} · 과거 측정 불가 {children['unmeasurable']}")
    print(f"자동 경로 대상 {children['automatic_targets']} · 자동 복구율 {children['automatic_recovery_rate']} · 시간(ms) {children['duration_ms']}")
    print("\n| input_id | child_id | trigger | recovery_status | failed_at | recovered_at | duration_ms |\n| --- | --- | --- | --- | --- | --- | --- |")
    for child in children["children"]:
        print("| " + " | ".join("-" if value is None else str(value) for value in child.values()) + " |")


if __name__ == "__main__":
    main()
