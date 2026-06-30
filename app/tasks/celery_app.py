from __future__ import annotations

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "url_shortener_analytics",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.tasks.health",
        "app.tasks.analytics",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    broker_connection_retry_on_startup=True,
    task_track_started=True,
    task_always_eager=settings.celery_task_always_eager,
    result_expires=settings.celery_result_expires_seconds,
    worker_prefetch_multiplier=1,
    task_routes={
        "health.*": {"queue": "default"},
        "analytics.*": {"queue": "analytics"},
    },
)
