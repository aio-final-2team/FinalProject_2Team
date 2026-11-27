"""아이 퇴소 관리 작업. DB 설계서 '아이가 퇴소할 때' 네 단계를 그대로 한다. 기본은 할 일만 출력한다.

1. 보호자 연결을 끝낸다. 2. 공개 범위를 family로 되돌린다.
3. 그 아이만 태그된 사진은 태그·사진 행·파일 순서로 지우고, 함께 찍힌 사진은 태그를 남긴다.
   프로필 사진(0021)도 경로를 비우고 파일을 지운다.
4. 그 아이 요청에서 나온 기억의 내용을 비우고 지운 시각을 남긴다.
기록은 photo_scope_changed 이력 하나로 남긴다. detail.withdrawn과 지운 사진 ID가 들어가고, 복원 뒤 다시 적용이 이걸 찾는다.
"""

import argparse
import json
import logging
from uuid import UUID

from sqlalchemy import text

from app.core.db import transaction
from app.maintenance.media_sweep import safe_path

log = logging.getLogger(__name__)


def plan(connection, child_id, lock=False):
    child = connection.execute(text("SELECT id,org_id,photo_scope,profile_photo_path FROM children WHERE id=:id" +
                                    (" FOR UPDATE" if lock else "")), {"id": child_id}).mappings().one_or_none()
    if child is None:
        return None
    key = {"child": child_id, "org": child["org_id"]}
    photos = connection.execute(text("""
        SELECT p.id, p.storage_path,
               (SELECT count(*) FROM feed_photo_children o WHERE o.photo_id=p.id AND o.org_id=p.org_id) AS tags
        FROM feed_photos p JOIN feed_photo_children t ON (t.photo_id,t.org_id)=(p.id,p.org_id)
        WHERE t.child_id=:child AND t.org_id=:org ORDER BY p.id
    """), key).mappings().all()
    return {
        "child_id": child_id, "org_id": child["org_id"], "photo_scope": child["photo_scope"],
        "profile_photo": child["profile_photo_path"],
        "guardian_ids": list(connection.scalars(text(
            "SELECT user_id FROM child_guardians WHERE child_id=:child AND org_id=:org ORDER BY user_id"), key)),
        "solo_photos": [{"id": p["id"], "storage_path": p["storage_path"]} for p in photos if p["tags"] == 1],
        "shared_photo_ids": [p["id"] for p in photos if p["tags"] > 1],
        # 돌봄 메모는 아이에 직접, 담임 기억은 카드 → 요청 → 아이로 이어져요.
        "memory_ids": list(connection.scalars(text("""
            SELECT m.id FROM memories m
            LEFT JOIN cards c ON (c.id,c.org_id)=(m.source_card_id,m.org_id)
            LEFT JOIN requests r ON (r.id,r.org_id)=(c.request_id,c.org_id)
            WHERE (r.child_id=:child OR m.child_id=:child) AND m.org_id=:org AND m.deleted_at IS NULL ORDER BY m.id
        """), key)),
    }


def pending(todo):
    return bool(todo["guardian_ids"] or todo["solo_photos"] or todo["memory_ids"] or todo["profile_photo"]
                or todo["photo_scope"] != "family")


def run(connection, child_id, record=True):
    """DB만 바꾸고 지울 파일 이름을 돌려준다. 파일은 커밋 뒤에 지운다."""
    todo = plan(connection, child_id, lock=True)
    if todo is None or not pending(todo):
        return todo, []
    key = {"child": child_id, "org": todo["org_id"]}
    connection.execute(text("DELETE FROM child_guardians WHERE child_id=:child AND org_id=:org"), key)
    connection.execute(text("UPDATE children SET photo_scope='family', profile_photo_path=NULL "
                            "WHERE id=:child AND org_id=:org"), key)
    solo = [p["id"] for p in todo["solo_photos"]]
    connection.execute(text("DELETE FROM feed_photo_children WHERE photo_id = ANY(:ids) AND org_id=:org"),
                       {**key, "ids": solo})
    connection.execute(text("DELETE FROM feed_photos WHERE id = ANY(:ids) AND org_id=:org"), {**key, "ids": solo})
    connection.execute(text("""
        UPDATE memories SET deleted_at=now(),content='',structured='{}'::jsonb
        WHERE id = ANY(:ids) AND org_id=:org AND deleted_at IS NULL
    """), {**key, "ids": todo["memory_ids"]})
    if record:
        detail = {"child_id": str(child_id), "before": todo["photo_scope"], "after": "family",
                  "withdrawn": True, "photo_ids": [str(i) for i in solo],
                  "profile_photo_removed": bool(todo["profile_photo"])}
        connection.execute(text("""
            INSERT INTO events(org_id,actor_type,action,detail)
            VALUES (:org,'system','photo_scope_changed',CAST(:detail AS jsonb))
        """), {**key, "detail": json.dumps(detail)})
    return todo, [p["storage_path"] for p in todo["solo_photos"]] + ([todo["profile_photo"]] if todo["profile_photo"] else [])


def remove_files(names):
    for name in names:
        try:
            safe_path(name).unlink(missing_ok=True)
        except (OSError, ValueError):
            # 남은 파일은 media_sweep이 고아로 정리한다.
            log.warning("withdraw_photo_delete_failed path=%s", name)


def withdraw(child_id, apply=False):
    with transaction() as connection:
        if not apply:
            return plan(connection, child_id)
        todo, names = run(connection, child_id)
    remove_files(names)
    return todo


def main(argv=None):
    parser = argparse.ArgumentParser(description="아이 퇴소 관리 작업. 기본은 할 일만 출력해요.")
    parser.add_argument("child_id", type=UUID)
    parser.add_argument("--apply", action="store_true", help="출력한 일을 실제로 해요")
    args = parser.parse_args(argv)
    todo = withdraw(args.child_id, args.apply)
    if todo is None:
        parser.exit(1, "그 아이가 없어요.\n")
    print(json.dumps(todo, ensure_ascii=False, indent=2, default=str))
    if not pending(todo):
        print("할 일이 없어요. 이미 퇴소 처리가 끝나 있어요.")
    else:
        print("실행했어요." if args.apply else "할 일만 보였어요. 실행하려면 --apply를 붙여요.")


if __name__ == "__main__":
    main()
