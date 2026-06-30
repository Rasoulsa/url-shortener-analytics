"""Phase 3 click analytics enrichment helpers.

Responsibilities:
- precise UTC timestamp
- IP anonymization
- User-Agent browser/OS parsing
- device type classification
- referrer normalization
- optional GeoIP country/city lookup

This module does not write to the database.
Persistence belongs to the click-recording/Celery task.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import urlparse

from app.services.geoip import GeoIPLocation, lookup_geoip_location

DeviceType = Literal["mobile", "desktop", "tablet", "bot", "unknown"]


@dataclass(frozen=True, slots=True)
class UserAgentInfo:
    browser: str | None
    os: str | None
    device_type: DeviceType


@dataclass(frozen=True, slots=True)
class EnrichedClickAnalytics:
    clicked_at: datetime
    ip_anonymized: str | None
    user_agent: str | None
    browser: str | None
    os: str | None
    device_type: DeviceType
    referrer: str | None
    country: str | None
    city: str | None


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(UTC)


def anonymize_ip(ip_address: str | None) -> str | None:
    """Anonymize an IP address before storage.

    IPv4:
        203.0.113.45 -> 203.0.113.0

    IPv6:
        Uses /48 network anonymization:
        2001:db8:abcd:0012::1 -> 2001:db8:abcd::

    Missing or invalid IP returns None.
    """

    if not ip_address:
        return None

    cleaned_ip = ip_address.strip()

    if not cleaned_ip:
        return None

    try:
        parsed_ip = ipaddress.ip_address(cleaned_ip)
    except ValueError:
        return None

    if isinstance(parsed_ip, ipaddress.IPv4Address):
        network = ipaddress.ip_network(f"{parsed_ip}/24", strict=False)
        return str(network.network_address)

    network = ipaddress.ip_network(f"{parsed_ip}/48", strict=False)
    return str(network.network_address)


def normalize_referrer(referrer: str | None, *, max_length: int = 2048) -> str | None:
    """Normalize incoming referrer URL.

    Rules:
    - missing/blank referrer -> None
    - only http/https referrers are accepted
    - invalid URL-like values -> None
    - long values are truncated defensively
    """

    if not referrer:
        return None

    cleaned_referrer = referrer.strip()

    if not cleaned_referrer:
        return None

    parsed_referrer = urlparse(cleaned_referrer)

    if parsed_referrer.scheme not in {"http", "https"}:
        return None

    if not parsed_referrer.netloc:
        return None

    return cleaned_referrer[:max_length]


def parse_user_agent(user_agent: str | None) -> UserAgentInfo:
    """Extract browser, OS, and device type from a User-Agent string."""

    if not user_agent:
        return UserAgentInfo(browser=None, os=None, device_type="unknown")

    normalized_user_agent = user_agent.strip().lower()

    if not normalized_user_agent:
        return UserAgentInfo(browser=None, os=None, device_type="unknown")

    return UserAgentInfo(
        browser=_detect_browser(normalized_user_agent),
        os=_detect_os(normalized_user_agent),
        device_type=_detect_device_type(normalized_user_agent),
    )


def enrich_click_analytics(
    *,
    ip_address: str | None,
    user_agent: str | None,
    referrer: str | None,
    clicked_at: datetime | None = None,
    enable_geoip: bool = True,
    geoip_database_path: str | None = None,
) -> EnrichedClickAnalytics:
    """Build a full enriched click analytics payload.

    Important:
    - raw IP is used only for optional GeoIP lookup
    - only anonymized IP should be persisted
    - this function performs no database writes
    """

    user_agent_info = parse_user_agent(user_agent)

    geoip_location = (
        lookup_geoip_location(ip_address, database_path=geoip_database_path)
        if enable_geoip
        else GeoIPLocation()
    )

    return EnrichedClickAnalytics(
        clicked_at=clicked_at or utc_now(),
        ip_anonymized=anonymize_ip(ip_address),
        user_agent=user_agent,
        browser=user_agent_info.browser,
        os=user_agent_info.os,
        device_type=user_agent_info.device_type,
        referrer=normalize_referrer(referrer),
        country=geoip_location.country,
        city=geoip_location.city,
    )


def _detect_browser(user_agent: str) -> str | None:
    if _is_bot_user_agent(user_agent):
        return "Bot"

    if "edg/" in user_agent or "edge/" in user_agent:
        return "Edge"

    if "opr/" in user_agent or "opera" in user_agent:
        return "Opera"

    if "firefox/" in user_agent or "fxios/" in user_agent:
        return "Firefox"

    if "chrome/" in user_agent or "crios/" in user_agent:
        return "Chrome"

    if "safari/" in user_agent:
        return "Safari"

    if "msie" in user_agent or "trident/" in user_agent:
        return "Internet Explorer"

    return None


def _detect_os(user_agent: str) -> str | None:
    if "windows nt" in user_agent:
        return "Windows"

    if "android" in user_agent:
        return "Android"

    if "iphone" in user_agent or "ipad" in user_agent or "ipod" in user_agent:
        return "iOS"

    if "mac os x" in user_agent or "macintosh" in user_agent:
        return "macOS"

    if "linux" in user_agent or "x11" in user_agent:
        return "Linux"

    return None


def _detect_device_type(user_agent: str) -> DeviceType:
    if _is_bot_user_agent(user_agent):
        return "bot"

    if "ipad" in user_agent or "tablet" in user_agent or "kindle" in user_agent:
        return "tablet"

    if "mobile" in user_agent or "iphone" in user_agent:
        return "mobile"

    if "android" in user_agent:
        if "mobile" in user_agent:
            return "mobile"
        return "tablet"

    if (
        "windows nt" in user_agent
        or "macintosh" in user_agent
        or "mac os x" in user_agent
        or "linux" in user_agent
        or "x11" in user_agent
    ):
        return "desktop"

    return "unknown"


def _is_bot_user_agent(user_agent: str) -> bool:
    bot_markers = (
        "bot",
        "crawler",
        "spider",
        "slurp",
        "bingpreview",
        "facebookexternalhit",
        "whatsapp",
        "telegrambot",
        "discordbot",
        "linkedinbot",
        "preview",
    )

    return any(marker in user_agent for marker in bot_markers)
