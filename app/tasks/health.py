from __future__ import annotations

from app.tasks.celery_app import celery_app


@celery_app.task(name="health.ping")
def ping() -> str:
    """Simple Celery health task used for validation."""
    return "pong"
