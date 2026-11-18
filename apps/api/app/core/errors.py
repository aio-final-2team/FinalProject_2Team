"""공통 오류 형식(API 설계 문서 1.4).

모든 오류는 {"error": {code, message, trace_id, details}} 하나로 돌려준다.
형식 검사(Pydantic)는 422 VALIDATION_FAILED, 서버 검사는 ApiError로 403·404·409를 낸다(4.1).
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("yuchion.api")

DEFAULT_MESSAGES = {
    "UNAUTHENTICATED": "다시 로그인해 주세요.",
    "FORBIDDEN_ROLE": "이 일을 할 권한이 없어요.",
    "NOT_FOUND": "찾는 자료가 없어요.",
    "CARD_VERSION_CONFLICT": "다른 사람이 먼저 카드를 처리했어요. 새로고침해 주세요.",
    "ALREADY_DECIDED": "이미 결정한 카드예요.",
    "INVALID_TRANSITION": "지금 단계에서는 할 수 없는 일이에요.",
    "REASON_REQUIRED": "학부모 확인 전에 끝내려면 마무리한 방법을 적어 주세요.",
    "SLOT_TAKEN": "그 시간은 이미 다른 상담이 확정됐어요.",
    "SLOT_NOT_CHOSEN": "학부모가 고르지 않은 시간이에요.",
    "NOTE_BATCH_BLOCKED": "확인이 안 끝난 알림장이 있어요.",
    "VALIDATION_FAILED": "입력한 값을 다시 확인해 주세요.",
    "INTERNAL_ERROR": "잠시 뒤 다시 시도해 주세요.",
    "UPSTREAM_UNAVAILABLE": "잠시 뒤 다시 처리할게요.",
}


class ApiError(Exception):
    """서버 검사에서 걸린 오류. details는 code별 추가 정보(예: current_version)."""

    def __init__(self, status: int, code: str, message: str | None = None, **details):
        super().__init__(code)
        self.status = status
        self.code = code
        self.message = message or DEFAULT_MESSAGES.get(code, code)
        self.details = details


def trace_id_of(request: Request) -> str | None:
    return getattr(request.state, "trace_id", None)


def error_response(request: Request, status: int, code: str, message: str | None = None,
                   details: dict | None = None) -> JSONResponse:
    body = {"error": {
        "code": code,
        "message": message or DEFAULT_MESSAGES.get(code, code),
        "trace_id": trace_id_of(request),
        "details": details or {},
    }}
    return JSONResponse(status_code=status, content=body)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError):
        return error_response(request, exc.status, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        fields = []
        for err in exc.errors():
            loc = [str(p) for p in err.get("loc", ())]
            if loc and loc[0] in ("body", "query", "path", "header"):   # 앞의 위치 표시만 뗀다
                loc = loc[1:]
            fields.append({"field": ".".join(loc), "problem": err.get("msg", "")})
        return error_response(request, 422, "VALIDATION_FAILED", details={"fields": fields})

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        code = {401: "UNAUTHENTICATED", 403: "FORBIDDEN_ROLE", 404: "NOT_FOUND"}.get(exc.status_code)
        if code is None:
            code = "INTERNAL_ERROR" if exc.status_code >= 500 else "VALIDATION_FAILED"
        return error_response(request, exc.status_code, code)
