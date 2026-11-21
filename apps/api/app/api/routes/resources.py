"""알림·알림장·자료 API."""

from datetime import date as Date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Query, Response, UploadFile

from app.api.schemas.actions import NoteDraftIn, NoteBatchIn, NotePatchIn
from app.api.schemas.auth import ChildList
from app.api.schemas.views import (NotificationList, NotificationResponse, DraftResponse, NoteList, NoteResponse,
                                  SendResponse, DocumentResponse, DocumentList)
from app.api.schemas.common import errors
from app.core.auth import CurrentUser, current_user as note_user, require_roles as note_roles
# T27에서 걷을 목록: 자료·알림의 workflows 별칭. 알림장은 위 core.auth를 직접 쓴다.
from app.core.workflows import workflow_user as current_user, require_workflow_roles as require_roles
from app import backend
from app.backend import store, notifications, documents

router = APIRouter(tags=["알림장·자료"])
Sort = Literal["-created_at", "created_at"]


def page_of(items, page, size, sort="-created_at"):
    items = sorted(items, key=lambda item: item.created_at if hasattr(item, "created_at") else str(item.id),
                   reverse=sort.startswith("-"))
    return {"items": items[(page-1)*size:page*size], "total": len(items), "page": page, "size": size}


@router.get("/notifications", response_model=NotificationList, responses=errors(401, 422))
def notification_list(page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100), sort: Sort = "-created_at",
                       user: CurrentUser = Depends(current_user)):
    result = page_of(notifications.visible(user), page, size, sort)
    result["items"] = [n.__dict__ for n in result["items"]]
    return result


@router.post("/notifications/{notification_id}/read", response_model=NotificationResponse, responses=errors(401, 404, 422))
def notification_read(notification_id: int, user: CurrentUser = Depends(current_user)):
    return {"notification": notifications.read(user, notification_id).__dict__}


@router.get("/classrooms/{classroom_id}/children", response_model=ChildList, responses=errors(401, 403, 404, 422))
def classroom_children(classroom_id: UUID, user: CurrentUser = Depends(note_roles("teacher", "director"))):
    return backend.notes.classroom_children(user, classroom_id)


@router.post("/daily-notes/drafts", status_code=202, response_model=DraftResponse,
             responses={200: {"model": DraftResponse}, **errors(401, 403, 404, 422)})
def draft_notes(body: NoteDraftIn, response: Response, background_tasks: BackgroundTasks,
                user: CurrentUser = Depends(note_roles("teacher"))):
    result, created = backend.notes.draft(user, body, background_tasks)
    if not created:
        response.status_code = 200
    return result


@router.get("/daily-notes/drafts/{input_id}", response_model=DraftResponse, responses=errors(401, 403, 404, 422))
def draft_status(input_id: UUID, user: CurrentUser = Depends(note_roles("teacher"))):
    return backend.notes.draft_view(backend.notes.input_in_scope(user, input_id))


@router.get("/daily-notes", response_model=NoteList, responses=errors(401, 403, 404, 422))
def note_list(date: Date, classroom_id: UUID | None = None, page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
              sort: Sort = "-created_at", user: CurrentUser = Depends(note_user)):
    return backend.notes.list_notes(user, date, classroom_id, page, size, sort)


@router.patch("/daily-notes/{note_id}", response_model=NoteResponse, responses=errors(401, 403, 404, 409, 422))
def patch_note(note_id: UUID, body: NotePatchIn, user: CurrentUser = Depends(note_roles("teacher"))):
    return backend.notes.patch(user, note_id, body)


@router.post("/daily-notes/send", response_model=SendResponse, responses=errors(401, 403, 404, 409, 422),
             description="초안 작업이 queued·running·failed면 409 NOTE_BATCH_BLOCKED, details.blocked=[]로 답해요.")
def send_notes(body: NoteBatchIn, user: CurrentUser = Depends(note_roles("teacher"))):
    return backend.notes.send(user, body)


@router.post("/documents", status_code=202, response_model=DocumentResponse,
             responses={200: {"model": DocumentResponse}, **errors(401, 403, 404, 409, 422)})
def upload_document(response: Response, file: UploadFile = File(...),
                    doc_type: Literal["notice", "schedule", "menu", "policy", "consult_timetable", "law", "public_data"] = Form(...),
                    visibility: Literal["staff", "parents", "all"] = Form(...), effective_from: Date = Form(...),
                    classroom_ids: list[UUID] = Form([], alias="classroom_ids[]"), replaces_document_id: UUID | None = Form(None),
                    user: CurrentUser = Depends(require_roles("teacher", "director"))):
    doc, created = documents.upload(user, file.filename or "자료", file.file.read(), doc_type, visibility,
                                    classroom_ids, effective_from, replaces_document_id)
    if not created:
        response.status_code = 200
    return {"document": documents.view(doc)}


@router.get("/documents", response_model=DocumentList, responses=errors(401, 403, 422))
def document_list(page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100), sort: Sort = "-created_at",
                  user: CurrentUser = Depends(require_roles("teacher", "director"))):
    with store._lock:
        items = documents.visible(user)
        result = page_of(items, page, size, sort)
        result["items"] = [documents.view(d) for d in result["items"]]
        return result


@router.get("/documents/{document_id}", response_model=DocumentResponse, responses=errors(401, 403, 404, 422))
def document_detail(document_id: UUID, user: CurrentUser = Depends(require_roles("teacher", "director"))):
    return {"document": documents.view(documents.in_scope(user, document_id))}
