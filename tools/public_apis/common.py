"""공공 API 클라이언트가 같이 쓰는 호출·오류 처리.

키는 URL에만 넣고 로그·예외 메시지·출처 주소에는 남기지 않는다.
"""

import json
import socket
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

TIMEOUT_SECONDS = 10  # API 설계 문서 6.1: 외부 법령·기상 API는 10초
KST = timezone(timedelta(hours=9))


class PublicApiError(Exception):
    """도구 실패 코드(API 설계 문서 5.2)를 담은 예외."""

    def __init__(self, code, message, retryable):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


def upstream(message, retryable=True):
    return PublicApiError("UPSTREAM_UNAVAILABLE", message, retryable)


def not_found(message):
    return PublicApiError("NOT_FOUND", message, False)


def urlopen_bytes(url, timeout):
    """기본 호출기. 시험에서는 같은 모양의 함수를 넣어 실제 호출을 막는다."""
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.status, response.read()


def fetch_json(url, name, opener=None):
    """GET 한 번. 시간 초과·연결 실패·429·5xx는 다시 해 볼 만한 UPSTREAM_UNAVAILABLE."""
    opener = opener or urlopen_bytes
    try:
        status, body = opener(url, TIMEOUT_SECONDS)
    except urllib.error.HTTPError as error:
        retryable = error.code == 429 or error.code >= 500
        raise upstream(f"{name}가 HTTP {error.code}로 답했어요", retryable) from None
    except (TimeoutError, socket.timeout):
        raise upstream(f"{name}가 {TIMEOUT_SECONDS}초 안에 응답하지 않았어요") from None
    except (urllib.error.URLError, OSError):
        raise upstream(f"{name}에 연결하지 못했어요") from None
    if status != 200:
        raise upstream(f"{name}가 HTTP {status}로 답했어요", status == 429 or status >= 500)
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        # 점검 안내 HTML·XML처럼 JSON이 아닌 응답. 키·요청 값부터 확인한다
        raise upstream(f"{name} 응답이 JSON이 아니에요(키·요청 값 확인)", False) from None


def now_kst():
    return datetime.now(KST)


def tool_result(call, trace_id=None):
    """에이전트 도구 공통 출력 형식 {ok, data | error, trace_id}로 감싼다."""
    try:
        return {"ok": True, "data": call(), "trace_id": trace_id}
    except PublicApiError as error:
        return {"ok": False, "trace_id": trace_id,
                "error": {"code": error.code, "message": error.message, "retryable": error.retryable}}
