from __future__ import annotations

import hashlib
import ipaddress
from datetime import UTC, datetime
from typing import Any

from celery.utils.log import get_task_logger
from redis import Redis
from redis.exceptions import RedisError

from app.core.config import settings
from app.tasks.celery_app import celery_app

logger = get_task_logger(__name__)


def _sync_redis_client() -> Redis:
    """
    Celery tasks run synchronously, so use the synchronous Redis client here.
    Do not import the app's async redis_client.
    """
    return Redis.from_url(
        settings.redis_url,
        decode_responses=True,
    )


def _anonymize_ip(ip_address: str | None) -> str | None:
    """
    Privacy-friendly IP anonymization.

    IPv4: keep /24 by zeroing the last octet.
    IPv6: keep /64 by zeroing the lower 64 bits.
    """
    if not ip_address:
        return None

    try:
        ip = ipaddress.ip_address(ip_address)

        if isinstance(ip, ipaddress.IPv4Address):
            network = ipaddress.ip_network(f"{ip}/24", strict=False)
            return str(network.network_address)

        network = ipaddress.ip_network(f"{ip}/64", strict=False)
        return str(network.network_address)

    except ValueError:
        return None


def _hash_value(value: str | None) -> str | None:
    if not value:
        return None

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _parse_clicked_at(clicked_at: str | None) -> datetime:
    if not clicked_at:
        return datetime.now(UTC)

    try:
        normalized = clicked_at.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)

        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)

        return parsed.astimezone(UTC)
    except ValueError:
        return datetime.now(UTC)


@celery_app.task(
    bind=True,
    name="analytics.process_click_event",
    autoretry_for=(RedisError,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def process_click_event(
    self: Any,
    *,
    short_code: str,
    clicked_at: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    referrer: str | None = None,
) -> dict[str, Any]:
    """
    Process a redirect click asynchronously.

    This Day 2 setup task intentionally keeps analytics lightweight:
    - anonymizes/hash-sensitive data
    - updates Redis analytics counters
    - proves the async pipeline works end-to-end

    Later branches can extend this to write ClickEvent rows, GeoIP, UA parsing, etc.
    """
    clicked_dt = _parse_clicked_at(clicked_at)
    day = clicked_dt.date().isoformat()

    anonymized_ip = _anonymize_ip(ip_address)
    ip_hash = _hash_value(anonymized_ip)
    user_agent_hash = _hash_value(user_agent)
    referrer_hash = _hash_value(referrer)

    redis = _sync_redis_client()

    pipe = redis.pipeline(transaction=True)

    pipe.incr("analytics:clicks:processed")
    pipe.incr(f"analytics:link:{short_code}:processed")
    pipe.incr(f"analytics:link:{short_code}:daily:{day}")

    pipe.hset(
        f"analytics:link:{short_code}:last_event",
        mapping={
            "short_code": short_code,
            "clicked_at": clicked_dt.isoformat(),
            "day": day,
            "ip_hash": ip_hash or "",
            "user_agent_hash": user_agent_hash or "",
            "referrer_hash": referrer_hash or "",
        },
    )

    pipe.expire(f"analytics:link:{short_code}:daily:{day}", 60 * 60 * 24 * 90)
    pipe.expire(f"analytics:link:{short_code}:last_event", 60 * 60 * 24 * 30)

    pipe.execute()

    logger.info("Processed click analytics for short_code=%s", short_code)

    return {
        "short_code": short_code,
        "clicked_at": clicked_dt.isoformat(),
        "day": day,
        "processed": True,
    }
