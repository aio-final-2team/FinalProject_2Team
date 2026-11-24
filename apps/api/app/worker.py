"""같은 DB 입구를 쓰는 Celery 태스크예요. 큐에는 입력 본문 없이 ID만 넘겨요."""

from datetime import datetime
import logging

from celery import Celery
from celery.signals import worker_init, beat_init

from app.core.config import settings
from app.core.schedule import KST

celery_app = Celery("yuchion", broker=settings.celery_broker_url)
celery_app.conf.update(
    task_serializer="json", accept_content=["json"], result_serializer="json",
    task_ignore_result=True, task_default_queue="default",
    task_routes={"yuchion.daily_note_drafts": {"queue": "notes"}},
    worker_prefetch_multiplier=1, task_acks_late=True, task_reject_on_worker_lost=True,
    broker_connection_retry_on_startup=True,
    broker_transport_options={"socket_connect_timeout": 2, "socket_timeout": 2},
    timezone="Asia/Seoul", enable_utc=True,
    beat_schedule={
        "missing-cards-and-drafts": {"task": "yuchion.sweep", "schedule": 300.0,
                                     "options": {"expires": 290}},
        "notifications": {"task": "yuchion.deliver_notifications", "schedule": 60.0,
                          "options": {"expires": 55}},
        "consultation-reminders": {"task": "yuchion.consultation_reminders", "schedule": 60.0,
                                   "options": {"expires": 55}},
        "request-expiry": {"task": "yuchion.expire_requests", "schedule": 60.0,
                           "options": {"expires": 55}},
    },
)


def enabled():
    return settings.data_backend == "db" and settings.run_in == "worker"


@worker_init.connect
@beat_init.connect
def warn_disabled_worker(**kwargs):
    if not enabled():
        logging.getLogger(__name__).warning(
            "워커 작업 비활성: DATA_BACKEND=db·RUN_IN=worker와 worker 프로필을 함께 설정해 주세요.")


@celery_app.task(name="yuchion.daily_note_drafts")
def daily_note_drafts(input_id):
    if enabled():
        from app.modules.daily_notes.runner import run_daily_note_drafts
        run_daily_note_drafts(input_id)


@celery_app.task(name="yuchion.request_agent")
def request_agent(request_id):
    if enabled():
        from app.modules.requests.runner import run_request
        run_request(request_id)


@celery_app.task(name="yuchion.sweep")
def sweep():
    if enabled():
        from app.core.jobs import publish
        from app.modules.daily_notes.runner import requeue_daily_note_drafts
        from app.modules.requests.runner import sweep_missing_cards
        count = sweep_missing_cards(datetime.now(KST))
        for input_id in requeue_daily_note_drafts(stale_only=True):
            publish("daily_note", input_id)
        return count
    return 0


@celery_app.task(name="yuchion.deliver_notifications")
def deliver_notifications():
    if enabled():
        from app.modules.notifications.delivery import deliver_pending
        return deliver_pending()
    return 0


@celery_app.task(name="yuchion.consultation_reminders")
def consultation_reminders():
    if enabled():
        from app.modules.consultations.reminders import sweep_consultation_notifications
        return sweep_consultation_notifications()
    return 0


@celery_app.task(name="yuchion.expire_requests")
def expire_requests():
    if enabled():
        from app.modules.requests.requests import sweep_expired_requests
        return sweep_expired_requests()
    return 0
