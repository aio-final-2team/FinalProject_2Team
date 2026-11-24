"""커밋한 작업 ID만 API 백그라운드 또는 Celery로 넘겨요."""

import logging

from app.core.config import settings

log = logging.getLogger(__name__)
API_MAINTENANCE_INTERVAL = 300


def run_api_maintenance():
    """API 단독 실행의 점검. 여러 API 프로세스가 동시에 AI 재전달을 하지 않아요."""
    from datetime import datetime
    from sqlalchemy import text
    from app.core.db import transaction
    from app.core.schedule import KST
    from app.modules.requests.requests import sweep_expired_requests
    from app.modules.requests.runner import sweep_missing_cards

    try:
        with transaction() as connection:
            if not connection.scalar(text(
                "SELECT pg_try_advisory_xact_lock(hashtextextended('api:maintenance',0))"
            )):
                return
            sweep_expired_requests()
            sweep_missing_cards(datetime.now(KST))
    except Exception as error:
        log.error("API 주기 점검 실패 error_type=%s", type(error).__name__)


def check_broker():
    """시작 때 한 번만 확인해요. 접속 실패는 경고하고 API는 계속 띄워요."""
    from app.worker import celery_app
    try:
        with celery_app.connection_for_write(connect_timeout=2) as connection:
            connection.ensure_connection(max_retries=0)
    except Exception as error:
        log.warning("워커 브로커 접속 실패: worker 프로필·CELERY_BROKER_URL을 확인해 주세요. error_type=%s",
                    type(error).__name__)


def publish(job, object_id):
    from app.worker import daily_note_drafts, request_agent
    task = {"daily_note": daily_note_drafts, "request": request_agent}[job]
    try:
        task.apply_async(args=[str(object_id)], retry=False)
    except Exception as error:
        # 접수한 행은 유지해요. 요청은 주기 점검으로, 알림장은 실패 표시 뒤 담임의 다시 만들기로 복구해요.
        log.error("작업 전달 실패 job=%s id=%s error_type=%s", job, object_id, type(error).__name__)
        if job == "daily_note":
            from app.modules.daily_notes.runner import queue_failed
            queue_failed(object_id)


def dispatch(job, object_id, background_tasks):
    if settings.run_in == "worker":
        background_tasks.add_task(publish, job, object_id)
    else:
        from app.modules.daily_notes.runner import run_daily_note_drafts
        from app.modules.requests.runner import run_request
        background_tasks.add_task({"daily_note": run_daily_note_drafts, "request": run_request}[job], object_id)
