from contextlib import asynccontextmanager

import anyio
from fastapi import BackgroundTasks, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.core.errors import install_error_handlers
from app.core.request_id import request_id_middleware


@asynccontextmanager
async def lifespan(app):
    if settings.data_backend == "mock":
        yield
        return
    from app.modules.daily_notes.runner import requeue_daily_note_drafts, run_daily_note_drafts
    pending = await anyio.to_thread.run_sync(requeue_daily_note_drafts)
    tasks = BackgroundTasks()
    for input_id in pending:
        tasks.add_task(run_daily_note_drafts, input_id)
    async with anyio.create_task_group() as group:
        group.start_soon(tasks)
        yield


app = FastAPI(
    title="유치온 API",
    version="0.1.0",
    description="T13 API 설계 문서(Docs/Step2/API_설계_문서.md)의 엔드포인트. "
                "지금은 모의 API라 메모리 안 데모 데이터로 답한다(contracts/mock_api/README.md).",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)
app.middleware("http")(request_id_middleware)
install_error_handlers(app)
app.include_router(api_router)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
