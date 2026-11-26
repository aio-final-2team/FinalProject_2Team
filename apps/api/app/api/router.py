"""/api/v1 아래 라우터를 모은다. 목록은 API 설계 문서 2장 번호 순서."""

from fastapi import APIRouter

from app.api.routes import auth, requests, cards, resources, feed, consents, calendar, notification_settings

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(requests.router)

api_router.include_router(cards.router)
api_router.include_router(resources.router)
api_router.include_router(feed.router)
api_router.include_router(consents.router)
api_router.include_router(calendar.router)
api_router.include_router(notification_settings.router)
