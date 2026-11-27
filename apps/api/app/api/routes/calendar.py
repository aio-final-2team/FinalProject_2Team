"""63번 API: [제안] 자료에서 원 일정을 읽어요."""

from datetime import date

from fastapi import APIRouter, Depends, Query

from app import backend
from app.api.schemas.calendar import CalendarOut
from app.api.schemas.common import errors
from app.core.auth import CurrentUser, current_user
from app.core.errors import ApiError

router = APIRouter(tags=["[제안] 원 일정"])


@router.get("/calendar", response_model=CalendarOut, responses=errors(401, 422))
def calendar(from_: date = Query(..., alias="from"), to: date = Query(...),
             user: CurrentUser = Depends(current_user)):
    if from_ > to:
        raise ApiError(422, "VALIDATION_FAILED")
    return backend.calendar.listing(user, from_, to)
