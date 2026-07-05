from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import Request
from kombu.exceptions import KombuError

from app.core.config import settings
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def enqueue_click_event(
    *,
    short_code: str,
    request: Request,
) -> bool:
    """
    Enqueue click analytics without blocking the redirect path.

    If Celery/Redis broker is unavailable, fail open:
    the redirect should still work.

    In test/eager mode (CELERY_TASK_ALWAYS_EAGER=true) we skip the broker
    entirely — send_task() ignores the eager flag and would emit a warning.
    """
    if not settings.analytics_queue_enabled:
        return False

    # send_task() does not honour task_always_eager; skip the broker in
    # eager/test mode to avoid the AlwaysEagerIgnored warning.
    if celery_app.conf.task_always_eager:
        logger.debug(
            "Eager mode active — skipping broker enqueue for short_code=%s",
            short_code,
        )
        return False

    payload: dict[str, Any] = {
        "short_code": short_code,
        "clicked_at": datetime.now(UTC).isoformat(),
        "ip_address": _client_ip(request),
        "user_agent": request.headers.get("User-Agent"),
        "referrer": request.headers.get("Referer"),
    }

    try:
        celery_app.send_task(
            "analytics.process_click_event",
            kwargs=payload,
            ignore_result=True,
            queue="analytics",
        )
    except (KombuError, OSError, RuntimeError) as exc:
        logger.warning(
            "Failed to enqueue click analytics for short_code=%s: %s",
            short_code,
            exc,
        )
        return False

    return True


def _client_ip(request: Request) -> str | None:
    forwarded_for = request.headers.get("X-Forwarded-For")

    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    if request.client is None:
        return None

    return request.client.host
