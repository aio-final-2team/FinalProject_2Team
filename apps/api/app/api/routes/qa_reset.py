"""71번 API: QA_TOOLS가 꺼져 있으면 인증·본문 해석 전에 숨겨요."""

from fastapi import APIRouter, Depends, Request
from fastapi.routing import APIRoute

from app import backend
from app.api.schemas.common import errors
from app.api.schemas.qa_reset import NoteResetIn, NoteResetOut
from app.core.auth import CurrentUser, require_roles
from app.core.config import settings
from app.core.errors import ApiError


class QAOnlyRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def enabled(request: Request):
            if not settings.qa_tools:
                raise ApiError(404, "NOT_FOUND")
            return await handler(request)

        return enabled


router = APIRouter(tags=["[QA 전용] 알림장 다시 시험하기"], route_class=QAOnlyRoute)


@router.post("/qa/daily-notes/reset", response_model=NoteResetOut, responses=errors(401, 403, 404, 422))
def reset(body: NoteResetIn, user: CurrentUser = Depends(require_roles("teacher", "director"))):
    return backend.qa_reset.reset(user, body.classroom_id, body.note_date)
