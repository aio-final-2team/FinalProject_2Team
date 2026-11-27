"""62·68번 API: 알림장 답장과 준비물 '챙겼어요'."""

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Request

from app import backend
from app.api.schemas.actions import MessageIn
from app.api.schemas.common import errors
from app.api.schemas.views import NoteReplyAccepted, SuppliesCheckOut
from app.core.auth import CurrentUser, require_roles
from app.core.errors import trace_id_of

router = APIRouter(tags=["[제안] 알림장 답장·준비물 확인"])


@router.post("/daily-notes/{note_id}/replies", status_code=202, response_model=NoteReplyAccepted,
             responses=errors(401, 403, 404, 409, 422))
def reply(note_id: UUID, body: MessageIn, request: Request, background_tasks: BackgroundTasks,
          user: CurrentUser = Depends(require_roles("parent"))):
    return backend.notes.reply(user, note_id, body.body, background_tasks, trace_id_of(request))


@router.post("/daily-notes/{note_id}/supplies-check", response_model=SuppliesCheckOut,
             responses=errors(401, 403, 404, 409, 422))
def supplies_check(note_id: UUID, user: CurrentUser = Depends(require_roles("parent"))):
    return backend.notes.supplies_check(user, note_id)
