"""업로드 자료에서 모델 지시로 보이는 문장을 표시한다."""

import re

SUSPICIOUS = re.compile(
    r"이전\s*지시(?:를|는|를\s*모두)?\s*무시|ignore\s+(?:all\s+)?previous\s+instructions?"
    r"|시스템\s*프롬프트|system\s+prompt|너는\s*이제|you\s+are\s+now"
    r"|AI(?:는|에게).{0,80}(?:답하라|출력하라|따르라)",
    re.IGNORECASE,
)


def suspicious_chunk(content: str) -> bool:
    return bool(SUSPICIOUS.search(content))
