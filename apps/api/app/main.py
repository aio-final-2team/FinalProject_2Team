from contextlib import asynccontextmanager

import anyio
from fastapi import BackgroundTasks, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.core.errors import install_error_handlers
from app.core.request_id import request_id_middleware


async def periodic_maintenance():
    from app.core.jobs import API_MAINTENANCE_INTERVAL, run_api_maintenance
    while True:
        await anyio.sleep(API_MAINTENANCE_INTERVAL)
        await anyio.to_thread.run_sync(run_api_maintenance)


@asynccontextmanager
async def lifespan(app):
    if settings.data_backend == "mock":
        yield
        return
    from functools import partial
    from app.core.jobs import check_broker, dispatch, run_api_maintenance
    from app.modules.daily_notes.runner import requeue_daily_note_drafts
    if settings.run_in == "worker":
        await anyio.to_thread.run_sync(check_broker)
    pending = await anyio.to_thread.run_sync(partial(requeue_daily_note_drafts,
                                                   stale_only=settings.run_in == "worker"))
    tasks = BackgroundTasks()
    for input_id in pending:
        dispatch("daily_note", input_id, tasks)
    if settings.run_in == "api":
        await anyio.to_thread.run_sync(run_api_maintenance)
    async with anyio.create_task_group() as group:
        group.start_soon(tasks)
        # 주기 점검만 취소해요. 이미 맡긴 알림장 BackgroundTasks는 끝까지 마쳐요.
        async with anyio.create_task_group() as periodic:
            if settings.run_in == "api":
                periodic.start_soon(periodic_maintenance)
            try:
                yield
            finally:
                periodic.cancel_scope.cancel()


app = FastAPI(
    title="유치온 API",
    version="0.1.0",
    description="T13 API 설계 문서(Docs/Step2/API_설계_문서.md)의 엔드포인트. "
                "DATA_BACKEND=mock은 메모리 데모 데이터, db는 PostgreSQL을 사용해요. "
                "DB 지원 범위는 apps/api/README.md의 진행표를 봐 주세요.",
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
