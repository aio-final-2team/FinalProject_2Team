"""T46 등록 인계자 조회·재검사와 교직원 실제 확인. 요청 행 잠금으로 직렬화해요."""

from sqlalchemy import text

from app.core import scope
from app.core.care import care_view, check_decision
from app.core.constants import UNREGISTERED_PICKUP_CHECK
from app.core.db import transaction
from app.core.errors import ApiError
from app.modules.requests.events import record, set_status


def view(connection, req):
    rows = connection.execute(text("""
        SELECT action,to_status,detail,created_at FROM events
        WHERE request_id=:id AND org_id=:org AND card_id IS NULL ORDER BY id
    """), {"id": req["id"], "org": req["org_id"]}).mappings().all()
    return care_view(rows, req["type"])


def _guardians(connection, org_id, child_id):
    return [dict(row) for row in connection.execute(text("""
        SELECT u.id,u.display_name,g.relation FROM child_guardians g JOIN users u ON (u.id,u.org_id)=(g.user_id,g.org_id)
        WHERE g.org_id=:org AND g.child_id=:child AND u.role='parent' AND u.is_active
        ORDER BY u.display_name,u.id
    """), {"org": org_id, "child": child_id}).mappings()]


def guardians(user, child_id):
    with transaction() as connection:
        scope.child_in_scope(user, child_id, connection=connection)
        return {"items": _guardians(connection, user.org_id, child_id)}


def validate_guardian(connection, user, child_id, guardian_id):
    guardian = next((g for g in _guardians(connection, user.org_id, child_id) if str(g["id"]) == str(guardian_id)), None)
    if guardian is None:
        raise ApiError(422, "VALIDATION_FAILED", field="pickup_guardian_id")
    return {"pickup_guardian_id": str(guardian["id"]), "pickup_name": guardian["display_name"],
            "pickup_relation": guardian["relation"]}


def decision(user, request_id, body):
    with transaction() as connection:
        scope.request_in_scope(user, request_id, connection=connection)
        req = dict(connection.execute(text("SELECT * FROM requests WHERE id=:id FOR NO KEY UPDATE"),
                                      {"id": request_id}).mappings().one())
        current = view(connection, req)
        target = check_decision(req["type"], req["status"], current, body)
        snapshot = {}
        if target and req["type"] == "pickup" and body.decision == "confirm":
            snapshot = {k: current.get(k) for k in ("pickup_guardian_id", "pickup_name", "pickup_relation")}
            if body.pickup_guardian_id is not None:
                snapshot = validate_guardian(connection, user, req["child_id"], body.pickup_guardian_id)
        if target:
            connection.execute(text("UPDATE requests SET assignee_id=:user WHERE id=:id"),
                               {"id": request_id, "user": user.id})
            req["assignee_id"] = user.id
            set_status(connection, req, target, action="checked" if body.decision == "confirm" else "completed",
                       actor_type="user", actor_id=user.id, care_decision=body.decision,
                       version=current["version"], pickup_snapshot=snapshot)
            if body.decision == "confirm" and current["unregistered_pickup"]:
                record(connection, req, "checked", actor_type="user", actor_id=user.id,
                       unregistered_pickup=True, label=UNREGISTERED_PICKUP_CHECK, version=current["version"])
        return {"request": {"id": req["id"], "status": req["status"]}, "care": view(connection, req)}


def listing(user, classroom_id, status, page, size, sort):
    from app.api.labels import staff_label

    with transaction() as connection:
        if classroom_id:
            scope.classroom_in_scope(user, classroom_id, connection=connection)
        rows = connection.execute(text("""
            SELECT * FROM requests r WHERE r.org_id=:org AND r.type IN ('medication','pickup')
              AND (CAST(:class AS uuid) IS NULL OR r.classroom_id=CAST(:class AS uuid))
              AND (CAST(:status AS text) IS NULL OR r.status=:status)
              AND (:director OR EXISTS (SELECT 1 FROM classroom_staff s
                WHERE s.org_id=r.org_id AND s.classroom_id=r.classroom_id AND s.user_id=:user
                  AND (s.valid_from IS NULL OR s.valid_from<=CURRENT_DATE)
                  AND (s.valid_to IS NULL OR s.valid_to>=CURRENT_DATE)))
            ORDER BY r.created_at DESC,r.id DESC
        """), {"org": user.org_id, "class": classroom_id, "status": status,
               "user": user.id, "director": user.role == "director"}).mappings().all()
        rows = sorted(rows, key=lambda r: (r[sort.lstrip("-")], str(r["id"])), reverse=sort.startswith("-"))
        return {"items": [{**{k: r[k] for k in ("id", "type", "title", "status", "updated_at")},
                           "status_label": staff_label(r["status"], r["type"]),
                           **{k: v for k, v in view(connection, r).items()
                              if k in ("version", "unregistered_pickup", "missing_fields")},
                           "next_action": "confirm" if r["status"] == "received" else "complete" if r["status"] == "assigned" else None}
                          for r in rows[(page-1)*size:page*size]], "total": len(rows), "page": page, "size": size}
