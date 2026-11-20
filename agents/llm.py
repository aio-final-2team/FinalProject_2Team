"""에이전트가 쓰는 모델 호출. 역할별 모델 이름은 .env의 LLM_MODEL_*를 읽는다(API 설계 문서 8장)."""

import json
import os
from typing import Protocol


class ModelError(Exception):
    """모델 호출이 실패했거나 JSON이 아닌 답을 받았다."""


class JsonModel(Protocol):
    def json(self, system: str, user: str) -> dict: ...


def model_name(role: str) -> str:
    """role: SUPERVISOR·DOCUMENT·MEMORY·CHECKER. 비어 있으면 LLM_MODEL_DEFAULT."""
    return os.getenv(f"LLM_MODEL_{role}") or os.getenv("LLM_MODEL_DEFAULT", "gpt-6-luna")


class OpenAIModel:
    """JSON 한 덩어리를 돌려받는 단순 호출. 시간 초과는 30초(T13 5장 TOOL_TIMEOUT과 같음)."""

    def __init__(self, role: str, timeout: float = 30.0):
        self.name = model_name(role)
        self.timeout = timeout

    def json(self, system: str, user: str) -> dict:
        try:
            from openai import OpenAI

            response = OpenAI(timeout=self.timeout).chat.completions.create(
                model=self.name,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                response_format={"type": "json_object"},
            )
            return json.loads(response.choices[0].message.content)
        except Exception as error:  # 네트워크·인증·JSON 오류를 모두 같은 실패로 다룬다
            raise ModelError(str(error)) from error
