from __future__ import annotations

from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError

PENDING_CLICK_COUNTER_SET_KEY = "analytics:click_counters:pending"
CLICK_COUNTER_TTL_SECONDS = 7 * 24 * 60 * 60


def link_click_counter_key(short_code: str) -> str:
    return f"link:{short_code}:clicks"


async def increment_link_click_counter(
    redis: Redis,
    short_code: str,
    *,
    ttl_seconds: int = CLICK_COUNTER_TTL_SECONDS,
) -> int | None:
    short_code = short_code.strip()

    if not short_code:
        return None

    key = link_click_counter_key(short_code)

    try:
        pipe = redis.pipeline(transaction=True)
        pipe.incr(key)
        pipe.sadd(PENDING_CLICK_COUNTER_SET_KEY, short_code)
        pipe.expire(key, ttl_seconds)

        results: list[Any] = await pipe.execute()
    except RedisError:
        return None

    return int(results[0])
