from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.link import Link
from app.models.user import User
from app.schemas.analytics import (
    BreakdownOut,
    CompareOut,
    CompareSeries,
    CountBucket,
    TimeseriesOut,
    TimeSeriesPoint,
)
from app.schemas.common import Envelope
from app.services.dashboard import (
    get_browser_breakdown,
    get_country_breakdown,
    get_link_id_for_owner,
    get_referrer_breakdown,
    get_timeseries,
    normalize_period,
)

router = APIRouter(prefix="/api/v1/analytics", tags=["Analytics Dashboard"])


_401 = {
    "description": "Missing or invalid API key",
    "content": {
        "application/json": {
            "example": {
                "data": None,
                "meta": {},
                "errors": [
                    {
                        "code": "unauthorized",
                        "message": "API key required. Pass it in the X-API-Key header.",
                    }
                ],
            }
        }
    },
}

_404 = {
    "description": "Link not found",
    "content": {
        "application/json": {
            "example": {
                "data": None,
                "meta": {},
                "errors": [{"code": "not_found", "message": "Link not found"}],
            }
        }
    },
}


def _fill_missing_days(
    rows: list[tuple[str, int]],
    *,
    days: int,
) -> list[TimeSeriesPoint]:
    """
    Ensure every day in the window is present, filling gaps with 0.
    Keeps the line chart continuous.
    """
    counts = dict(rows)
    today = datetime.now(UTC).date()

    points: list[TimeSeriesPoint] = []
    for offset in range(days - 1, -1, -1):
        day = (today - timedelta(days=offset)).isoformat()
        points.append(TimeSeriesPoint(date=day, clicks=counts.get(day, 0)))

    return points


async def _resolve_owned_link_id(
    db: AsyncSession,
    *,
    short_code: str,
    user_id: int,
) -> int:
    link_id = await get_link_id_for_owner(db, short_code=short_code, user_id=user_id)
    if link_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Link not found")
    return link_id


@router.get(
    "/compare",
    response_model=Envelope[CompareOut],
    summary="Multi-link comparison",
    description=(
        "Compare daily visits for multiple links on one chart. "
        "Pass `codes` as a comma-separated list of short codes you own. "
        "Max 10 links."
    ),
    responses={401: _401, 404: _404},
)
async def compare_links(
    codes: str = Query(
        ...,
        description="Comma-separated short codes, e.g. abc123,def456",
        examples=["abc123,def456"],
    ),
    days: int = Query(default=7, description="Window size: 7, 30, or 90"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Envelope[CompareOut]:
    period = normalize_period(days)

    raw_codes = [c.strip() for c in codes.split(",") if c.strip()]
    short_codes = list(dict.fromkeys(raw_codes))  # dedupe, preserve order

    if not short_codes:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No short codes provided")

    if len(short_codes) > 10:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "You can compare at most 10 links.",
        )

    owned = (
        await db.execute(
            select(Link.id, Link.short_code).where(
                Link.short_code.in_(short_codes),
                Link.user_id == user.id,
            )
        )
    ).all()

    owned_map = {row.short_code: row.id for row in owned}

    missing = [c for c in short_codes if c not in owned_map]
    if missing:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Link(s) not found: {', '.join(missing)}",
        )

    series: list[CompareSeries] = []
    for code in short_codes:
        rows = await get_timeseries(db, link_id=owned_map[code], days=period)
        points = _fill_missing_days(rows, days=period)
        series.append(
            CompareSeries(
                short_code=code,
                total=sum(p.clicks for p in points),
                points=points,
            )
        )

    return Envelope(data=CompareOut(period_days=period, series=series))


@router.get(
    "/{short_code}/timeseries",
    response_model=Envelope[TimeseriesOut],
    summary="Visits over time (line chart)",
    description=(
        "Daily click counts for the last **7 / 30 / 90** days. "
        "Missing days are filled with `0` so the chart stays continuous."
    ),
    responses={401: _401, 404: _404},
)
async def link_timeseries(
    short_code: str,
    days: int = Query(default=7, description="Window size: 7, 30, or 90"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Envelope[TimeseriesOut]:
    period = normalize_period(days)
    link_id = await _resolve_owned_link_id(db, short_code=short_code, user_id=user.id)

    rows = await get_timeseries(db, link_id=link_id, days=period)
    points = _fill_missing_days(rows, days=period)
    total = sum(p.clicks for p in points)

    return Envelope(
        data=TimeseriesOut(
            short_code=short_code,
            period_days=period,
            total=total,
            points=points,
        )
    )


@router.get(
    "/{short_code}/countries",
    response_model=Envelope[BreakdownOut],
    summary="Geographic breakdown by country",
    responses={401: _401, 404: _404},
)
async def link_countries(
    short_code: str,
    days: int | None = Query(default=None, description="Optional window: 7, 30, 90"),
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Envelope[BreakdownOut]:
    period = normalize_period(days) if days is not None else None
    link_id = await _resolve_owned_link_id(db, short_code=short_code, user_id=user.id)

    rows = await get_country_breakdown(db, link_id=link_id, days=period, limit=limit)
    items = [CountBucket(label=label, count=count) for label, count in rows]

    return Envelope(
        data=BreakdownOut(
            short_code=short_code,
            total=sum(i.count for i in items),
            items=items,
        )
    )


@router.get(
    "/{short_code}/referrers",
    response_model=Envelope[BreakdownOut],
    summary="Top referrers",
    responses={401: _401, 404: _404},
)
async def link_referrers(
    short_code: str,
    days: int | None = Query(default=None, description="Optional window: 7, 30, 90"),
    limit: int = Query(default=10, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Envelope[BreakdownOut]:
    period = normalize_period(days) if days is not None else None
    link_id = await _resolve_owned_link_id(db, short_code=short_code, user_id=user.id)

    rows = await get_referrer_breakdown(db, link_id=link_id, days=period, limit=limit)
    items = [CountBucket(label=label, count=count) for label, count in rows]

    return Envelope(
        data=BreakdownOut(
            short_code=short_code,
            total=sum(i.count for i in items),
            items=items,
        )
    )


@router.get(
    "/{short_code}/browsers",
    response_model=Envelope[BreakdownOut],
    summary="Top browsers",
    responses={401: _401, 404: _404},
)
async def link_browsers(
    short_code: str,
    days: int | None = Query(default=None, description="Optional window: 7, 30, 90"),
    limit: int = Query(default=10, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Envelope[BreakdownOut]:
    period = normalize_period(days) if days is not None else None
    link_id = await _resolve_owned_link_id(db, short_code=short_code, user_id=user.id)

    rows = await get_browser_breakdown(db, link_id=link_id, days=period, limit=limit)
    items = [CountBucket(label=label, count=count) for label, count in rows]

    return Envelope(
        data=BreakdownOut(
            short_code=short_code,
            total=sum(i.count for i in items),
            items=items,
        )
    )
