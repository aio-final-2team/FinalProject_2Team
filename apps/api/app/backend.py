"""백엔드 선택은 여기서만 한다. 기본 mock은 기존 구현을 그대로 쓴다.

DB 업무는 영역별로 연결한다. 아직 연결하지 않은 API는 workflows에서 막는다.
"""

from app.core.config import settings

if settings.data_backend == "mock":
    from app.mock import cards, card_views, documents, notes, notifications, request_actions, store
    users = store
else:
    from app.core import users
    from app.modules.daily_notes import notes
    from app.modules.documents import documents
    from app.modules.requests import requests as request_actions
    # T27에서 걷을 목록: 미구현 라우트 호환용 store=users 별칭(core/workflows.py 참고).
    store = users
    # 미구현 업무는 core/workflows.py에서 인증·범위를 검사한 뒤 501로 막는다.
    cards = card_views = notifications = None
