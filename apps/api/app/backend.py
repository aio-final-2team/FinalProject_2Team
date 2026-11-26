"""백엔드 선택은 여기서만 한다. 기본 mock은 기존 구현을 그대로 쓴다.

DB 업무는 영역별로 연결한다. 아직 연결하지 않은 API는 workflows에서 막는다.
"""

from app.core.config import settings

if settings.data_backend == "mock":
    from app.mock import cards, card_views, documents, memories, notes, notifications, request_actions, store
    from app.mock import consultation_reminders
    from app.mock import feed, consents, calendar
    users = store
else:
    from app.modules.consents import consents
    from app.modules.feed import feed
    from app.modules.consultations import reminders as consultation_reminders
    from app.core import users
    from app.modules.daily_notes import notes
    from app.modules.documents import documents
    from app.modules.documents import calendar
    from app.modules.memories import memories
    from app.modules.requests import requests as request_actions
    # T27에서 걷을 목록: 미구현 라우트 호환용 store=users 별칭(core/workflows.py 참고).
    store = users
    from app.modules.cards import cards, card_views
    from app.modules.notifications import notifications
