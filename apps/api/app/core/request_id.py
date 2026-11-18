"""X-Request-ID 미들웨어(API 설계 문서 1.3).

화면이 보낸 값이 있으면 그대로, 없으면 서버가 만든다. 응답 헤더와 오류의 trace_id에 같은 값을 쓴다.
처리 못 한 예외도 여기서 500 INTERNAL_ERROR 형식으로 바꿔 헤더를 붙인다.
"""

import logging
from uuid import uuid4

from fastapi import Request

from app.core.errors import error_response

log = logging.getLogger("yuchion.api")


async def request_id_middleware(request: Request, call_next):
    trace_id = request.headers.get("X-Request-ID") or str(uuid4())
    request.state.trace_id = trace_id
    try:
        response = await call_next(request)
    except Exception:  # 내부 내용은 로그에만 남기고 응답에는 넣지 않는다(1.4)
        log.exception("unhandled error trace_id=%s", trace_id)
        response = error_response(request, 500, "INTERNAL_ERROR")
    response.headers["X-Request-ID"] = trace_id
    return response
