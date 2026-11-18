from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.core.errors import install_error_handlers
from app.core.request_id import request_id_middleware

app = FastAPI(
    title="유치온 API",
    version="0.1.0",
    description="T13 API 설계 문서(Docs/Step2/API_설계_문서.md)의 엔드포인트. "
                "지금은 모의 API라 메모리 안 데모 데이터로 답한다(contracts/mock_api/README.md).",
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
