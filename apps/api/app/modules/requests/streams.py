"""저장된 요청 이력의 단계만 SSE로 보내요. 초안·카드·내부 실패 이유는 보내지 않아요."""

import json
import time

import anyio
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from sqlalchemy import text

from app.core import scope
from app.core.constants import CARE_REQUEST_TYPES
from app.core.db import transaction
from app.core.errors import ApiError, DEFAULT_MESSAGES
from app.core.request_id import active_trace_id

POLL_SECONDS = 0.25
MAX_SECONDS = 300


def _encode(event, data):
    return f"event: {event}\ndata: {json.dumps(jsonable_encoder(data), ensure_ascii=False)}\n\n"


def stream_request(user, request_id):
    scope.request_in_scope(user, request_id)
    trace_id = active_trace_id.get()

    def read(cursor):
        with transaction() as connection:
            req = scope.request_in_scope(user, request_id, connection=connection)
            rows = connection.execute(text("""
                SELECT id,action,card_id,agent_name,to_status,created_at FROM events
                WHERE request_id=:id AND org_id=:org AND id>:cursor ORDER BY id
            """), {"id": request_id, "org": user.org_id, "cursor": cursor}).mappings().all()
            return req, rows

    async def events():
        cursor, deadline = 0, time.monotonic() + MAX_SECONDS
        while True:
            try:
                req, rows = await anyio.to_thread.run_sync(read, cursor)
            except Exception as error:
                code = error.code if isinstance(error, ApiError) else "INTERNAL_ERROR"
                yield _encode("error", {"error": {"code": code, "message": DEFAULT_MESSAGES[code],
                                                 "trace_id": trace_id, "details": {}}})
                return
            if req["type"] in CARE_REQUEST_TYPES:
                yield _encode("done", {"request_status": req["status"]})
                return
            for row in rows:
                cursor = row["id"]
                stage = None
                if row["action"] == "created" and row["card_id"] is None and row["to_status"] == "received":
                    stage = "classifying"
                elif row["action"] == "classified":
                    stage = "searching"
                elif row["action"] == "drafted":
                    stage = "drafting"
                elif row["action"] == "checked" and row["agent_name"] == "checker":
                    stage = "checking"
                if stage:
                    yield _encode("stage", {"stage": stage, "at": row["created_at"]})
            if req["status"] not in ("received", "classified", "assigned"):
                yield _encode("done", {"request_status": req["status"]})
                return
            if time.monotonic() >= deadline:
                yield _encode("error", {"error": {"code": "UPSTREAM_UNAVAILABLE",
                    "message": DEFAULT_MESSAGES["UPSTREAM_UNAVAILABLE"], "trace_id": trace_id, "details": {}}})
                return
            await anyio.sleep(POLL_SECONDS)

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
