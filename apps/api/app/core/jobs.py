"""커밋한 작업 ID만 API 백그라운드 또는 Celery로 넘겨요."""

import logging

from app.core.config import settings

log = logging.getLogger(__name__)


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
    from app.worker import daily_note_drafts, request_agent, voice_analysis
    task = {"daily_note": daily_note_drafts, "request": request_agent, "voice_analysis": voice_analysis}[job]
    try:
        task.apply_async(args=[str(object_id)], retry=False)
    except Exception as error:
        # 접수 행은 유지해요. 음성은 점검에서 실패로 끝내고, 기존 요청·초안은 복구 규칙을 따라요.
        log.error("작업 전달 실패 job=%s id=%s error_type=%s", job, object_id, type(error).__name__)


def dispatch(job, object_id, background_tasks):
    if settings.run_in == "worker" and not (job == "voice_analysis" and settings.data_backend == "mock"):
        background_tasks.add_task(publish, job, object_id)
    else:
        from app.modules.daily_notes.runner import run_daily_note_drafts
        from app.modules.requests.runner import run_request
        from app.modules.consultations.voice_runner import run_voice_analysis
        background_tasks.add_task({"daily_note": run_daily_note_drafts, "request": run_request,
                                   "voice_analysis": run_voice_analysis}[job], object_id)
