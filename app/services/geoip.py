"""Optional GeoIP lookup service for Phase 3 analytics.

The MaxMind GeoLite2 database is not committed to the repository.

Supported env vars:
- GEOIP_DATABASE_PATH
- GEOIP_DB_PATH

Default path:
- geoip/GeoLite2-City.mmdb

This module intentionally fails open. Missing database, missing geoip2 package,
invalid IPs, or lookup failures return empty country/city values.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from importlib import import_module
from pathlib import Path
from typing import Any

DEFAULT_GEOIP_DATABASE_PATH = "geoip/GeoLite2-City.mmdb"


@dataclass(frozen=True, slots=True)
class GeoIPLocation:
    country: str | None = None
    city: str | None = None


@lru_cache(maxsize=1)
def _get_geoip_reader(database_path: str) -> Any | None:
    db_path = Path(database_path)

    if not db_path.exists():
        return None

    try:
        geoip_database = import_module("geoip2.database")
    except ImportError:
        return None

    try:
        return geoip_database.Reader(str(db_path))
    except OSError:
        return None


def lookup_geoip_location(
    ip_address: str | None,
    *,
    database_path: str | None = None,
) -> GeoIPLocation:
    """Lookup country/city for an IP address."""

    if not ip_address:
        return GeoIPLocation()

    resolved_database_path = (
        database_path
        or os.getenv("GEOIP_DATABASE_PATH")
        or os.getenv("GEOIP_DB_PATH")
        or DEFAULT_GEOIP_DATABASE_PATH
    )

    reader = _get_geoip_reader(resolved_database_path)

    if reader is None:
        return GeoIPLocation()

    try:
        response: Any = reader.city(ip_address)
    except Exception:  # noqa: BLE001
        return GeoIPLocation()

    return GeoIPLocation(
        country=response.country.name,
        city=response.city.name,
    )


def lookup_geoip(
    ip_address: str | None,
    database_path: str | None = None,
) -> GeoIPLocation:
    """Backward-compatible alias used by app.tasks.analytics."""

    return lookup_geoip_location(ip_address, database_path=database_path)
