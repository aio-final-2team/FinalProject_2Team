"""[제안][선택] 실제 녹음 대신 synthetic=true 가상 음성만 접수해요."""

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException
from starlette.formparsers import MultiPartException

from app import backend
from app.api.schemas.common import errors
from app.api.schemas.voice_analysis import VoiceAnalysis, VoiceAnalysisList
from app.core import jobs, voice_analysis as rules
from app.core.auth import CurrentUser, current_user
from app.core.errors import ApiError

router = APIRouter(tags=["[선택] 가상 음성 분석"], dependencies=[Depends(rules.enabled)])
UPLOAD = {"requestBody": {"required": True, "content": {"multipart/form-data": {"schema": {
    "type": "object", "required": ["file", "synthetic"], "properties": {
        "file": {"type": "string", "format": "binary"}, "synthetic": {"type": "boolean", "const": True}}}}}}}


@router.post("/consultations/{booking_id}/voice-analyses", status_code=202, response_model=VoiceAnalysis,
             responses=errors(401, 403, 404, 413, 422), openapi_extra=UPLOAD)
async def create(booking_id: UUID, request: Request, response: Response, background_tasks: BackgroundTasks,
                 user: CurrentUser = Depends(current_user)):
    await run_in_threadpool(backend.voice_analyses.access, user, booking_id, write=True)
    received = 0

    async def receive():
        nonlocal received
        message = await request.receive()
        received += len(message.get("body", b""))
        if received > rules.MAX_VOICE_BYTES + 64 * 1024:
            raise MultiPartException("Upload body too large")
        return message

    try:
        async with Request(request.scope, receive).form(max_files=1, max_fields=1) as form:
            file = form.get("file")
            if (set(form) != {"file", "synthetic"} or form.get("synthetic") != "true"
                    or not isinstance(file, UploadFile)):
                raise ApiError(422, "VALIDATION_FAILED", field="file/synthetic")
            data = await file.read(rules.MAX_VOICE_BYTES + 1)
            metadata = await run_in_threadpool(rules.inspect, data)
            row = await run_in_threadpool(backend.voice_analyses.create, user, booking_id, data, metadata)
    except HTTPException:
        raise ApiError(413 if received > rules.MAX_VOICE_BYTES + 64 * 1024 else 422,
                       "VALIDATION_FAILED", field="file/synthetic") from None
    jobs.dispatch("voice_analysis", row["id"], background_tasks)
    response.headers["Cache-Control"] = "private, no-store"
    return row


@router.get("/consultations/{booking_id}/voice-analyses", response_model=VoiceAnalysisList,
            responses=errors(401, 403, 404, 422))
def listing(booking_id: UUID, response: Response, user: CurrentUser = Depends(current_user)):
    response.headers["Cache-Control"] = "private, no-store"
    return backend.voice_analyses.listing(user, booking_id)


@router.get("/voice-analyses/{analysis_id}", response_model=VoiceAnalysis, responses=errors(401, 403, 404, 422))
def detail(analysis_id: UUID, response: Response, user: CurrentUser = Depends(current_user)):
    response.headers["Cache-Control"] = "private, no-store"
    return backend.voice_analyses.get(user, analysis_id)
