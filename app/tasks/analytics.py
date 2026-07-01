from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Coroutine
from datetime import UTC, datetime
from typing import Any, TypeVar

from celery.utils.log import get_task_logger
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.link import Link
from app.services.analytics import create_click_event
from app.services.counters import (
    CLICK_COUNTER_TTL_SECONDS,
    PENDING_CLICK_COUNTER_SET_KEY,
    link_click_counter_key,
)
from app.services.geoip import lookup_geoip
from app.services.privacy import anonymize_ip
from app.services.user_agent import parse_user_agent
from app.services.webhooks import WebhookDispatch, build_click_threshold_payload
from app.tasks.celery_app import celery_app

logger = get_task_logger(__name__)

T = TypeVar("T")

_worker_loop: asyncio.AbstractEventLoop | None = None


def _run_async(coro: Coroutine[Any, Any, T]) -> T:  # noqa: UP047
    """
    Run async DB code from a synchronous Celery task.

    Do not use asyncio.run() here.

    asyncio.run() creates and closes a new event loop per task. SQLAlchemy's
    asyncpg connection pool can then reuse connections attached to a previous
    closed loop, causing:

        RuntimeError: got Future attached to a different loop

    Celery prefork workers process tasks inside long-lived child processes, so
    keeping one event loop per worker process is safer for async SQLAlchemy.
    """
    global _worker_loop

    if _worker_loop is None or _worker_loop.is_closed():
        _worker_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_worker_loop)

    return _worker_loop.run_until_complete(coro)


def _sync_redis_client() -> Redis:
    """
    Celery tasks run synchronously, so use the synchronous Redis client here.
    Do not import the app's async Redis client.
    """
    return Redis.from_url(
        settings.redis_url,
        decode_responses=True,
    )


def _hash_value(value: str | None) -> str | None:
    """
    Hash sensitive values before storing them in Redis debug/summary keys.
    """
    if not value:
        return None

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _parse_clicked_at(clicked_at: str | None) -> datetime:
    """
    Parse ISO datetime from the queued event.

    If missing or invalid, fall back to current UTC time.
    """
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


def _get_field(value: Any, field_name: str) -> str | None:
    """
    Support either dict-style or object/dataclass-style return values.

    Supported examples:
        {"browser": "Chrome"}
        ParsedUserAgent(browser="Chrome")
    """
    if value is None:
        return None

    if isinstance(value, dict):
        field_value = value.get(field_name)
    else:
        field_value = getattr(value, field_name, None)

    if field_value is None:
        return None

    return str(field_value)


def _safe_parse_user_agent(user_agent: str | None) -> Any:
    """
    Parse User-Agent without allowing parser failures to drop click events.
    """
    try:
        return parse_user_agent(user_agent)
    except Exception:
        logger.warning(
            "Failed to parse User-Agent for Phase 3 click analytics",
            exc_info=True,
        )
        return None


def _safe_lookup_geoip(ip_address: str | None) -> Any:
    """
    Lookup GeoIP without allowing missing/invalid GeoIP DB to drop click events.

    Raw IP is only used for lookup accuracy. It is not stored.
    """
    try:
        return lookup_geoip(ip_address)
    except Exception:
        logger.warning(
            "Failed to lookup GeoIP for Phase 3 click analytics",
            exc_info=True,
        )
        return None


async def _persist_click_event(
    *,
    short_code: str,
    clicked_at: datetime,
    ip_anonymized: str | None,
    user_agent: str | None,
    referrer: str | None,
    country: str | None,
    city: str | None,
    browser: str | None,
    os: str | None,
    device_type: str | None,
) -> dict[str, Any]:
    """
    Resolve short_code to link_id and persist one enriched Click row.
    """
    async with SessionLocal() as db:
        result = await db.execute(
            select(Link.id).where(Link.short_code == short_code),
        )
        link_id = result.scalar_one_or_none()

        if link_id is None:
            logger.warning(
                "Skipping click analytics persistence; link not found for short_code=%s",
                short_code,
            )
            return {
                "persisted": False,
                "reason": "link_not_found",
                "link_id": None,
                "click_id": None,
            }

        click = await create_click_event(
            db,
            link_id=link_id,
            clicked_at=clicked_at,
            ip_anonymized=ip_anonymized,
            user_agent=user_agent,
            referrer=referrer,
            country=country,
            city=city,
            browser=browser,
            os=os,
            device_type=device_type,
        )

        return {
            "persisted": True,
            "reason": None,
            "link_id": link_id,
            "click_id": click.id,
        }


def _record_redis_analytics(
    *,
    short_code: str,
    clicked_at: datetime,
    ip_anonymized: str | None,
    user_agent: str | None,
    referrer: str | None,
    country: str | None,
    browser: str | None,
    device_type: str | None,
    persisted: bool,
) -> None:
    """
    Keep lightweight Redis analytics counters from the previous branch.

    PostgreSQL clicks table is now the main Phase 3 analytics source.
    """
    day = clicked_at.date().isoformat()

    ip_hash = _hash_value(ip_anonymized)
    user_agent_hash = _hash_value(user_agent)
    referrer_hash = _hash_value(referrer)

    redis = _sync_redis_client()
    pipe = redis.pipeline(transaction=True)

    pipe.incr("analytics:clicks:processed")
    pipe.incr(f"analytics:link:{short_code}:processed")
    pipe.incr(f"analytics:link:{short_code}:daily:{day}")

    if country:
        pipe.incr(f"analytics:link:{short_code}:country:{country}")

    if browser:
        pipe.incr(f"analytics:link:{short_code}:browser:{browser}")

    if device_type:
        pipe.incr(f"analytics:link:{short_code}:device:{device_type}")

    pipe.hset(
        f"analytics:link:{short_code}:last_event",
        mapping={
            "short_code": short_code,
            "clicked_at": clicked_at.isoformat(),
            "day": day,
            "ip_hash": ip_hash or "",
            "user_agent_hash": user_agent_hash or "",
            "referrer_hash": referrer_hash or "",
            "country": country or "",
            "browser": browser or "",
            "device_type": device_type or "",
            "persisted": "true" if persisted else "false",
        },
    )

    ninety_days = 60 * 60 * 24 * 90
    thirty_days = 60 * 60 * 24 * 30

    pipe.expire(f"analytics:link:{short_code}:daily:{day}", ninety_days)
    pipe.expire(f"analytics:link:{short_code}:last_event", thirty_days)

    if country:
        pipe.expire(
            f"analytics:link:{short_code}:country:{country}",
            ninety_days,
        )

    if browser:
        pipe.expire(
            f"analytics:link:{short_code}:browser:{browser}",
            ninety_days,
        )

    if device_type:
        pipe.expire(
            f"analytics:link:{short_code}:device:{device_type}",
            ninety_days,
        )

    pipe.execute()


def _redis_value_to_str(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")

    return str(value)


def _redis_value_to_int(value: Any) -> int | None:
    try:
        return int(_redis_value_to_str(value))
    except (TypeError, ValueError):
        return None


def _enqueue_webhook_dispatch(dispatch: WebhookDispatch) -> None:
    """
    Enqueue webhook delivery after the database transaction commits.

    Import inside the function to avoid Celery task import cycles.
    """
    from app.tasks.webhooks import send_webhook_event

    payload = build_click_threshold_payload(dispatch)

    send_webhook_event.apply_async(
        kwargs={
            "webhook_url": dispatch.webhook_url,
            "payload": payload,
        },
    )


async def _increment_link_click_count_by(
    *,
    short_code: str,
    count: int,
) -> dict[str, Any]:
    """
    Increment links.click_count by a flushed Redis counter value.

    Also detects click-threshold webhook crossing in the same DB transaction.

    Returns:
        {
            "updated": bool,
            "webhook_dispatch": WebhookDispatch | None,
        }

    Idempotency:
    - A webhook only fires when webhook_fired is false.
    - The row is locked with SELECT ... FOR UPDATE.
    - webhook_fired is set true before commit.
    """
    async with SessionLocal() as db:
        result = await db.execute(
            select(Link).where(Link.short_code == short_code).with_for_update(),
        )
        link = result.scalar_one_or_none()

        if link is None:
            return {
                "updated": False,
                "webhook_dispatch": None,
            }

        old_click_count = link.click_count or 0
        new_click_count = old_click_count + count

        link.click_count = new_click_count

        webhook_dispatch: WebhookDispatch | None = None

        if (
            link.webhook_url
            and link.webhook_threshold is not None
            and not link.webhook_fired
            and old_click_count < link.webhook_threshold <= new_click_count
        ):
            fired_at = datetime.now(UTC)
            threshold = int(link.webhook_threshold)

            link.webhook_fired = True
            link.webhook_fired_at = fired_at

            webhook_dispatch = WebhookDispatch(
                link_id=link.id,
                short_code=link.short_code,
                long_url=link.long_url,
                click_count=new_click_count,
                webhook_threshold=threshold,
                webhook_url=link.webhook_url,
                event_id=f"link.threshold.{link.id}.{threshold}",
                event_type="link.click_threshold_reached",
                occurred_at=fired_at.isoformat().replace("+00:00", "Z"),
            )

        await db.commit()

        return {
            "updated": True,
            "webhook_dispatch": webhook_dispatch,
        }


def _get_pending_click_counter_short_codes(redis: Redis) -> list[str]:
    raw_short_codes = redis.smembers(PENDING_CLICK_COUNTER_SET_KEY)

    short_codes: set[str] = set()

    for raw_short_code in raw_short_codes:
        short_code = _redis_value_to_str(raw_short_code).strip()

        if short_code:
            short_codes.add(short_code)

    return sorted(short_codes)


def _restore_pending_click_counter(
    redis: Redis,
    *,
    short_code: str,
    count: int,
) -> None:
    """
    Restore a Redis counter if database flush fails after GETDEL.

    This keeps the flush task retryable for handled SQLAlchemy failures.
    """
    counter_key = link_click_counter_key(short_code)

    pipe = redis.pipeline(transaction=True)
    pipe.incrby(counter_key, count)
    pipe.sadd(PENDING_CLICK_COUNTER_SET_KEY, short_code)
    pipe.expire(counter_key, CLICK_COUNTER_TTL_SECONDS)
    pipe.execute()


def _flush_single_click_counter(
    redis: Redis,
    *,
    short_code: str,
) -> dict[str, Any]:
    counter_key = link_click_counter_key(short_code)

    raw_count = redis.getdel(counter_key)

    if raw_count is None:
        redis.srem(PENDING_CLICK_COUNTER_SET_KEY, short_code)

        return {
            "short_code": short_code,
            "flushed": False,
            "count": 0,
            "reason": "counter_missing",
            "webhook_enqueued": False,
        }

    count = _redis_value_to_int(raw_count)

    if count is None or count <= 0:
        redis.srem(PENDING_CLICK_COUNTER_SET_KEY, short_code)

        return {
            "short_code": short_code,
            "flushed": False,
            "count": 0,
            "reason": "invalid_counter_value",
            "webhook_enqueued": False,
        }

    try:
        update_result = _run_async(
            _increment_link_click_count_by(
                short_code=short_code,
                count=count,
            ),
        )
    except SQLAlchemyError:
        _restore_pending_click_counter(
            redis,
            short_code=short_code,
            count=count,
        )
        raise

    if isinstance(update_result, bool):
        # Backward-compatible path for older tests/mocks.
        updated = update_result
        webhook_dispatch = None
    else:
        updated = bool(update_result["updated"])
        webhook_dispatch = update_result["webhook_dispatch"]

    if not updated:
        logger.warning(
            "Skipping click counter flush; link not found for short_code=%s",
            short_code,
        )
        redis.srem(PENDING_CLICK_COUNTER_SET_KEY, short_code)

        return {
            "short_code": short_code,
            "flushed": False,
            "count": count,
            "reason": "link_not_found",
            "webhook_enqueued": False,
        }

    webhook_enqueued = False

    if webhook_dispatch is not None:
        _enqueue_webhook_dispatch(webhook_dispatch)
        webhook_enqueued = True

    if redis.exists(counter_key):
        redis.sadd(PENDING_CLICK_COUNTER_SET_KEY, short_code)
    else:
        redis.srem(PENDING_CLICK_COUNTER_SET_KEY, short_code)

    return {
        "short_code": short_code,
        "flushed": True,
        "count": count,
        "reason": None,
        "webhook_enqueued": webhook_enqueued,
    }


def _flush_pending_click_counters(redis: Redis | None = None) -> dict[str, Any]:
    """
    Flush Redis click counters into PostgreSQL links.click_count.

    Uses Redis GETDEL so normal successful flushes do not double count.
    If the database update fails, the removed counter value is restored and the
    task is allowed to retry.

    Also enqueues click-threshold webhooks when a link crosses its configured
    webhook_threshold.
    """
    redis_client = redis or _sync_redis_client()
    short_codes = _get_pending_click_counter_short_codes(redis_client)

    flushed_links = 0
    flushed_clicks = 0
    skipped = 0
    webhooks_enqueued = 0
    results: list[dict[str, Any]] = []

    for short_code in short_codes:
        result = _flush_single_click_counter(
            redis_client,
            short_code=short_code,
        )
        results.append(result)

        if result["flushed"]:
            flushed_links += 1
            flushed_clicks += int(result["count"])
        else:
            skipped += 1

        if result.get("webhook_enqueued"):
            webhooks_enqueued += 1

    return {
        "processed_short_codes": len(short_codes),
        "flushed_links": flushed_links,
        "flushed_clicks": flushed_clicks,
        "skipped": skipped,
        "webhooks_enqueued": webhooks_enqueued,
        "results": results,
    }


@celery_app.task(
    bind=True,
    name="analytics.flush_click_counters",
    autoretry_for=(SQLAlchemyError, RedisError),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def flush_click_counters(_self: Any) -> dict[str, Any]:
    """
    Flush pending Redis click counters into PostgreSQL.

    This keeps the redirect path fast while making links.click_count
    eventually consistent.
    """
    result = _flush_pending_click_counters()

    logger.info(
        "Flushed Phase 3 click counters: links=%s clicks=%s skipped=%s webhooks=%s",
        result["flushed_links"],
        result["flushed_clicks"],
        result["skipped"],
        result["webhooks_enqueued"],
    )

    return result


@celery_app.task(
    bind=True,
    name="analytics.process_click_event",
    ignore_result=True,
    autoretry_for=(SQLAlchemyError, RedisError),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def process_click_event(
    _self: Any,
    *,
    short_code: str,
    clicked_at: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    referrer: str | None = None,
) -> dict[str, Any]:
    """
    Process a redirect click asynchronously for Phase 3 analytics.

    Responsibilities:
    - keep redirect path non-blocking
    - parse precise click timestamp
    - anonymize IP before persistence
    - parse User-Agent into browser, OS, and device type
    - lookup GeoIP country/city
    - persist one Click row in PostgreSQL
    - update lightweight Redis analytics counters

    Privacy:
    - raw IP is never stored in PostgreSQL
    - Redis stores only a hash of the anonymized IP in last_event
    """
    clicked_dt = _parse_clicked_at(clicked_at)
    day = clicked_dt.date().isoformat()

    ip_anonymized = anonymize_ip(ip_address)

    user_agent_info = _safe_parse_user_agent(user_agent)
    browser = _get_field(user_agent_info, "browser")
    os = _get_field(user_agent_info, "os")
    device_type = _get_field(user_agent_info, "device_type")

    geoip_info = _safe_lookup_geoip(ip_address)
    country = _get_field(geoip_info, "country")
    city = _get_field(geoip_info, "city")

    persistence_result = _run_async(
        _persist_click_event(
            short_code=short_code,
            clicked_at=clicked_dt,
            ip_anonymized=ip_anonymized,
            user_agent=user_agent,
            referrer=referrer,
            country=country,
            city=city,
            browser=browser,
            os=os,
            device_type=device_type,
        ),
    )

    persisted = bool(persistence_result["persisted"])

    try:
        _record_redis_analytics(
            short_code=short_code,
            clicked_at=clicked_dt,
            ip_anonymized=ip_anonymized,
            user_agent=user_agent,
            referrer=referrer,
            country=country,
            browser=browser,
            device_type=device_type,
            persisted=persisted,
        )
    except RedisError:
        logger.warning(
            "Failed to update Redis analytics counters for short_code=%s",
            short_code,
            exc_info=True,
        )

    logger.info(
        "Processed Phase 3 click analytics for short_code=%s persisted=%s",
        short_code,
        persisted,
    )

    return {
        "short_code": short_code,
        "clicked_at": clicked_dt.isoformat(),
        "day": day,
        "processed": True,
        "persisted": persisted,
        "link_id": persistence_result["link_id"],
        "click_id": persistence_result["click_id"],
        "country": country,
        "city": city,
        "browser": browser,
        "os": os,
        "device_type": device_type,
    }
