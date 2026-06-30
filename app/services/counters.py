from __future__ import annotations

from redis.asyncio import Redis
from redis.exceptions import RedisError

CLICK_COUNTER_TTL_SECONDS = 7 * 24 * 60 * 60


def link_click_counter_key(short_code: str) -> str:
    return f"link:{short_code}:clicks"


async def increment_link_click_counter(
    redis: Redis,
    short_code: str,
    *,
    ttl_seconds: int = CLICK_COUNTER_TTL_SECONDS,
) -> int | None:
    """
    Increment the Redis click counter for a link.

    Returns:
        Current counter value on success.
        None if Redis is unavailable or the increment fails.

    Redis key:
        link:{short_code}:clicks

    Notes:
        The TTL prevents stale counter keys from living forever if a link is
        deleted or if Celery flushing is temporarily disabled.
    """
    key = link_click_counter_key(short_code)

    try:
        value = await redis.incr(key)
        await redis.expire(key, ttl_seconds)
    except RedisError:
        return None

    return int(value)


async def get_link_click_counter(
    redis: Redis,
    short_code: str,
) -> int:
    key = link_click_counter_key(short_code)

    value = await redis.get(key)
    if value is None:
        return 0

    if isinstance(value, bytes):
        value = value.decode("utf-8")

    return int(value)


async def delete_link_click_counter(
    redis: Redis,
    short_code: str,
) -> None:
    await redis.delete(link_click_counter_key(short_code))
