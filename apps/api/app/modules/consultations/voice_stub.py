"""실제 음성을 읽지 않는 가상 상담 대역이에요."""


def analyze(path):
    return {"transcript": "[가상] 보호자: 친구와 어울리는 모습을 알려 주세요.\n교사: 다음 상담에서 함께 살펴볼게요.",
            "result": {"summary": "가상 상담에서 또래 관계를 이야기했어요.",
                       "parent_requests": ["친구와 어울리는 모습 안내"], "follow_ups": ["다음 상담에서 확인"]}}
