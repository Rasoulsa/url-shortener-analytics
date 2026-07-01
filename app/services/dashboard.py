from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import String, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.click import Click
from app.models.link import Link

ALLOWED_PERIODS = (7, 30, 90)


def normalize_period(days: int) -> int:
    """Clamp requested window to an allowed value."""
    if days in ALLOWED_PERIODS:
        return days
    # pick nearest allowed period
    return min(ALLOWED_PERIODS, key=lambda p: abs(p - days))


def _window_start(days: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=days)


async def get_link_id_for_owner(
    db: AsyncSession,
    *,
    short_code: str,
    user_id: int,
) -> int | None:
    result = await db.execute(
        select(Link.id).where(
            Link.short_code == short_code,
            Link.user_id == user_id,
        ),
    )
    return result.scalar_one_or_none()


async def get_timeseries(
    db: AsyncSession,
    *,
    link_id: int,
    days: int,
) -> list[tuple[str, int]]:
    """
    Return [(date_iso, count), ...] for the last `days` days.

    Uses date_trunc('day', clicked_at) so gaps (days with 0 clicks) are simply
    absent; the API layer fills missing days with 0.
    """
    start = _window_start(days)

    day_col = func.date_trunc("day", Click.clicked_at)

    stmt = (
        select(day_col.label("day"), func.count().label("hits"))
        .where(Click.link_id == link_id, Click.clicked_at >= start)
        .group_by(day_col)
        .order_by(day_col.asc())
    )

    rows = (await db.execute(stmt)).all()

    return [(row.day.date().isoformat(), int(row.hits)) for row in rows]


async def _grouped_counts(
    db: AsyncSession,
    *,
    link_id: int,
    column,
    days: int | None,
    limit: int,
    empty_label: str,
) -> list[tuple[str, int]]:
    label_col = func.coalesce(
        column,
        literal(empty_label, type_=String),
    ).label("label")

    stmt = select(label_col, func.count().label("hits")).where(
        Click.link_id == link_id,
    )

    if days is not None:
        stmt = stmt.where(Click.clicked_at >= _window_start(days))

    stmt = stmt.group_by(label_col).order_by(func.count().desc()).limit(limit)

    rows = (await db.execute(stmt)).all()
    return [(str(row.label), int(row.hits)) for row in rows]


async def get_country_breakdown(
    db: AsyncSession,
    *,
    link_id: int,
    days: int | None = None,
    limit: int = 50,
) -> list[tuple[str, int]]:
    return await _grouped_counts(
        db,
        link_id=link_id,
        column=Click.country,
        days=days,
        limit=limit,
        empty_label="Unknown",
    )


async def get_referrer_breakdown(
    db: AsyncSession,
    *,
    link_id: int,
    days: int | None = None,
    limit: int = 10,
) -> list[tuple[str, int]]:
    return await _grouped_counts(
        db,
        link_id=link_id,
        column=Click.referrer,
        days=days,
        limit=limit,
        empty_label="Direct / None",
    )


async def get_browser_breakdown(
    db: AsyncSession,
    *,
    link_id: int,
    days: int | None = None,
    limit: int = 10,
) -> list[tuple[str, int]]:
    return await _grouped_counts(
        db,
        link_id=link_id,
        column=Click.browser,
        days=days,
        limit=limit,
        empty_label="Unknown",
    )
