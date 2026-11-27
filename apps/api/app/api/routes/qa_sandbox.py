"""QA 서버의 사람별 원 초기화·요청 이력·배포 정보."""

import json
import os
from pathlib import Path as FilePath
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text

from app.api.routes.qa_reset import QAOnlyRoute
from app.api.schemas.common import errors
from app.api.schemas.qa_sandbox import SandboxResetOut, TraceOut, QAInfo
from app.core.auth import CurrentUser, current_user
from app.core.config import settings
from app.core.db import transaction
from app.core.errors import ApiError
from app.core.qa_orgs import QA_ORGS, find_org
from app.core.request_id import qa_errors, active_trace_id
from app.modules.documents import embedding

router = APIRouter(tags=["[QA 전용] 사람별 QA 원"], route_class=QAOnlyRoute)
_optional_bearer = HTTPBearer(auto_error=False)
CONSOLE = FilePath(__file__).resolve().parents[1] / "qa_console.html"


def _me(request, cred):
    """토큰이 있으면 QA 도구 화면이 반 이름을 고를 수 있게 내 원·반을 돌려줘요. 토큰이 틀리면 None."""
    if cred is None:
        return None
    try:
        user = current_user(request, cred)
    except ApiError:
        return None
    if settings.data_backend == "db":
        with transaction() as connection:
            org_name = connection.scalar(text("SELECT name FROM organizations WHERE id=:org"), {"org": user.org_id})
            classrooms = [dict(row) for row in connection.execute(text(
                "SELECT id, name FROM classrooms WHERE org_id=:org ORDER BY name COLLATE \"C\", id"),
                {"org": user.org_id}).mappings()]
    else:
        from app.mock import store
        state = store.state()
        org_name = None
        classrooms = sorted(({"id": c.id, "name": c.name} for c in state.classrooms.values()
                             if c.org_id == user.org_id), key=lambda c: (c["name"], str(c["id"])))
    return {"role": user.role, "org_name": org_name, "classrooms": classrooms}


@router.post("/qa/sandbox/reset", response_model=SandboxResetOut, responses=errors(401, 404))
def reset(user: CurrentUser = Depends(current_user)):
    org = find_org(user.org_id)
    if settings.data_backend != "db" or org is None or not settings.qa_password:
        raise ApiError(404, "NOT_FOUND")
    from db.seeds.qa_orgs import DELETE_ORDER, lock, populate, template

    with transaction() as connection:
        lock(connection, org)
        source = template(connection)
        deleted = {table: connection.execute(text(f"DELETE FROM {table} WHERE org_id=:org"),
                   {"org": user.org_id}).rowcount for table in DELETE_ORDER}
        # shortcut: 사진·문서 파일은 남겨요. 디스크 정리가 필요해지면 별도 보존 정책으로 처리해요.
        seeded = populate(connection, org, source)
        connection.execute(text("""INSERT INTO events(org_id,actor_type,actor_id,action,detail)
            VALUES (:org,'user',:actor,'tool_called',CAST(:detail AS jsonb))"""),
            {"org": user.org_id, "actor": user.id, "detail": json.dumps({"tool": "qa_sandbox_reset",
             "deleted": deleted, "trace_id": active_trace_id.get()})})
    return {"org_name": org["name"], "deleted": deleted, "seeded": seeded}


@router.get("/qa/traces/{trace_id}", response_model=TraceOut, responses=errors(401, 404, 422))
def traces(trace_id: Annotated[str, Path(min_length=1, max_length=128)], user: CurrentUser = Depends(current_user)):
    if settings.data_backend == "db":
        with transaction() as connection:
            events = list(connection.execute(text("""SELECT created_at,action,actor_type,agent_name,
                request_id,card_id,daily_note_id,detail FROM events
                WHERE org_id=:org AND detail->>'trace_id'=:trace ORDER BY created_at,id"""),
                {"org": user.org_id, "trace": trace_id}).mappings())
    else:
        from app.mock import store
        events = sorted((vars(event) for event in store.state().events if event.org_id == user.org_id
                         and event.detail.get("trace_id") == trace_id), key=lambda event: event["created_at"])
    return {"trace_id": trace_id, "events": events,
            "errors": [row for row in list(qa_errors) if row["trace_id"] == trace_id
                       and row["org_id"] == user.org_id]}


@router.get("/qa/console", response_class=HTMLResponse, include_in_schema=False)
def console():
    """화면으로 쓰는 QA 도구(로그인·원 되돌리기·알림장 지우기·요청 ID로 찾기). API 목록에는 넣지 않아요."""
    return HTMLResponse(CONSOLE.read_text(encoding="utf-8"))


@router.get("/qa/info", response_model=QAInfo, responses=errors(404))
def info(request: Request, cred: HTTPAuthorizationCredentials | None = Depends(_optional_bearer)):
    migration = None
    if settings.data_backend == "db":
        with transaction() as connection:
            migration = connection.scalar(text("SELECT version_num FROM alembic_version"))
    return {"commit": os.getenv("GIT_SHA") or None, "deployed_at": os.getenv("DEPLOYED_AT") or None,
            "migration": migration, "data_backend": settings.data_backend, "qa_orgs": QA_ORGS,
            "me": _me(request, cred),
            "switches": {"daily_note_writer": settings.daily_note_writer,
                         "answer_writer": os.getenv("ANSWER_WRITER", "stub"), "request_agent": settings.request_agent,
                         "embedding": embedding.enabled(),
                         "llm_models": {role.lower(): os.getenv(f"LLM_MODEL_{role}", "gpt-6-luna" if role == "DEFAULT" else "")
                                        for role in ("DEFAULT", "SUPERVISOR", "DOCUMENT", "MEMORY", "CHECKER", "CODE")}}}
