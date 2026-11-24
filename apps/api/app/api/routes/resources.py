"""알림·알림장·자료 API."""

from datetime import date as Date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Path, Query, Response, UploadFile

from app.api.schemas.actions import NoteDraftIn, NoteBatchIn, NotePatchIn, NoteCorrectIn
from app.api.schemas.auth import ChildList
from app.api.schemas.views import (NotificationList, NotificationResponse, DraftResponse, NoteList, NoteResponse,
                                  SendResponse, DocumentResponse, DocumentDetailResponse, DocumentList,
                                  MemoryKind, MemoryList, RegenerateResponse)
from app.api.schemas.common import errors
from app.core.auth import CurrentUser, current_user as note_user, require_roles as note_roles
from app.core.constants import MAX_DOCUMENT_BYTES
from app.core.errors import ApiError
from app import backend

# 자료 쓰기·상세도 DB 모드에서 연결했어요(T20). 두 모드 모두 역할만 확인하고 backend.documents를 그때그때 불러요.
require_roles = note_roles

router = APIRouter(tags=["알림장·자료"])
Sort = Literal["-created_at", "created_at"]


@router.get("/notifications", response_model=NotificationList, responses=errors(401, 422))
def notification_list(page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100), sort: Sort = "-created_at",
                       user: CurrentUser = Depends(note_user)):
    return backend.notifications.listing(user, page, size, sort)


@router.post("/notifications/{notification_id}/read", response_model=NotificationResponse, responses=errors(401, 404, 422))
def notification_read(notification_id: int, user: CurrentUser = Depends(note_user)):
    return {"notification": backend.notifications.read(user, notification_id)}


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


@router.post("/daily-notes/drafts/{input_id}/regenerate", status_code=202, response_model=RegenerateResponse,
             responses=errors(401, 403, 404, 409, 422))
def regenerate_notes(input_id: UUID, background_tasks: BackgroundTasks,
                     user: CurrentUser = Depends(note_roles("teacher"))):
    return backend.notes.regenerate(user, input_id, background_tasks)


@router.get("/memories", response_model=MemoryList, responses=errors(401, 403, 422))
def memory_list(kind: MemoryKind | None = None, page: int = Query(1, ge=1),
                size: int = Query(20, ge=1, le=100), sort: Sort = "-created_at",
                user: CurrentUser = Depends(note_roles("teacher"))):
    return backend.memories.list_memories(user, kind, page, size, sort)


@router.delete("/memories/{memory_id}", status_code=204, responses=errors(401, 403, 404, 422))
def delete_memory(memory_id: int = Path(..., ge=1), user: CurrentUser = Depends(note_roles("teacher"))):
    backend.memories.delete(user, memory_id)
    return Response(status_code=204)


@router.get("/daily-notes", response_model=NoteList, responses=errors(401, 403, 404, 422))
def note_list(date: Date, classroom_id: UUID | None = None, page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
              sort: Sort = "-created_at", user: CurrentUser = Depends(note_user)):
    return backend.notes.list_notes(user, date, classroom_id, page, size, sort)


@router.patch("/daily-notes/{note_id}", response_model=NoteResponse, responses=errors(401, 403, 404, 409, 422))
def patch_note(note_id: UUID, body: NotePatchIn, user: CurrentUser = Depends(note_roles("teacher"))):
    return backend.notes.patch(user, note_id, body)


@router.post("/daily-notes/{note_id}/correct", response_model=NoteResponse,
             responses=errors(401, 403, 404, 409, 422),
             description="[제안] 보낸 알림장만 정정하고 보호자에게 알림을 남겨요. 현재 version이 필요해요.")
def correct_note(note_id: UUID, body: NoteCorrectIn, user: CurrentUser = Depends(note_roles("teacher", "director"))):
    return backend.notes.correct(user, note_id, body)


@router.post("/daily-notes/send", response_model=SendResponse, responses=errors(401, 403, 404, 409, 422),
             description="초안 작업이 queued·running·failed면 409 NOTE_BATCH_BLOCKED, details.blocked=[]로 답해요.")
def send_notes(body: NoteBatchIn, user: CurrentUser = Depends(note_roles("teacher"))):
    return backend.notes.send(user, body)


@router.post("/documents", status_code=202, response_model=DocumentResponse,
             responses={200: {"model": DocumentResponse}, **errors(401, 403, 404, 409, 413, 422)})
def upload_document(response: Response, file: UploadFile = File(...),
                    doc_type: Literal["notice", "schedule", "menu", "policy", "consult_timetable", "law", "public_data"] = Form(...),
                    visibility: Literal["staff", "parents", "all"] = Form(...), effective_from: Date = Form(...),
                    classroom_ids: list[UUID] = Form([], alias="classroom_ids[]"), replaces_document_id: UUID | None = Form(None),
                    user: CurrentUser = Depends(require_roles("teacher", "director"))):
    data = file.file.read(MAX_DOCUMENT_BYTES + 1)
    if len(data) > MAX_DOCUMENT_BYTES:
        raise ApiError(413, "VALIDATION_FAILED", message="자료 파일은 2MiB 이하여야 해요.")
    doc, created = backend.documents.upload(user, file.filename or "자료", data, doc_type, visibility,
                                    classroom_ids, effective_from, replaces_document_id)
    if not created:
        response.status_code = 200
    return {"document": backend.documents.view(doc)}


@router.get("/documents", response_model=DocumentList, responses=errors(401, 403, 422))
def document_list(page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100), sort: Sort = "-created_at",
                  user: CurrentUser = Depends(note_roles("teacher", "director"))):
    return backend.documents.list_documents(user, page, size, sort)


@router.get("/documents/{document_id}", response_model=DocumentDetailResponse, responses=errors(401, 403, 404, 422))
def document_detail(document_id: UUID, user: CurrentUser = Depends(require_roles("teacher", "director"))):
    return {"document": backend.documents.view(backend.documents.in_scope(user, document_id), include_chunks=True)}
