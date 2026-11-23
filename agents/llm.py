"""에이전트가 쓰는 모델 호출. 역할별 모델 이름은 .env의 LLM_MODEL_*를 읽는다(API 설계 문서 8장).

재시도는 API 설계 문서 6.1·6.2와 같다: 1번 30초, 시간 초과·429·5xx·연결 오류만 최대 2번 다시(1초 → 2초).
400·401·403·422처럼 요청이 틀린 오류와 JSON이 아닌 답은 바로 ModelError로 올린다.
"""

import json
import os
import time
from typing import Protocol

TIMEOUT_SECONDS = 30.0
RETRY_DELAYS = (1.0, 2.0)


class ModelError(Exception):
    """모델 호출이 실패했거나 JSON이 아닌 답을 받았다. format=True면 답 모양 문제라 한 번 더 물어볼 만하다."""

    def __init__(self, message: str, format: bool = False):
        super().__init__(message)
        self.format = format


class JsonModel(Protocol):
    def json(self, system: str, user: str) -> dict: ...


def model_name(role: str) -> str:
    """role: SUPERVISOR·DOCUMENT·MEMORY·CHECKER. 비어 있으면 LLM_MODEL_DEFAULT."""
    return os.getenv(f"LLM_MODEL_{role}") or os.getenv("LLM_MODEL_DEFAULT", "gpt-6-luna")


def retryable(error: Exception) -> bool:
    """시간 초과·연결 오류·429·5xx만 다시 해 볼 만하다(6.2)."""
    name = type(error).__name__
    if name in ("APITimeoutError", "APIConnectionError", "RateLimitError", "InternalServerError", "TimeoutError"):
        return True
    status = getattr(error, "status_code", None)
    return isinstance(status, int) and (status == 429 or status >= 500)


class OpenAIModel:
    """JSON 한 덩어리를 돌려받는 호출."""

    def __init__(self, role: str, timeout: float = TIMEOUT_SECONDS, sleep=time.sleep):
        self.name = model_name(role)
        self.timeout = timeout
        self.sleep = sleep

    def _call(self, system: str, user: str) -> str:
        from openai import OpenAI

        response = OpenAI(timeout=self.timeout, max_retries=0).chat.completions.create(
            model=self.name,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content

    def json(self, system: str, user: str) -> dict:
        for attempt in range(len(RETRY_DELAYS) + 1):
            try:
                text = self._call(system, user)
                break
            except Exception as error:  # noqa: BLE001 - 종류를 보고 다시 할지 정한다
                if attempt < len(RETRY_DELAYS) and retryable(error):
                    self.sleep(RETRY_DELAYS[attempt])
                    continue
                raise ModelError(type(error).__name__) from error
        try:
            return json.loads(text)
        except (TypeError, ValueError) as error:
            raise ModelError("JSON이 아닌 답", format=True) from error
