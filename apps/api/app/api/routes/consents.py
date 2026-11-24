"""53~55번 API: [제안] 내 필수 동의와 반 아이별 동의 현황이에요."""

from uuid import UUID

from fastapi import APIRouter, Depends

from app import backend
from app.api.schemas.common import errors
from app.api.schemas.consents import ConsentIn, ConsentOut, ClassroomConsents
from app.core.auth import CurrentUser, current_user, require_roles

router = APIRouter(tags=["[제안] 필수 동의"])


@router.get("/consents", response_model=ConsentOut, responses=errors(401))
def get_consents(user: CurrentUser = Depends(current_user)):
    return backend.consents.get(user)


@router.post("/consents", response_model=ConsentOut, responses=errors(401, 409, 422))
def agree_consents(body: ConsentIn, user: CurrentUser = Depends(current_user)):
    return backend.consents.agree(user, body.items, body.terms_version)


@router.get("/classrooms/{classroom_id}/consents", response_model=ClassroomConsents,
            responses=errors(401, 403, 404, 422))
def classroom_consents(classroom_id: UUID, user: CurrentUser = Depends(require_roles("teacher", "director"))):
    return backend.consents.classroom(user, classroom_id)
