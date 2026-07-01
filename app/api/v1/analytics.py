from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.schemas.common import Envelope, meta_from
from app.services.analytics_stats import (
    AnalyticsDimension,
    get_link_breakdown,
    get_link_overview,
    get_link_timeseries,
    get_user_analytics_overview,
    normalize_date_range,
)

router = APIRouter(prefix="/api/v1/analytics", tags=["Analytics"])


def _user_id(current_user: Any) -> int:
    return int(current_user.id)


def _envelope(data: Any, meta: dict[str, Any] | None = None) -> Envelope[Any]:
    """Wrap analytics payloads in the shared canonical Envelope.

    Analytics data shapes are heterogeneous (overview object, timeseries
    list, breakdown list), so the generic parameter is Any — but the outer
    {data, meta, errors} contract is identical to every other endpoint.
    """
    return Envelope(data=data, meta=meta_from(**meta) if meta else None)


@router.get(
    "/overview",
    response_model=Envelope[Any],
    summary="User analytics overview",
    description=(
        "Aggregate analytics for all links owned by the authenticated user. "
        "Defaults to the last 30 days. Override with `from` / `to` / `days`."
    ),
)
async def analytics_overview(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[Any, Depends(get_current_user)],
    from_: Annotated[
        datetime | None,
        Query(alias="from", description="Start datetime, ISO-8601"),
    ] = None,
    to: Annotated[
        datetime | None,
        Query(description="End datetime, ISO-8601"),
    ] = None,
    days: Annotated[
        int,
        Query(ge=1, le=365, description="Rolling window in days (default 30)"),
    ] = 30,
) -> Envelope[Any]:
    """Phase 4 analytics overview for all links owned by the authenticated user."""
    start, end = normalize_date_range(from_=from_, to=to, days=days)

    data = await get_user_analytics_overview(
        db=db,
        user_id=_user_id(current_user),
        from_=start,
        to=end,
    )

    return _envelope(
        data=data,
        meta={
            "from": start.isoformat(),
            "to": end.isoformat(),
            "days": days,
        },
    )


@router.get(
    "/links/{short_code}/overview",
    response_model=Envelope[Any],
    summary="Per-link analytics overview",
    description="Aggregate analytics for a single link identified by its short code.",
)
async def link_analytics_overview(
    short_code: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[Any, Depends(get_current_user)],
    from_: Annotated[
        datetime | None,
        Query(alias="from", description="Start datetime, ISO-8601"),
    ] = None,
    to: Annotated[
        datetime | None,
        Query(description="End datetime, ISO-8601"),
    ] = None,
    days: Annotated[
        int,
        Query(ge=1, le=365, description="Rolling window in days (default 30)"),
    ] = 30,
) -> Envelope[Any]:
    """Phase 4 per-link analytics overview."""
    start, end = normalize_date_range(from_=from_, to=to, days=days)

    data = await get_link_overview(
        db=db,
        short_code=short_code,
        user_id=_user_id(current_user),
        from_=start,
        to=end,
    )

    return _envelope(
        data=data,
        meta={
            "short_code": short_code,
            "from": start.isoformat(),
            "to": end.isoformat(),
            "days": days,
        },
    )


@router.get(
    "/links/{short_code}/timeseries",
    response_model=Envelope[Any],
    summary="Per-link click time series",
    description=(
        "Returns daily click counts for the given link over the requested window. "
        "Used by the dashboard line chart (7 / 30 / 90 day presets)."
    ),
)
async def link_analytics_timeseries(
    short_code: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[Any, Depends(get_current_user)],
    from_: Annotated[
        datetime | None,
        Query(alias="from", description="Start datetime, ISO-8601"),
    ] = None,
    to: Annotated[
        datetime | None,
        Query(description="End datetime, ISO-8601"),
    ] = None,
    days: Annotated[
        int,
        Query(
            ge=1,
            le=365,
            description="Rolling window in days (default 30). Use 7, 30, or 90 for dashboard.",
        ),
    ] = 30,
) -> Envelope[Any]:
    """Phase 4 click time series grouped by day."""
    start, end = normalize_date_range(from_=from_, to=to, days=days)

    data = await get_link_timeseries(
        db=db,
        short_code=short_code,
        user_id=_user_id(current_user),
        from_=start,
        to=end,
    )

    return _envelope(
        data=data,
        meta={
            "short_code": short_code,
            "from": start.isoformat(),
            "to": end.isoformat(),
            "days": days,
            "granularity": "day",
        },
    )


@router.get(
    "/links/{short_code}/breakdown",
    response_model=Envelope[Any],
    summary="Per-link analytics breakdown by dimension",
    description=(
        "Groups clicks by a single dimension. "
        "Use `dimension=country` for the geographic table, "
        "`dimension=browser` or `dimension=referrer` for top-browsers / top-referrers "
        "dashboard panels."
    ),
)
async def link_analytics_breakdown(
    short_code: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[Any, Depends(get_current_user)],
    dimension: Annotated[
        AnalyticsDimension,
        Query(
            description=(
                "Aggregation dimension: country, city, browser, os, device_type, referrer"
            ),
        ),
    ] = "country",
    from_: Annotated[
        datetime | None,
        Query(alias="from", description="Start datetime, ISO-8601"),
    ] = None,
    to: Annotated[
        datetime | None,
        Query(description="End datetime, ISO-8601"),
    ] = None,
    days: Annotated[
        int,
        Query(ge=1, le=365, description="Rolling window in days (default 30)"),
    ] = 30,
    limit: Annotated[
        int,
        Query(ge=1, le=100, description="Maximum number of rows to return"),
    ] = 10,
) -> Envelope[Any]:
    """Phase 4 analytics breakdown by country, browser, referrer, os, city, or device type."""
    start, end = normalize_date_range(from_=from_, to=to, days=days)

    data = await get_link_breakdown(
        db=db,
        short_code=short_code,
        user_id=_user_id(current_user),
        dimension=dimension,
        from_=start,
        to=end,
        limit=limit,
    )

    return _envelope(
        data=data,
        meta={
            "short_code": short_code,
            "dimension": dimension,
            "from": start.isoformat(),
            "to": end.isoformat(),
            "days": days,
            "limit": limit,
        },
    )
