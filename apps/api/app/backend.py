"""백엔드 선택은 여기서만 한다. 기본 mock은 기존 구현을 그대로 쓴다.

T19는 DB 연결·마이그레이션까지다. DB API는 T24·T27에서 이곳에 연결한다.
그 전에는 DB 모드로 메모리 구현을 실행하지 않도록 기동을 막는다.
"""

from app.core.config import settings

if settings.data_backend == "mock":
    from app.mock import cards, card_views, documents, notes, notifications, request_actions, store
else:
    raise RuntimeError("DATA_BACKEND=db API는 T24·T27에서 연결해요. T19에서는 마이그레이션·시드만 실행할 수 있어요.")
