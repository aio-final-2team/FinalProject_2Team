"""3·5번 API: 요청 만들기, 요청 상세(API 설계 문서 3.1·3.2)."""

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response, status

from app.api.schemas.common import errors
from app.api.schemas.requests import (RequestAccepted, RequestAcceptedOut,
                                      RequestCreateIn, RequestDetailOut)
from app.core.auth import CurrentUser, current_user, require_roles
from app.core.errors import trace_id_of
from app.core.schedule import KST
from app import backend
from app.api.schemas.actions import MessageIn, SlotChoicesIn, ConsultationDelayIn
from app.api.schemas.requests import RequestStatus
from app.api.schemas.requests import CareDecisionIn, CareDecisionOut, PickupGuardiansOut
from app.api.schemas.views import CareRequestList, RequestList, MessageResponse, ChoicesResponse, ConfirmResponse, ConsultationDelayResponse
from fastapi import Query
from typing import Literal

router = APIRouter(tags=["학부모 요청"])


@router.get("/children/{child_id}/pickup-guardians", response_model=PickupGuardiansOut,
            responses=errors(401, 404, 422), summary="등록 인계자 목록 (T46 팀 확인 전 초안)")
def pickup_guardians(child_id: UUID, user: CurrentUser = Depends(current_user)):
    return backend.request_actions.care.guardians(user, child_id)


@router.get("/care-requests", response_model=CareRequestList, responses=errors(401, 403, 404, 422),
            summary="교직원 투약·귀가 요청 목록 (T46 팀 확인 전 초안)")
def care_requests(classroom_id: UUID | None = None,
                  status: Literal["received", "assigned", "completed"] | None = None,
                  page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
                  sort: Literal["-created_at", "created_at", "-updated_at", "updated_at"] = "-created_at",
                  user: CurrentUser = Depends(require_roles("teacher", "director"))):
    return backend.request_actions.care.listing(user, classroom_id, status, page, size, sort)


@router.post("/requests/{request_id}/care-decisions", response_model=CareDecisionOut,
             responses=errors(401, 403, 404, 409, 422), summary="투약·인계 실제 확인·완료 기록 (T46 팀 확인 전 초안)")
def care_decision(request_id: UUID, body: CareDecisionIn,
                  user: CurrentUser = Depends(require_roles("teacher", "director"))):
    return backend.request_actions.care.decision(user, request_id, body)


def _stream_url(request_id: UUID) -> str:
    return f"/api/v1/requests/{request_id}/stream"


@router.post("/requests", status_code=status.HTTP_202_ACCEPTED, response_model=RequestAcceptedOut,
             responses={200: {"model": RequestAcceptedOut, "description": "같은 client_request_id로 다시 보냄"},
                        **errors(401, 403, 404, 409, 422)},
             summary="요청 만들기, AI 처리 접수 (FR-02, FR-03)")
def create_request(body: RequestCreateIn, request: Request, response: Response, background_tasks: BackgroundTasks,
                   user: CurrentUser = Depends(require_roles("parent"))) -> RequestAcceptedOut:
    req, created = backend.request_actions.create(user, background_tasks=background_tasks,
                                                  trace_id=trace_id_of(request), **body.model_dump())
    if not created:
        response.status_code = status.HTTP_200_OK
    return RequestAcceptedOut(request=RequestAccepted(id=req["id"], status="received" if created else req["status"],
                                                      stream_url=_stream_url(req["id"])))


@router.get("/requests/{request_id}", response_model=RequestDetailOut, responses=errors(401, 404, 422),
            summary="요청 상세·대화·진행 기록 (FR-02, FR-11)")
def get_request(request_id: UUID, user: CurrentUser = Depends(current_user)) -> RequestDetailOut:
    return backend.request_actions.detail(user, request_id)


@router.get("/requests", response_model=RequestList, responses=errors(401, 403, 422))
def list_requests(status: RequestStatus | None = None, page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
                  sort: Literal["-created_at", "created_at", "-updated_at", "updated_at"] = "-created_at",
                  user: CurrentUser = Depends(require_roles("parent"))):
    return backend.request_actions.listing(user, status, page, size, sort)


@router.get("/requests/{request_id}/stream", response_class=Response,
            responses={200: {"content": {"text/event-stream": {"schema": {"type": "string"}}}}, **errors(401, 403, 404, 422)})
def request_stream(request_id: UUID, user: CurrentUser = Depends(require_roles("parent"))):
    return backend.request_actions.stream(user, request_id)


@router.post("/requests/{request_id}/messages", status_code=201, response_model=MessageResponse, responses=errors(401, 403, 404, 409, 422))
def add_message(request_id: UUID, body: MessageIn, background_tasks: BackgroundTasks, user: CurrentUser = Depends(require_roles("parent"))):
    return backend.request_actions.message(user, request_id, body.body, background_tasks=background_tasks)


@router.post("/requests/{request_id}/slot-choices", response_model=ChoicesResponse,
             responses={**errors(401, 403, 404, 409, 422),
                        409: {**errors(409)[409], "description": "SLOT_PAST: 이미 시작한 후보; SLOT_TAKEN: 예약·체크 충돌"}})
def choose_slots(request_id: UUID, body: SlotChoicesIn, user: CurrentUser = Depends(require_roles("parent"))):
    return backend.request_actions.choices(user, request_id, body)


@router.post("/requests/{request_id}/confirm", response_model=ConfirmResponse, responses=errors(401, 403, 404, 409, 422))
def confirm_request(request_id: UUID, user: CurrentUser = Depends(require_roles("parent"))):
    return backend.request_actions.confirm(user, request_id)


@router.post("/consultations/{booking_id}/delay", response_model=ConsultationDelayResponse,
             responses=errors(401, 403, 404, 409, 422), summary="상담 지연 기록 ([제안] v0.6 T48)")
def consultation_delay(booking_id: UUID, body: ConsultationDelayIn,
                       user: CurrentUser = Depends(require_roles("teacher"))):
    result = backend.consultation_reminders.report_delay(user, booking_id, body.expected_end_at)
    # 입력 직후에는 이 예약 담임의 같은 한국 날짜만 점검해요. DB 전체 점검은 Beat가 맡아요.
    backend.consultation_reminders.sweep_consultation_notifications(
        teacher_id=user.id, day=result["booking"]["period"]["start"].astimezone(KST).date())
    return result
