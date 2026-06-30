from __future__ import annotations

from datetime import UTC, datetime

from app.services.analytics_enrichment import (
    anonymize_ip,
    enrich_click_analytics,
    normalize_referrer,
    parse_user_agent,
    utc_now,
)
from app.services.geoip import lookup_geoip, lookup_geoip_location
from app.services.privacy import anonymize_ip as privacy_anonymize_ip
from app.services.user_agent import parse_user_agent as legacy_parse_user_agent


def test_utc_now_returns_timezone_aware_utc_datetime() -> None:
    timestamp = utc_now()

    assert timestamp.tzinfo is not None
    assert timestamp.utcoffset() == UTC.utcoffset(timestamp)


def test_anonymize_ipv4_zeroes_last_octet() -> None:
    assert anonymize_ip("203.0.113.45") == "203.0.113.0"


def test_anonymize_ipv4_strips_whitespace() -> None:
    assert anonymize_ip(" 198.51.100.25 ") == "198.51.100.0"


def test_anonymize_ipv6_uses_48_bit_network() -> None:
    assert anonymize_ip("2001:db8:abcd:0012::1") == "2001:db8:abcd::"


def test_anonymize_missing_ip_returns_none() -> None:
    assert anonymize_ip(None) is None
    assert anonymize_ip("") is None
    assert anonymize_ip("   ") is None


def test_anonymize_invalid_ip_returns_none() -> None:
    assert anonymize_ip("not-an-ip") is None


def test_parse_chrome_macos_desktop_user_agent() -> None:
    user_agent = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    )

    parsed = parse_user_agent(user_agent)

    assert parsed.browser == "Chrome"
    assert parsed.os == "macOS"
    assert parsed.device_type == "desktop"


def test_parse_edge_windows_desktop_user_agent() -> None:
    user_agent = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0"
    )

    parsed = parse_user_agent(user_agent)

    assert parsed.browser == "Edge"
    assert parsed.os == "Windows"
    assert parsed.device_type == "desktop"


def test_parse_firefox_linux_desktop_user_agent() -> None:
    user_agent = "Mozilla/5.0 (X11; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0"

    parsed = parse_user_agent(user_agent)

    assert parsed.browser == "Firefox"
    assert parsed.os == "Linux"
    assert parsed.device_type == "desktop"


def test_parse_mobile_safari_ios_user_agent() -> None:
    user_agent = (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/17.5 Mobile/15E148 Safari/604.1"
    )

    parsed = parse_user_agent(user_agent)

    assert parsed.browser == "Safari"
    assert parsed.os == "iOS"
    assert parsed.device_type == "mobile"


def test_parse_android_mobile_chrome_user_agent() -> None:
    user_agent = (
        "Mozilla/5.0 (Linux; Android 14; Pixel 8) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Mobile Safari/537.36"
    )

    parsed = parse_user_agent(user_agent)

    assert parsed.browser == "Chrome"
    assert parsed.os == "Android"
    assert parsed.device_type == "mobile"


def test_parse_tablet_user_agent() -> None:
    user_agent = (
        "Mozilla/5.0 (iPad; CPU OS 17_5 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/17.5 Mobile/15E148 Safari/604.1"
    )

    parsed = parse_user_agent(user_agent)

    assert parsed.browser == "Safari"
    assert parsed.os == "iOS"
    assert parsed.device_type == "tablet"


def test_parse_bot_user_agent() -> None:
    parsed = parse_user_agent("Googlebot/2.1 (+http://www.google.com/bot.html)")

    assert parsed.browser == "Bot"
    assert parsed.os is None
    assert parsed.device_type == "bot"


def test_parse_missing_user_agent_returns_unknown_device() -> None:
    parsed = parse_user_agent(None)

    assert parsed.browser is None
    assert parsed.os is None
    assert parsed.device_type == "unknown"


def test_parse_blank_user_agent_returns_unknown_device() -> None:
    parsed = parse_user_agent("   ")

    assert parsed.browser is None
    assert parsed.os is None
    assert parsed.device_type == "unknown"


def test_normalize_referrer_accepts_http_and_https_urls() -> None:
    assert normalize_referrer("https://example.com/page") == "https://example.com/page"
    assert normalize_referrer("http://example.com/page") == "http://example.com/page"


def test_normalize_referrer_strips_whitespace() -> None:
    assert normalize_referrer("  https://example.com/page  ") == "https://example.com/page"


def test_normalize_referrer_rejects_empty_values() -> None:
    assert normalize_referrer(None) is None
    assert normalize_referrer("") is None
    assert normalize_referrer("   ") is None


def test_normalize_referrer_rejects_non_http_urls() -> None:
    assert normalize_referrer("javascript:alert(1)") is None
    assert normalize_referrer("ftp://example.com/file") is None
    assert normalize_referrer("not-a-url") is None


def test_normalize_referrer_truncates_long_values() -> None:
    referrer = "https://example.com/" + ("a" * 3000)

    normalized = normalize_referrer(referrer)

    assert normalized is not None
    assert len(normalized) == 2048


def test_enrich_click_analytics_without_geoip() -> None:
    clicked_at = datetime(2026, 6, 30, 12, 30, tzinfo=UTC)
    user_agent = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    )

    enriched = enrich_click_analytics(
        ip_address="203.0.113.45",
        user_agent=user_agent,
        referrer="https://referrer.example/path",
        clicked_at=clicked_at,
        enable_geoip=False,
    )

    assert enriched.clicked_at == clicked_at
    assert enriched.ip_anonymized == "203.0.113.0"
    assert enriched.user_agent == user_agent
    assert enriched.browser == "Chrome"
    assert enriched.os == "macOS"
    assert enriched.device_type == "desktop"
    assert enriched.referrer == "https://referrer.example/path"
    assert enriched.country is None
    assert enriched.city is None


def test_enrich_click_analytics_handles_missing_values() -> None:
    enriched = enrich_click_analytics(
        ip_address=None,
        user_agent=None,
        referrer=None,
        enable_geoip=False,
    )

    assert enriched.clicked_at.tzinfo is not None
    assert enriched.ip_anonymized is None
    assert enriched.user_agent is None
    assert enriched.browser is None
    assert enriched.os is None
    assert enriched.device_type == "unknown"
    assert enriched.referrer is None
    assert enriched.country is None
    assert enriched.city is None


def test_geoip_lookup_returns_empty_location_when_database_missing() -> None:
    location = lookup_geoip_location(
        "8.8.8.8",
        database_path="/missing/GeoLite2-City.mmdb",
    )

    assert location.country is None
    assert location.city is None


def test_geoip_lookup_returns_empty_location_when_ip_missing() -> None:
    location = lookup_geoip_location(
        None,
        database_path="/missing/GeoLite2-City.mmdb",
    )

    assert location.country is None
    assert location.city is None


def test_privacy_wrapper_uses_canonical_anonymizer() -> None:
    assert privacy_anonymize_ip("203.0.113.45") == "203.0.113.0"


def test_user_agent_wrapper_uses_canonical_parser() -> None:
    parsed = legacy_parse_user_agent(
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    )

    assert parsed.browser == "Chrome"
    assert parsed.os == "Windows"
    assert parsed.device_type == "desktop"


def test_lookup_geoip_alias_matches_location_api_when_database_missing() -> None:
    location_from_alias = lookup_geoip(
        "8.8.8.8",
        database_path="/missing/GeoLite2-City.mmdb",
    )
    location_from_canonical = lookup_geoip_location(
        "8.8.8.8",
        database_path="/missing/GeoLite2-City.mmdb",
    )

    assert location_from_alias == location_from_canonical
    assert location_from_alias.country is None
    assert location_from_alias.city is None
