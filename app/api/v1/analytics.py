from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.services.analytics_stats import (
    AnalyticsDimension,
    get_link_breakdown,
    get_link_overview,
    get_link_timeseries,
    get_user_analytics_overview,
    normalize_date_range,
)

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


def _user_id(current_user: Any) -> int:
    return int(current_user.id)


def _envelope(
    *,
    data: Any,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "data": data,
        "meta": meta or {},
        "errors": [],
    }


@router.get("/overview")
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
        Query(ge=1, le=365),
    ] = 30,
) -> dict[str, Any]:
    """
    Phase 3 analytics overview for all links owned by the authenticated user.
    """
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


@router.get("/links/{short_code}/overview")
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
        Query(ge=1, le=365),
    ] = 30,
) -> dict[str, Any]:
    """
    Phase 3 per-link analytics overview.
    """
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


@router.get("/links/{short_code}/timeseries")
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
        Query(ge=1, le=365),
    ] = 30,
) -> dict[str, Any]:
    """
    Phase 3 click time series grouped by day.
    """
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


@router.get("/links/{short_code}/breakdown")
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
        Query(ge=1, le=365),
    ] = 30,
    limit: Annotated[
        int,
        Query(ge=1, le=100),
    ] = 10,
) -> dict[str, Any]:
    """
    Phase 3 analytics breakdown.

    Supported dimensions:
    country, city, browser, os, device_type, referrer.
    """
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
