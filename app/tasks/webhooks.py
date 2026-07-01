"""Celery tasks for outbound webhooks."""

from __future__ import annotations

import time
from typing import Any

import httpx
from celery.utils.log import get_task_logger

from app.core.config import settings
from app.services.webhooks import build_webhook_signature, canonical_json_bytes
from app.tasks.celery_app import celery_app

logger = get_task_logger(__name__)


def _setting(name: str, default: Any) -> Any:
    """Read settings safely across lowercase/uppercase config styles."""
    return getattr(settings, name, getattr(settings, name.upper(), default))


@celery_app.task(
    bind=True,
    name="app.tasks.webhooks.send_webhook_event",
    autoretry_for=(httpx.RequestError, httpx.HTTPStatusError),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def send_webhook_event(
    self,
    *,
    webhook_url: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Send webhook event with HMAC signature and retry/backoff.

    Retries occur for network errors and non-2xx HTTP responses.
    """
    max_retries = int(_setting("webhook_max_retries", 5))

    if self.request.retries >= max_retries:
        logger.error(
            "Webhook max retries exhausted event_id=%s url=%s",
            payload.get("event_id"),
            webhook_url,
        )
        raise RuntimeError("Webhook max retries exhausted")

    body = canonical_json_bytes(payload)
    timestamp = str(int(time.time()))
    secret = str(_setting("webhook_secret", "dev-webhook-secret-change-me"))
    timeout_seconds = float(_setting("webhook_timeout_seconds", 5.0))
    user_agent = str(_setting("webhook_user_agent", "url-shortener-analytics-webhook/1.0"))

    signature = build_webhook_signature(
        secret=secret,
        timestamp=timestamp,
        body=body,
    )

    headers = {
        "Content-Type": "application/json",
        "User-Agent": user_agent,
        "X-Webhook-Event": str(payload.get("event_type", "")),
        "X-Webhook-Event-Id": str(payload.get("event_id", "")),
        "X-Webhook-Timestamp": timestamp,
        "X-Webhook-Signature": signature,
    }

    logger.info(
        "Sending webhook event_id=%s url=%s attempt=%s",
        payload.get("event_id"),
        webhook_url,
        self.request.retries + 1,
    )

    with httpx.Client(
        timeout=timeout_seconds,
        follow_redirects=False,
    ) as client:
        response = client.post(
            webhook_url,
            content=body,
            headers=headers,
        )

    try:
        response.raise_for_status()
    except httpx.HTTPStatusError:
        logger.warning(
            "Webhook failed event_id=%s url=%s status=%s body=%s",
            payload.get("event_id"),
            webhook_url,
            response.status_code,
            response.text[:500],
        )
        raise

    logger.info(
        "Webhook delivered event_id=%s url=%s status=%s",
        payload.get("event_id"),
        webhook_url,
        response.status_code,
    )

    return {
        "event_id": payload.get("event_id"),
        "status_code": response.status_code,
    }
