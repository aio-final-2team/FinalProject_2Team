"""12~21번 교직원 API."""

from uuid import UUID
from typing import Literal

from fastapi import APIRouter, Depends, Query, Response

from app.api.schemas.actions import (InboxFilter, CardKind, DecisionIn, ReclassifyIn, BookingIn,
                                    InstructionIn, ReassignIn, RuleDecisionIn)
from app.api.schemas.views import (CardList, CardDetail, DecisionResponse, ReclassifyResponse, BookingResponse,
                                  ReassignResponse, RuleResponse, Overview)
from app.api.schemas.common import errors
from app.core.auth import CurrentUser, require_roles
# 기억 규칙 결정은 T39에서 연결해요.
from app.core.workflows import workflow_user
from app import backend

router = APIRouter(tags=["교직원 받은함"])
staff = require_roles("teacher", "director")


@router.get("/cards", response_model=CardList, responses=errors(401, 403, 422))
def list_cards(filter: InboxFilter | None = None, request_type: Literal["complaint", "consultation", "inquiry", "all"] | None = None,
               risk_level: Literal["urgent"] | None = None, kind: CardKind | None = None,
               assignee: Literal["me"] | None = None, page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
               user: CurrentUser = Depends(staff)):
    return backend.card_views.listing(user, filter, request_type, risk_level, kind, assignee, page, size)


@router.get("/cards/{card_id}", response_model=CardDetail, responses=errors(401, 403, 404, 422))
def get_card(card_id: UUID, user: CurrentUser = Depends(staff)):
    return backend.card_views.detail(user, card_id)


@router.get("/cards/{card_id}/stream", response_class=Response,
            responses={200: {"content": {"text/event-stream": {"schema": {"type": "string"}}}}, **errors(401, 403, 404, 422)})
def card_stream(card_id: UUID, user: CurrentUser = Depends(staff)):
    return backend.cards.stream(user, card_id)


@router.post("/cards/{card_id}/decisions", response_model=DecisionResponse, responses=errors(401, 403, 404, 409, 422))
def decide(card_id: UUID, body: DecisionIn, user: CurrentUser = Depends(staff)):
    return backend.cards.decide(user, card_id, body)


@router.post("/cards/{card_id}/reclassify", response_model=ReclassifyResponse, responses=errors(401, 403, 404, 409, 422))
def reclassify(card_id: UUID, body: ReclassifyIn, user: CurrentUser = Depends(staff)):
    return backend.cards.reclassify(user, card_id, body)


@router.post("/cards/{card_id}/bookings", response_model=BookingResponse, responses=errors(401, 403, 404, 409, 422))
def book(card_id: UUID, body: BookingIn, user: CurrentUser = Depends(require_roles("teacher"))):
    return backend.cards.book(user, card_id, body)


@router.post("/cards/{card_id}/instructions", response_model=DecisionResponse, responses=errors(401, 403, 404, 409, 422))
def instruct(card_id: UUID, body: InstructionIn, user: CurrentUser = Depends(require_roles("director"))):
    return backend.cards.instruct(user, card_id, body)


@router.post("/cards/{card_id}/reassign", response_model=ReassignResponse, responses=errors(401, 403, 404, 409, 422))
def reassign(card_id: UUID, body: ReassignIn, user: CurrentUser = Depends(require_roles("director"))):
    return backend.cards.reassign(user, card_id, body)


@router.post("/memory-rules/{rule_id}/decision", response_model=RuleResponse, responses=errors(401, 404, 409, 422))
def rule_decision(rule_id: UUID, body: RuleDecisionIn, user: CurrentUser = Depends(workflow_user)):
    return backend.cards.rule_decision(user, rule_id, body)


@router.get("/overview", response_model=Overview, responses=errors(401, 403))
def overview(user: CurrentUser = Depends(require_roles("director"))):
    return backend.card_views.overview(user)
