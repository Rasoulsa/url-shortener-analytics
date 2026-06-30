from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any, cast

from redis.asyncio import Redis

# Atomic sliding-window rate limit using a Redis sorted set.
#
# KEYS[1] = rate limit key
# ARGV[1] = now_ms
# ARGV[2] = window_ms
# ARGV[3] = limit
# ARGV[4] = unique member
#
# Returns: {allowed (0/1), remaining, ttl_ms}
SLIDING_WINDOW_LUA = """
local key = KEYS[1]
local now_ms = tonumber(ARGV[1])
local window_ms = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]

local cutoff = now_ms - window_ms

redis.call("ZREMRANGEBYSCORE", key, 0, cutoff)

local current_count = redis.call("ZCARD", key)

if current_count >= limit then
    local ttl_ms = redis.call("PTTL", key)
    if ttl_ms < 0 then
        redis.call("PEXPIRE", key, window_ms)
        ttl_ms = window_ms
    end
    return {0, 0, ttl_ms}
end

redis.call("ZADD", key, now_ms, member)
redis.call("PEXPIRE", key, window_ms)

local new_count = redis.call("ZCARD", key)
local remaining = limit - new_count
local ttl_ms = redis.call("PTTL", key)

return {1, remaining, ttl_ms}
"""


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    retry_after_seconds: int


async def check_rate_limit(
    redis_client: Redis,
    *,
    key: str,
    limit: int,
    window_seconds: int,
) -> RateLimitResult:
    """
    Check a Redis-backed sliding-window rate limit.

    Fails open (allows the request) if Redis is unavailable so that
    a Redis outage does not take down the whole API.
    """
    now_ms = int(time.time() * 1000)
    window_ms = window_seconds * 1000
    member = f"{now_ms}:{uuid.uuid4()}"

    try:
        raw_result = await redis_client.eval(
            SLIDING_WINDOW_LUA,
            1,
            key,
            now_ms,
            window_ms,
            limit,
            member,
        )
    except Exception:
        return RateLimitResult(
            allowed=True,
            limit=limit,
            remaining=limit,
            retry_after_seconds=0,
        )

    result = cast(list[Any], raw_result)

    allowed = bool(int(result[0]))
    remaining = max(int(result[1]), 0)
    ttl_ms = max(int(result[2]), 0)

    if allowed:
        retry_after_seconds = 0
    else:
        retry_after_seconds = max((ttl_ms + 999) // 1000, 1)

    return RateLimitResult(
        allowed=allowed,
        limit=limit,
        remaining=remaining,
        retry_after_seconds=retry_after_seconds,
    )
