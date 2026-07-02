from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from app.api.v1.analytics_dashboard import _fill_missing_days
from app.services.dashboard import _window_start, normalize_period

# ── normalize_period ────────────────────────────────────────────────────────


def test_normalize_period_accepts_supported_values() -> None:
    assert normalize_period(7) == 7
    assert normalize_period(30) == 30
    assert normalize_period(90) == 90


def test_normalize_period_clamps_to_nearest() -> None:
    assert normalize_period(1) == 7
    assert normalize_period(15) == 7
    assert normalize_period(20) == 30
    assert normalize_period(50) == 30
    assert normalize_period(60) == 30  # equidistant 30/90 → min() picks 30
    assert normalize_period(200) == 90


# ── _window_start ───────────────────────────────────────────────────────────


def test_window_start_is_tz_aware_utc() -> None:
    start = _window_start(7)

    assert start.tzinfo is not None
    assert start.utcoffset() == UTC.utcoffset(start)


def test_window_start_is_roughly_n_days_ago() -> None:
    now = datetime.now(UTC)
    start = _window_start(7)
    delta = now - start

    assert timedelta(days=6, hours=23, minutes=59) < delta < timedelta(days=7, seconds=5)


# ── _fill_missing_days ──────────────────────────────────────────────────────


def test_fill_missing_days_returns_requested_count() -> None:
    assert len(_fill_missing_days([], days=7)) == 7
    assert len(_fill_missing_days([], days=30)) == 30
    assert len(_fill_missing_days([], days=90)) == 90


def test_fill_missing_days_zeros_when_no_data() -> None:
    points = _fill_missing_days([], days=7)
    assert all(p.clicks == 0 for p in points)


def test_fill_missing_days_preserves_existing_counts() -> None:
    today = datetime.now(UTC).date().isoformat()
    points = _fill_missing_days([(today, 9)], days=7)

    assert points[-1].date == today
    assert points[-1].clicks == 9


def test_fill_missing_days_dates_are_consecutive_ascending() -> None:
    points = _fill_missing_days([], days=7)
    dates = [date.fromisoformat(p.date) for p in points]

    assert dates == sorted(dates)
    for i in range(1, len(dates)):
        assert dates[i] - dates[i - 1] == timedelta(days=1)
