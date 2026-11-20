"""커밋한 작업 ID만 API 백그라운드 또는 Celery로 넘겨요."""

import logging

from app.core.config import settings

log = logging.getLogger(__name__)


def publish(job, object_id):
    from app.worker import daily_note_drafts, request_agent
    task = {"daily_note": daily_note_drafts, "request": request_agent}[job]
    try:
        task.apply_async(args=[str(object_id)], retry=False)
    except Exception as error:
        # 접수한 DB 행은 유지해요. 알림장은 주기 복구, 요청은 카드 누락 점검으로 인계해요.
        log.error("작업 전달 실패 job=%s id=%s error_type=%s", job, object_id, type(error).__name__)


def dispatch(job, object_id, background_tasks):
    if settings.run_in == "worker":
        background_tasks.add_task(publish, job, object_id)
    else:
        from app.modules.daily_notes.runner import run_daily_note_drafts
        from app.modules.requests.runner import run_request
        background_tasks.add_task({"daily_note": run_daily_note_drafts, "request": run_request}[job], object_id)
