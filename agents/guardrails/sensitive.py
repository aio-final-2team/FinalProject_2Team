"""모델 입력 가리기와 답변 초안 검사가 공유하는 민감정보 형식."""

import re

SENSITIVE = re.compile(
    r"(?P<phone>(?<!\d)01[016789][- .]?\d{3,4}[- .]?\d{4}(?!\d))"
    r"|(?P<resident>(?<!\d)\d{6}[- ]?[1-4]\d{6}(?!\d))"
    r"|(?P<account>(?<!\d)\d{3,6}[- ]\d{2,6}[- ]\d{3,6}(?!\d))"
    r"|(?P<email>[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})"
)

LABELS = {"phone": "전화번호", "resident": "주민등록번호", "account": "계좌번호", "email": "이메일"}


def mask_sensitive(text: str) -> str:
    return SENSITIVE.sub(lambda match: f"[{LABELS[match.lastgroup]}]", text)
