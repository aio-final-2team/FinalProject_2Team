"""X-Request-ID 미들웨어(API 설계 문서 1.3).

화면이 보낸 값이 있으면 그대로, 없으면 서버가 만든다. 응답 헤더와 오류의 trace_id에 같은 값을 쓴다.
처리 못 한 예외도 여기서 500 INTERNAL_ERROR 형식으로 바꿔 헤더를 붙인다.
"""

import logging
from collections import deque
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
import traceback

active_trace_id = ContextVar("trace_id", default=None)
from uuid import uuid4

from fastapi import Request

from app.core.errors import error_response
from app.core.config import settings

log = logging.getLogger("yuchion.api")
# shortcut: API 최근 500건만 보관해요. worker·영구 이력이 필요해지면 별도 수집기로 옮겨요.
qa_errors = deque(maxlen=500)


async def request_id_middleware(request: Request, call_next):
    trace_id = request.headers.get("X-Request-ID") or str(uuid4())
    request.state.trace_id = trace_id
    active_trace_id.set(trace_id)
    try:
        response = await call_next(request)
    except Exception as exc:  # 내부 내용은 로그에만 남기고 응답에는 넣지 않는다(1.4)
        log.exception("unhandled error trace_id=%s", trace_id)
        if settings.qa_tools:
            frame = traceback.extract_tb(exc.__traceback__)[-1]
            qa_errors.append({"trace_id": trace_id, "org_id": getattr(request.state, "qa_org_id", None),
                              "at": datetime.now(timezone.utc), "method": request.method, "path": request.url.path,
                              "status": 500, "error_type": type(exc).__name__,
                              "where": f"{Path(frame.filename).name}:{frame.lineno}"})
        response = error_response(request, 500, "INTERNAL_ERROR")
    response.headers["X-Request-ID"] = trace_id
    return response
