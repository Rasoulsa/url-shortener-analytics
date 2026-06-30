from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import Request
from kombu.exceptions import KombuError

from app.core.config import settings
from app.tasks.analytics import process_click_event

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
    """
    if not settings.analytics_queue_enabled:
        return False

    try:
        process_click_event.apply_async(
            kwargs={
                "short_code": short_code,
                "clicked_at": datetime.now(UTC).isoformat(),
                "ip_address": _client_ip(request),
                "user_agent": request.headers.get("User-Agent"),
                "referrer": request.headers.get("Referer"),
            },
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
