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
from app.services.geoip import lookup_geoip
from app.services.privacy import anonymize_ip
from app.services.user_agent import parse_user_agent
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


@celery_app.task(
    bind=True,
    name="analytics.process_click_event",
    autoretry_for=(SQLAlchemyError,),
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
