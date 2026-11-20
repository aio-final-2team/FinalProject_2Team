"""백엔드 선택은 여기서만 한다. 기본 mock은 기존 구현을 그대로 쓴다.

T24는 DB 인증·범위 검사까지다. 알림장·요청 업무는 다음 항목에서 하나씩 연결한다.
"""

from app.core.config import settings

if settings.data_backend == "mock":
    from app.mock import cards, card_views, documents, notes, notifications, request_actions, store
    users = store
else:
    from app.core import users
    store = users
    # 미구현 업무는 core/workflows.py에서 인증·범위를 검사한 뒤 501로 막는다.
    cards = card_views = documents = notes = notifications = request_actions = None
