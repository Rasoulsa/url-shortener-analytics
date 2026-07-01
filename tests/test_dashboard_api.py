from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.dashboard import (
    _window_start,
    get_browser_breakdown,
    get_country_breakdown,
    get_referrer_breakdown,
    get_timeseries,
    normalize_period,
)

# ---------------------------------------------------------------------------
# normalize_period
# ---------------------------------------------------------------------------


def test_normalize_period_exact_values() -> None:
    assert normalize_period(7) == 7
    assert normalize_period(30) == 30
    assert normalize_period(90) == 90


def test_normalize_period_clamps_to_nearest() -> None:
    assert normalize_period(1) == 7  # closest to 7
    assert normalize_period(15) == 7  # equidistant 7/30 → min() picks 7
    assert normalize_period(20) == 30  # closest to 30
    assert normalize_period(60) == 30  # equidistant 30/90 → min() picks 30
    assert normalize_period(200) == 90  # beyond max → 90


def test_normalize_period_boundary() -> None:
    assert normalize_period(0) == 7
    assert normalize_period(50) == 30  # |50-30|=20 < |50-90|=40
    assert normalize_period(91) == 90  # just above 90 → clamps to 90


# ---------------------------------------------------------------------------
# _window_start
# ---------------------------------------------------------------------------


def test_window_start_is_in_the_past() -> None:
    now = datetime.now(UTC)
    start = _window_start(7)
    assert start < now
    # Should be roughly 7 days ago (within 5 seconds of margin)
    delta = now - start
    assert timedelta(days=6, hours=23, minutes=55) < delta < timedelta(days=7, seconds=5)


# ---------------------------------------------------------------------------
# Helper: build a fake AsyncSession whose execute() returns given rows
# ---------------------------------------------------------------------------


def _make_db(rows: list[Any]) -> AsyncMock:
    result_mock = MagicMock()
    result_mock.all.return_value = rows
    result_mock.scalar_one_or_none.return_value = None

    db = AsyncMock()
    db.execute.return_value = result_mock
    return db


# ---------------------------------------------------------------------------
# get_timeseries
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_timeseries_returns_list_of_tuples() -> None:
    # Simulate two rows coming back from the DB
    row1 = MagicMock()
    row1.day = datetime(2026, 6, 30, tzinfo=UTC)
    row1.hits = 5

    row2 = MagicMock()
    row2.day = datetime(2026, 7, 1, tzinfo=UTC)
    row2.hits = 3

    db = _make_db([row1, row2])

    result = await get_timeseries(db, link_id=1, days=7)

    assert result == [("2026-06-30", 5), ("2026-07-01", 3)]


@pytest.mark.asyncio
async def test_get_timeseries_empty_returns_empty_list() -> None:
    db = _make_db([])
    result = await get_timeseries(db, link_id=99, days=7)
    assert result == []


@pytest.mark.asyncio
async def test_get_timeseries_calls_execute_once() -> None:
    db = _make_db([])
    await get_timeseries(db, link_id=1, days=30)
    db.execute.assert_awaited_once()


# ---------------------------------------------------------------------------
# get_country_breakdown
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_country_breakdown_returns_label_count_tuples() -> None:
    row = MagicMock()
    row.label = "US"
    row.hits = 42

    db = _make_db([row])
    result = await get_country_breakdown(db, link_id=1)

    assert result == [("US", 42)]


@pytest.mark.asyncio
async def test_get_country_breakdown_unknown_fallback() -> None:
    # When country is None the coalesce produces "Unknown" — simulate that
    row = MagicMock()
    row.label = "Unknown"
    row.hits = 7

    db = _make_db([row])
    result = await get_country_breakdown(db, link_id=1)

    assert result[0] == ("Unknown", 7)


# ---------------------------------------------------------------------------
# get_referrer_breakdown
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_referrer_breakdown_direct_none_label() -> None:
    row = MagicMock()
    row.label = "Direct / None"
    row.hits = 9

    db = _make_db([row])
    result = await get_referrer_breakdown(db, link_id=1)

    assert result == [("Direct / None", 9)]


@pytest.mark.asyncio
async def test_get_referrer_breakdown_real_referrer() -> None:
    row = MagicMock()
    row.label = "https://google.com"
    row.hits = 15

    db = _make_db([row])
    result = await get_referrer_breakdown(db, link_id=1)

    assert result == [("https://google.com", 15)]


# ---------------------------------------------------------------------------
# get_browser_breakdown
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_browser_breakdown_returns_sorted_by_hits() -> None:
    chrome = MagicMock()
    chrome.label = "Chrome"
    chrome.hits = 100

    firefox = MagicMock()
    firefox.label = "Firefox"
    firefox.hits = 40

    # DB already returns sorted (ORDER BY hits DESC), simulate that
    db = _make_db([chrome, firefox])
    result = await get_browser_breakdown(db, link_id=1)

    assert result[0] == ("Chrome", 100)
    assert result[1] == ("Firefox", 40)


@pytest.mark.asyncio
async def test_get_browser_breakdown_empty() -> None:
    db = _make_db([])
    result = await get_browser_breakdown(db, link_id=1)
    assert result == []


# ---------------------------------------------------------------------------
# _fill_missing_days (router helper — test via import)
# ---------------------------------------------------------------------------


def test_fill_missing_days_fills_gaps() -> None:
    from app.api.v1.analytics_dashboard import _fill_missing_days

    today = datetime.now(UTC).date()
    yesterday = (today - timedelta(days=1)).isoformat()
    today_iso = today.isoformat()

    # Only today has data
    rows = [(today_iso, 5)]
    points = _fill_missing_days(rows, days=3)

    assert len(points) == 3
    # Last point is today
    assert points[-1].date == today_iso
    assert points[-1].clicks == 5
    # Second-to-last is yesterday with 0
    assert points[-2].date == yesterday
    assert points[-2].clicks == 0


def test_fill_missing_days_all_zeros_when_no_data() -> None:
    from app.api.v1.analytics_dashboard import _fill_missing_days

    points = _fill_missing_days([], days=7)
    assert len(points) == 7
    assert all(p.clicks == 0 for p in points)


def test_fill_missing_days_correct_length() -> None:
    from app.api.v1.analytics_dashboard import _fill_missing_days

    for period in (7, 30, 90):
        points = _fill_missing_days([], days=period)
        assert len(points) == period, f"Expected {period} points for days={period}"


def test_fill_missing_days_dates_are_consecutive() -> None:
    from app.api.v1.analytics_dashboard import _fill_missing_days

    points = _fill_missing_days([], days=7)
    dates = [date.fromisoformat(p.date) for p in points]

    for i in range(1, len(dates)):
        assert dates[i] - dates[i - 1] == timedelta(days=1)
