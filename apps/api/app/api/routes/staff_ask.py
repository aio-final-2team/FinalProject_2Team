"""66번 API: [제안] 교직원이 원 자료에 관해 물어요."""

from fastapi import APIRouter, Depends

from app import backend
from app.api.schemas.common import errors
from app.api.schemas.staff_ask import StaffAskIn, StaffAskOut
from app.core.auth import CurrentUser, require_roles
from app.core.consents import require_complete

router = APIRouter(tags=["[제안] 교직원 질문"])


@router.post("/staff/ask", response_model=StaffAskOut, responses=errors(401, 403, 422, 503))
def staff_ask(body: StaffAskIn, user: CurrentUser = Depends(require_roles("teacher", "director"))):
    require_complete(user)  # 질문을 국외 AI 사업자에게 보내므로 'AI 처리' 동의가 있어야 한다
    return backend.staff_ask.ask(user, body.question)
