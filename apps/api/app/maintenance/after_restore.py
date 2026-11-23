"""백업 뒤에 지우거나 좁힌 것을 복원한 DB에 다시 적용한다.

export: 복원하기 전, 지금 DB에서 백업 시각 뒤의 변경을 JSON으로 뽑는다.
apply: 복원한 DB에 그 JSON을 적용한다. 두 번 돌려도 결과가 같다. 파일은 지우지 않으니 다음에 media_sweep을 돌린다.
"""

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app.core.db import transaction
from app.maintenance import withdraw_child

FEED_ACTIONS = ("feed_post_deleted", "feed_post_hidden", "photo_scope_changed")
# 이력 시각은 트랜잭션 시작 시각이다. 백업 직전에 시작해 덤프 뒤에 커밋된 변경도 잡도록 앞을 넉넉히 본다.
MARGIN = timedelta(minutes=10)


def rows(connection, sql, **params):
    return [dict(r) for r in connection.execute(text(sql), params).mappings()]


def export(connection, since):
    start = since - MARGIN
    events = rows(connection, """
        SELECT id,org_id,actor_type,actor_id,agent_name,action,detail,created_at FROM events
        WHERE created_at > :start AND action = ANY(:actions) ORDER BY id
    """, start=start, actions=list(FEED_ACTIONS))
    scopes = {}
    for event in events:
        if event["action"] == "photo_scope_changed":
            scopes[event["detail"]["child_id"]] = {"child_id": event["detail"]["child_id"], "org_id": event["org_id"],
                                                   "photo_scope": event["detail"]["after"]}
    return {
        "since": since.isoformat(), "exported_at": datetime.now(timezone.utc).isoformat(),
        "posts_deleted": rows(connection, "SELECT id,org_id,deleted_at FROM feed_posts WHERE deleted_at > :start "
                                          "ORDER BY deleted_at,id", start=start),
        "posts_hidden": [{"id": e["detail"]["post_id"], "org_id": e["org_id"]}
                         for e in events if e["action"] == "feed_post_hidden"],
        "photo_scopes": list(scopes.values()),
        "memories_deleted": rows(connection, "SELECT id,org_id,deleted_at FROM memories WHERE deleted_at > :start "
                                             "ORDER BY id", start=start),
        "withdrawn_children": [{"child_id": e["detail"]["child_id"], "org_id": e["org_id"]}
                               for e in events if e["detail"].get("withdrawn")],
        "events": [{k: v for k, v in e.items() if k != "id"} for e in events],
    }


def apply(connection, data):
    count = {}

    def run(name, sql, items):
        count[name] = sum(connection.execute(text(sql), item).rowcount for item in items)

    run("posts_deleted", "UPDATE feed_posts SET deleted_at=:deleted_at WHERE id=:id AND org_id=:org_id "
                         "AND deleted_at IS NULL", data["posts_deleted"])
    run("posts_hidden", "UPDATE feed_posts SET status='hidden' WHERE id=:id AND org_id=:org_id AND status<>'hidden'",
        data["posts_hidden"])
    run("photo_scopes", "UPDATE children SET photo_scope=:photo_scope WHERE id=:child_id AND org_id=:org_id "
                        "AND photo_scope<>:photo_scope", data["photo_scopes"])
    # 퇴소는 같은 작업을 이력 없이 다시 돌린다. 이력은 아래에서 원래 행을 그대로 넣는다.
    count["withdrawn_children"] = 0
    for item in data["withdrawn_children"]:
        todo, _ = withdraw_child.run(connection, item["child_id"], record=False)
        count["withdrawn_children"] += todo is not None and withdraw_child.pending(todo)
    run("memories_deleted", "UPDATE memories SET deleted_at=:deleted_at,content='',structured='{}'::jsonb "
                            "WHERE id=:id AND org_id=:org_id AND deleted_at IS NULL", data["memories_deleted"])
    # 같은 시각·내용의 이력이 있으면 넣지 않는다. 복원한 DB에 없는 사용자의 이력은 FK 때문에 건너뛴다.
    run("events", """
        INSERT INTO events(org_id,actor_type,actor_id,agent_name,action,detail,created_at)
        SELECT :org_id,:actor_type,:actor_id,:agent_name,:action,CAST(:detail AS jsonb),:created_at
        WHERE NOT EXISTS (SELECT 1 FROM events WHERE org_id=:org_id AND action=:action
                          AND created_at=:created_at AND detail=CAST(:detail AS jsonb))
          AND (CAST(:actor_id AS uuid) IS NULL OR EXISTS (SELECT 1 FROM users WHERE id=:actor_id AND org_id=:org_id))
    """, [{**e, "detail": json.dumps(e["detail"])} for e in data["events"]])
    return count


def parse_since(value):
    since = datetime.fromisoformat(value)
    if since.tzinfo is None:
        raise argparse.ArgumentTypeError("시간대가 있는 시각을 넣어 주세요. 예: 2026-11-23T05:00:00Z")
    return since


def main(argv=None):
    parser = argparse.ArgumentParser(description="복원 뒤 다시 적용")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("export", help="지금 DB에서 백업 뒤 변경을 JSON으로 뽑아요").add_argument(
        "--since", type=parse_since, required=True, help="백업 meta.json의 created_at")
    commands.add_parser("apply", help="복원한 DB에 JSON을 적용해요").add_argument("file", help="JSON 파일, -는 표준 입력")
    args = parser.parse_args(argv)
    if args.command == "export":
        with transaction() as connection:
            json.dump(export(connection, args.since), sys.stdout, ensure_ascii=False, indent=1, default=str)
        print()
        return
    source = sys.stdin if args.file == "-" else open(args.file, encoding="utf-8")
    with source, transaction() as connection:
        print(json.dumps(apply(connection, json.load(source)), ensure_ascii=False))


if __name__ == "__main__":
    main()
