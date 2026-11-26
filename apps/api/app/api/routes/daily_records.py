"""56~58번 API: 담임의 하루 중 기록과 원장 읽기예요."""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

from app import backend
from app.api.schemas.common import errors
from app.api.schemas.daily_records import DailyRecordIn, DailyRecordOut, DailyRecordsOut
from app.core.auth import CurrentUser, require_roles

router = APIRouter(tags=["[제안] 하루 중 기록"])


@router.get("/classrooms/{classroom_id}/records", response_model=DailyRecordsOut,
            responses=errors(401, 403, 404, 422))
def list_records(classroom_id: UUID, note_date: date = Query(alias="date"),
                 user: CurrentUser = Depends(require_roles("teacher", "director"))):
    return backend.daily_records.list_records(user, classroom_id, note_date)


@router.post("/classrooms/{classroom_id}/records", response_model=DailyRecordOut, status_code=201,
             responses=errors(401, 403, 404, 422))
def create_record(classroom_id: UUID, body: DailyRecordIn,
                  user: CurrentUser = Depends(require_roles("teacher"))):
    return backend.daily_records.create(user, classroom_id, body)


@router.delete("/records/{record_id}", status_code=204, responses=errors(401, 403, 404, 422))
def delete_record(record_id: UUID, user: CurrentUser = Depends(require_roles("teacher"))):
    backend.daily_records.delete(user, record_id)
    return Response(status_code=204)
