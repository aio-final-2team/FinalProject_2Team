"""가상 음성의 메타데이터와 결과만 PostgreSQL에 저장해요."""

import json
from uuid import uuid4

from sqlalchemy import text

from app.core import media, voice_analysis as rules
from app.core.db import transaction
from app.core.errors import ApiError
from app.modules.consultations.video import record
from app.modules.requests.events import record as event


def access(user, booking_id, *, write=False):
    with transaction() as c:
        row = c.execute(text("SELECT * FROM consultation_bookings WHERE id=:id AND org_id=:org"),
                        {"id": booking_id, "org": user.org_id}).mappings().one_or_none()
    return rules.authorize(user, row, lambda: record(user, booking_id, "permission_denied"), write=write)


def _event(c, row, action, **detail):
    req = c.execute(text("SELECT * FROM requests WHERE id=:id"), {"id": row["request_id"]}).mappings().one()
    event(c, req, action, analysis_id=str(row["id"]), **detail)


def create(user, booking_id, data, metadata):
    booking = access(user, booking_id, write=True)
    name = media.save(data, metadata)
    try:
        with transaction() as c:
            row = c.execute(text("""
                INSERT INTO consultation_voice_analyses
                    (id,org_id,booking_id,request_id,storage_path,sha256,duration_seconds)
                VALUES (:id,:org,:booking,:request,:path,:sha256,:duration) RETURNING *
            """), {"id": uuid4(), "org": user.org_id, "booking": booking_id, "request": booking["request_id"],
                   "path": name, "sha256": metadata["sha256"], "duration": metadata["duration_seconds"]}).mappings().one()
            _event(c, row, "voice_analysis_requested", actor_type="user", actor_id=user.id)
        return rules.view(row)
    except Exception:
        rules.remove(name)
        raise


def get(user, analysis_id):
    with transaction() as c:
        row = c.execute(text("SELECT * FROM consultation_voice_analyses WHERE id=:id AND org_id=:org"),
                        {"id": analysis_id, "org": user.org_id}).mappings().one_or_none()
    if row is None:
        raise ApiError(404, "NOT_FOUND")
    access(user, row["booking_id"])
    return rules.view(row)


def listing(user, booking_id):
    access(user, booking_id)
    with transaction() as c:
        rows = c.execute(text("SELECT * FROM consultation_voice_analyses WHERE booking_id=:id AND org_id=:org "
                              "ORDER BY created_at DESC, id DESC"), {"id": booking_id, "org": user.org_id}).mappings()
        return {"items": [rules.view(r) for r in rows]}


def claim(analysis_id):
    with transaction() as c:
        return c.execute(text("UPDATE consultation_voice_analyses SET status='running',started_at=now() "
                              "WHERE id=:id AND status='queued' RETURNING *"), {"id": analysis_id}).mappings().one_or_none()


def finish(analysis_id, result):
    with transaction() as c:
        row = c.execute(text("""
            UPDATE consultation_voice_analyses SET status=:status,transcript=:transcript,result=CAST(:result AS jsonb),
                duration_seconds=coalesce(:duration,duration_seconds),storage_path=NULL,completed_at=now()
            WHERE id=:id AND status='running' RETURNING *
        """), {"id": analysis_id, "status": "succeeded" if result else "failed",
               "transcript": result["transcript"] if result else "", "result": json.dumps(result["result"] if result else
               {"summary": "", "parent_requests": [], "follow_ups": []}),
               "duration": result["duration_seconds"] if result else None}).mappings().one_or_none()
        if row:
            _event(c, row, "voice_analysis_completed", status=row["status"])


def sweep(*, all_pending=False):
    with transaction() as c:
        rows = c.execute(text("SELECT * FROM consultation_voice_analyses WHERE status IN ('queued','running') "
                              "AND (:all_pending OR CASE WHEN status='running' THEN started_at ELSE created_at END "
                              "< now()-make_interval(secs=>:timeout)) FOR UPDATE"),
                         {"timeout": rules.VOICE_TIMEOUT, "all_pending": all_pending}).mappings().all()
        for row in rows:
            c.execute(text("UPDATE consultation_voice_analyses SET status='failed',completed_at=now(),storage_path=NULL "
                           "WHERE id=:id"), {"id": row["id"]})
            _event(c, row, "voice_analysis_completed", status="failed")
    for row in rows:
        rules.remove(row["storage_path"])
    return len(rows)
