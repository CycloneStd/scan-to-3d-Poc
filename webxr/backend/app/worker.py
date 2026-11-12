from celery import Celery

from .config import get_settings

settings = get_settings()
celery_app = Celery("webxr_backend", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_track_started=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    result_expires=3600,
    broker_connection_retry_on_startup=True,
    beat_schedule={
        "purge-expired-auth-tokens-daily": {
            "task": "app.tasks.purge_expired_auth_tokens",
            "schedule": 86400.0,
        },
        "purge-expired-upload-sessions-hourly": {
            "task": "app.tasks.purge_expired_upload_sessions",
            "schedule": 3600.0,
        },
        "purge-old-pipeline-work-daily": {
            "task": "app.tasks.purge_old_pipeline_work",
            "schedule": 86400.0,
        },
    },
)

import app.tasks  # noqa: E402,F401  register worker tasks
