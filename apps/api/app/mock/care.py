"""투약·귀가 요청의 사람이 확인하는 경로(T46 팀 확인 전 초안)."""

from app.core.care import care_view, check_decision
from app.core.constants import CARE_REQUEST_TYPES, UNREGISTERED_PICKUP_CHECK
from app.core.errors import ApiError
from app.mock import seed, store


def view(req):
    return care_view([e.__dict__ for e in store.events_of(req.id)], req.type, req.care_detail)


def guardians(user, child_id):
    child = store.state().children.get(child_id)
    if child is None or child.org_id != user.org_id:
        store.deny(user)
    if user.role == "parent":
        if user.id not in child.guardian_ids:
            store.deny(user)
    else:
        store.classroom_in_scope(user, child.classroom_id)
    return {"items": sorted([{"id": u.id, "display_name": u.display_name}
                             for u in store.state().users.values() if u.id in child.guardian_ids
                             and u.org_id == child.org_id and u.is_active and u.role == "parent"],
                            key=lambda u: (u["display_name"], str(u["id"])))}


def validate_guardian(user, child_id, guardian_id):
    if str(guardian_id) not in {str(g["id"]) for g in guardians(user, child_id)["items"]}:
        raise ApiError(422, "VALIDATION_FAILED", field="pickup_guardian_id")
    guardian = store.state().users[guardian_id]
    return {"pickup_guardian_id": str(guardian_id), "pickup_name": guardian.display_name,
            "pickup_relation": seed.GUARDIAN_RELATIONS.get((child_id, guardian_id), "other")}


def decision(user, request_id, body):
    with store._lock:
        req = store.request_in_scope(user, request_id)
        current = view(req)
        target = check_decision(req.type, req.status, current, body)
        snapshot = {}
        if target and req.type == "pickup" and body.decision == "confirm":
            snapshot = {k: current.get(k) for k in ("pickup_guardian_id", "pickup_name", "pickup_relation")}
            if body.pickup_guardian_id is not None:
                snapshot = validate_guardian(user, req.child_id, body.pickup_guardian_id)
        if target:
            req.assignee_id = user.id
            store.set_request_status(req, target, action="checked" if body.decision == "confirm" else "completed",
                                     actor_type="user", actor_id=user.id, care_decision=body.decision,
                                     version=current["version"], pickup_snapshot=snapshot)
            if body.decision == "confirm" and current["unregistered_pickup"]:
                store.add_event(req, "checked", actor_type="user", actor_id=user.id,
                                unregistered_pickup=True, label=UNREGISTERED_PICKUP_CHECK, version=current["version"],
                                pickup_snapshot=snapshot)
        return {"request": {"id": req.id, "status": req.status}, "care": view(req)}


def listing(user, classroom_id, status, page, size, sort):
    with store._lock:
        if classroom_id:
            store.classroom_in_scope(user, classroom_id)
        classes = store.classroom_ids_of(user.id) if user.role == "teacher" else list(store.state().classrooms)
        rows = [r for r in store.state().requests.values() if r.org_id == user.org_id
                and r.classroom_id in classes and r.type in CARE_REQUEST_TYPES
                and (classroom_id is None or r.classroom_id == classroom_id)
                and (status is None or r.status == status)]
        from app.api.labels import staff_label
        rows.sort(key=lambda r: (getattr(r, sort.lstrip("-")), str(r.id)), reverse=sort.startswith("-"))
        return {"items": [{"id": r.id, "type": r.type, "title": r.title, "status": r.status,
                           "child_id": r.child_id, "child_name": store.state().children[r.child_id].display_name,
                           "status_label": staff_label(r.status, r.type), "updated_at": r.updated_at,
                           **{k: v for k, v in view(r).items() if k in ("version", "unregistered_pickup", "missing_fields")},
                           "next_action": "confirm" if r.status == "received" else "complete" if r.status == "assigned" else None}
                          for r in rows[(page-1)*size:page*size]], "total": len(rows), "page": page, "size": size}
