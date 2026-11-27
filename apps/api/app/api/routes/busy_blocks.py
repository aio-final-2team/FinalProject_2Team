"""59~61번 API: 교직원 본인의 바쁜 시간을 관리해요."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from pydantic import AwareDatetime

from app import backend
from app.api.schemas.busy_blocks import BusyBlockIn, BusyBlockOut, BusyBlocksOut
from app.api.schemas.common import errors
from app.core.auth import CurrentUser, require_roles
from app.core.errors import ApiError

router = APIRouter(tags=["바쁜 시간"])
staff = require_roles("teacher", "director")


@router.get("/staff/busy-blocks", response_model=BusyBlocksOut, responses=errors(401, 403, 404, 422))
def list_busy_blocks(from_: AwareDatetime = Query(alias="from"), to: AwareDatetime = Query(),
                     user_id: UUID | None = None, user: CurrentUser = Depends(staff)):
    if from_ >= to:
        raise ApiError(422, "VALIDATION_FAILED")
    return backend.busy_blocks.list_blocks(user, from_, to, user_id or user.id)


@router.post("/staff/busy-blocks", response_model=BusyBlockOut, status_code=201,
             responses=errors(401, 403, 409, 422))
def create_busy_block(body: BusyBlockIn, user: CurrentUser = Depends(staff)):
    return backend.busy_blocks.create(user, body)


@router.delete("/staff/busy-blocks/{id}", status_code=204, responses=errors(401, 403, 404, 422))
def delete_busy_block(id: int, user: CurrentUser = Depends(staff)):
    backend.busy_blocks.delete(user, id)
    return Response(status_code=204)
