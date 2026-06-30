from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from redis.asyncio import Redis

from app.core.config import settings


@dataclass(slots=True)
class CachedLink:
    short_code: str
    long_url: str
    expires_at: datetime | None
    is_permanent: bool
    password_hash: str | None


def link_meta_key(short_code: str) -> str:
    return f"link:{short_code}:meta"


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None

    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)

    return value.astimezone(UTC)


def is_expired(expires_at: datetime | None) -> bool:
    expires_at = _as_utc(expires_at)

    if expires_at is None:
        return False

    return expires_at <= datetime.now(UTC)


def calculate_cache_ttl(
    expires_at: datetime | None,
    *,
    hot: bool = False,
) -> int:
    """
    Calculate Redis TTL for cached redirect metadata.

    Rules:
    - Normal links use DEFAULT_CACHE_TTL.
    - Hot links may use HOT_LINK_EXTENDED_TTL.
    - Expiring links must never be cached beyond expires_at.
    - Expired links return 0 and should not be cached.
    """
    base_ttl = settings.hot_link_extended_ttl if hot else settings.default_cache_ttl

    expires_at = _as_utc(expires_at)

    if expires_at is None:
        return int(base_ttl)

    remaining = int((expires_at - datetime.now(UTC)).total_seconds())

    if remaining <= 0:
        return 0

    return int(min(base_ttl, remaining))


def _serialize_datetime(value: datetime | None) -> str | None:
    value = _as_utc(value)

    if value is None:
        return None

    return value.isoformat()


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None

    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return _as_utc(parsed)


def serialize_link(link: Any) -> str:
    """
    Serialize only redirect-required fields.

    Important:
    - plaintext passwords are never cached
    - password_hash may be cached because Redis is internal infrastructure
      and unlock requires password verification
    """
    payload = {
        "short_code": link.short_code,
        "long_url": str(link.long_url),
        "expires_at": _serialize_datetime(link.expires_at),
        "is_permanent": bool(link.is_permanent),
        "password_hash": link.password_hash,
    }

    return json.dumps(payload, separators=(",", ":"))


def deserialize_link(raw: str) -> CachedLink:
    payload = json.loads(raw)

    return CachedLink(
        short_code=payload["short_code"],
        long_url=payload["long_url"],
        expires_at=_parse_datetime(payload.get("expires_at")),
        is_permanent=bool(payload.get("is_permanent", False)),
        password_hash=payload.get("password_hash"),
    )


async def get_cached_link(
    redis: Redis,
    short_code: str,
) -> CachedLink | None:
    raw = await redis.get(link_meta_key(short_code))

    if not raw:
        return None

    cached = deserialize_link(raw)

    if is_expired(cached.expires_at):
        await delete_cached_link(redis, short_code)
        return None

    return cached


async def set_cached_link(
    redis: Redis,
    link: Any,
    *,
    hot: bool = False,
) -> bool:
    ttl = calculate_cache_ttl(link.expires_at, hot=hot)

    if ttl <= 0:
        await delete_cached_link(redis, link.short_code)
        return False

    await redis.set(
        link_meta_key(link.short_code),
        serialize_link(link),
        ex=ttl,
    )

    return True


async def delete_cached_link(
    redis: Redis,
    short_code: str,
) -> None:
    await redis.delete(link_meta_key(short_code))
