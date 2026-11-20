"""투약·귀가 요청의 사람이 확인하는 경로(T46 팀 확인 전 초안)."""

from app.core.care import care_view, check_decision
from app.core.constants import CARE_REQUEST_TYPES
from app.core.errors import ApiError
from app.mock import store


def view(req):
    return care_view([e.__dict__ for e in store.events_of(req.id)])


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


def decision(user, request_id, body):
    with store._lock:
        req = store.request_in_scope(user, request_id)
        target = check_decision(req.type, req.status, view(req), body)
        if req.type == "pickup":
            validate_guardian(user, req.child_id, body.pickup_guardian_id)
        if target:
            req.assignee_id = user.id
            store.set_request_status(req, target, action="checked" if body.decision == "confirm" else "completed",
                                     actor_type="user", actor_id=user.id, care_decision=body.decision)
        return {"request": {"id": req.id, "status": req.status}, "care": view(req)}


def listing(user, classroom_id, status, page, size):
    with store._lock:
        if classroom_id:
            store.classroom_in_scope(user, classroom_id)
        classes = store.classroom_ids_of(user.id) if user.role == "teacher" else list(store.state().classrooms)
        rows = [r for r in store.state().requests.values() if r.org_id == user.org_id
                and r.classroom_id in classes and r.type in CARE_REQUEST_TYPES
                and (classroom_id is None or r.classroom_id == classroom_id)
                and (status is None or r.status == status)]
        from app.api.labels import staff_label
        rows.sort(key=lambda r: (r.created_at, str(r.id)), reverse=True)
        return {"items": [{"id": r.id, "type": r.type, "title": r.title, "status": r.status,
                           "status_label": staff_label(r.status, r.type), "updated_at": r.updated_at,
                           "next_action": "confirm" if r.status == "received" else "complete" if r.status == "assigned" else None}
                          for r in rows[(page-1)*size:page*size]], "total": len(rows), "page": page, "size": size}
