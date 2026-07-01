"""Webhook dispatch helpers.

This module contains the database-side idempotency guard and payload/signature
helpers for click-threshold webhooks.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.link import Link

WEBHOOK_EVENT_TYPE_CLICK_THRESHOLD = "link.click_threshold_reached"


@dataclass(frozen=True)
class WebhookDispatch:
    """A webhook event that has been marked for one-time dispatch."""

    link_id: int
    short_code: str
    long_url: str
    click_count: int
    webhook_threshold: int
    webhook_url: str
    event_id: str
    event_type: str
    occurred_at: str


def canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    """Return deterministic JSON bytes for HMAC signing."""
    return json.dumps(
        payload,
        separators=(",", ":"),
        sort_keys=True,
        ensure_ascii=False,
    ).encode("utf-8")


def build_webhook_signature(
    *,
    secret: str,
    timestamp: str,
    body: bytes,
) -> str:
    """Build Stripe-style HMAC signature.

    Signature payload format:

        <timestamp>.<raw_body>

    Returned header format:

        sha256=<hex>
    """
    signed_payload = timestamp.encode("utf-8") + b"." + body
    digest = hmac.new(
        secret.encode("utf-8"),
        signed_payload,
        hashlib.sha256,
    ).hexdigest()
    return f"sha256={digest}"


def build_click_threshold_payload(dispatch: WebhookDispatch) -> dict[str, Any]:
    """Build public webhook JSON payload."""
    return {
        "event_id": dispatch.event_id,
        "event_type": dispatch.event_type,
        "occurred_at": dispatch.occurred_at,
        "data": {
            "link_id": dispatch.link_id,
            "short_code": dispatch.short_code,
            "long_url": dispatch.long_url,
            "click_count": dispatch.click_count,
            "webhook_threshold": dispatch.webhook_threshold,
        },
    }


async def mark_threshold_webhooks_for_firing(
    db: AsyncSession,
    *,
    short_codes: list[str] | None = None,
) -> list[WebhookDispatch]:
    """Atomically mark threshold-crossed links as webhook_fired.

    This is the idempotency guard.

    A webhook is eligible when:

    - webhook_url is not null
    - webhook_threshold is not null
    - webhook_fired is false
    - click_count >= webhook_threshold

    The function marks each eligible link as fired before enqueueing Celery.
    If another worker tries to process the same link, the guarded UPDATE will
    affect zero rows and no duplicate webhook will be returned.
    """
    now = datetime.now(UTC)

    stmt = select(Link).where(
        Link.webhook_url.is_not(None),
        Link.webhook_threshold.is_not(None),
        Link.webhook_fired.is_(False),
        Link.click_count >= Link.webhook_threshold,
    )

    if short_codes:
        stmt = stmt.where(Link.short_code.in_(short_codes))

    result = await db.execute(stmt)
    links = result.scalars().all()

    dispatches: list[WebhookDispatch] = []

    for link in links:
        update_stmt = (
            update(Link)
            .where(
                Link.id == link.id,
                Link.webhook_fired.is_(False),
                Link.webhook_url.is_not(None),
                Link.webhook_threshold.is_not(None),
                Link.click_count >= Link.webhook_threshold,
            )
            .values(
                webhook_fired=True,
                webhook_fired_at=now,
            )
            .returning(
                Link.id,
                Link.short_code,
                Link.long_url,
                Link.click_count,
                Link.webhook_threshold,
                Link.webhook_url,
            )
        )

        row = (await db.execute(update_stmt)).first()
        if row is None:
            continue

        link_id = int(row.id)
        threshold = int(row.webhook_threshold)
        event_id = f"link.threshold.{link_id}.{threshold}"

        dispatches.append(
            WebhookDispatch(
                link_id=link_id,
                short_code=str(row.short_code),
                long_url=str(row.long_url),
                click_count=int(row.click_count),
                webhook_threshold=threshold,
                webhook_url=str(row.webhook_url),
                event_id=event_id,
                event_type=WEBHOOK_EVENT_TYPE_CLICK_THRESHOLD,
                occurred_at=now.isoformat().replace("+00:00", "Z"),
            )
        )

    return dispatches


def enqueue_webhook_dispatches(dispatches: list[WebhookDispatch]) -> None:
    """Enqueue webhook dispatches after DB commit."""
    if not dispatches:
        return

    from app.tasks.webhooks import send_webhook_event

    for dispatch in dispatches:
        payload = build_click_threshold_payload(dispatch)
        send_webhook_event.delay(
            webhook_url=dispatch.webhook_url,
            payload=payload,
        )
