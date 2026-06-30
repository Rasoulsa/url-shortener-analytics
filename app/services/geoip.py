from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import geoip2.database
from geoip2.errors import AddressNotFoundError

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GeoIPResult:
    country: str | None
    city: str | None


_reader: geoip2.database.Reader | None = None
_reader_path: str | None = None


def _get_reader() -> geoip2.database.Reader | None:
    global _reader
    global _reader_path

    db_path = settings.geoip_db_path

    if _reader is not None and _reader_path == db_path:
        return _reader

    path = Path(db_path)

    if not path.exists():
        logger.debug("GeoIP database not found at %s", db_path)
        return None

    try:
        _reader = geoip2.database.Reader(str(path))
        _reader_path = db_path
        return _reader
    except Exception:
        logger.warning("Failed to open GeoIP database at %s", db_path, exc_info=True)
        return None


def lookup_geoip(ip_address: str | None) -> GeoIPResult:
    if not ip_address:
        return GeoIPResult(country=None, city=None)

    reader = _get_reader()

    if reader is None:
        return GeoIPResult(country=None, city=None)

    try:
        response = reader.city(ip_address)
        return GeoIPResult(
            country=response.country.name,
            city=response.city.name,
        )
    except AddressNotFoundError:
        return GeoIPResult(country=None, city=None)
    except Exception:
        logger.debug("GeoIP lookup failed for %s", ip_address, exc_info=True)
        return GeoIPResult(country=None, city=None)
