from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

AnalyticsDimension = Literal[
    "country",
    "city",
    "browser",
    "os",
    "device_type",
    "referrer",
]


DIMENSION_SQL: dict[str, str] = {
    "country": "COALESCE(NULLIF(c.country, ''), 'Unknown')",
    "city": "COALESCE(NULLIF(c.city, ''), 'Unknown')",
    "browser": "COALESCE(NULLIF(c.browser, ''), 'Unknown')",
    "os": "COALESCE(NULLIF(c.os, ''), 'Unknown')",
    "device_type": "COALESCE(NULLIF(c.device_type, ''), 'Unknown')",
    "referrer": """
        CASE
            WHEN c.referrer IS NULL OR c.referrer = '' THEN 'Direct / Unknown'
            ELSE split_part(regexp_replace(c.referrer, '^https?://', ''), '/', 1)
        END
    """,
}


def normalize_date_range(
    *,
    from_: datetime | None,
    to: datetime | None,
    days: int,
) -> tuple[datetime, datetime]:
    if days < 1 or days > 365:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="days must be between 1 and 365",
        )

    end = to or datetime.now(UTC)
    start = from_ or end - timedelta(days=days)

    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)

    if end.tzinfo is None:
        end = end.replace(tzinfo=UTC)

    if start >= end:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="'from' must be earlier than 'to'",
        )

    return start, end


async def get_owned_link(
    *,
    db: AsyncSession,
    short_code: str,
    user_id: int,
) -> dict[str, Any]:
    """
    Return a link owned by authenticated user.

    If your links table uses owner_id instead of user_id, replace l.user_id below.
    If your URL column is long_url instead of original_url, replace l.original_url below.
    """
    result = await db.execute(
        text(
            """
            SELECT
                l.id,
                l.short_code,
                l.long_url AS original_url,
                l.click_count
            FROM links AS l
            WHERE l.short_code = :short_code
              AND l.user_id = :user_id
            LIMIT 1
            """
        ),
        {
            "short_code": short_code,
            "user_id": user_id,
        },
    )

    row = result.mappings().first()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Link not found",
        )

    return dict(row)


async def get_link_overview(
    *,
    db: AsyncSession,
    short_code: str,
    user_id: int,
    from_: datetime,
    to: datetime,
) -> dict[str, Any]:
    link = await get_owned_link(
        db=db,
        short_code=short_code,
        user_id=user_id,
    )

    result = await db.execute(
        text(
            """
            SELECT
                COUNT(c.id)::int AS event_count,
                COUNT(DISTINCT NULLIF(c.country, ''))::int AS unique_countries,
                COUNT(DISTINCT NULLIF(c.browser, ''))::int AS unique_browsers,
                MIN(c.clicked_at) AS first_click_at,
                MAX(c.clicked_at) AS last_click_at
            FROM clicks AS c
            WHERE c.link_id = :link_id
              AND c.clicked_at >= :from_ts
              AND c.clicked_at < :to_ts
            """
        ),
        {
            "link_id": link["id"],
            "from_ts": from_,
            "to_ts": to,
        },
    )

    stats = dict(result.mappings().one())

    return {
        "short_code": link["short_code"],
        "original_url": link.get("original_url"),
        "stored_click_count": link.get("click_count", 0) or 0,
        "event_count": stats["event_count"] or 0,
        "unique_countries": stats["unique_countries"] or 0,
        "unique_browsers": stats["unique_browsers"] or 0,
        "first_click_at": stats["first_click_at"],
        "last_click_at": stats["last_click_at"],
    }


async def get_link_timeseries(
    *,
    db: AsyncSession,
    short_code: str,
    user_id: int,
    from_: datetime,
    to: datetime,
) -> list[dict[str, Any]]:
    link = await get_owned_link(
        db=db,
        short_code=short_code,
        user_id=user_id,
    )

    result = await db.execute(
        text(
            """
            WITH buckets AS (
                SELECT generate_series(
                    date_trunc('day', CAST(:from_ts AS timestamptz)),
                    date_trunc('day', CAST(:to_ts AS timestamptz)),
                    interval '1 day'
                )::date AS bucket_date
            ),
            counts AS (
                SELECT
                    date_trunc('day', c.clicked_at)::date AS bucket_date,
                    COUNT(c.id)::int AS clicks
                FROM clicks AS c
                WHERE c.link_id = :link_id
                  AND c.clicked_at >= :from_ts
                  AND c.clicked_at < :to_ts
                GROUP BY date_trunc('day', c.clicked_at)::date
            )
            SELECT
                buckets.bucket_date::text AS date,
                COALESCE(counts.clicks, 0)::int AS clicks
            FROM buckets
            LEFT JOIN counts ON counts.bucket_date = buckets.bucket_date
            ORDER BY buckets.bucket_date ASC
            """
        ),
        {
            "link_id": link["id"],
            "from_ts": from_,
            "to_ts": to,
        },
    )

    return [dict(row) for row in result.mappings().all()]


async def get_link_breakdown(
    *,
    db: AsyncSession,
    short_code: str,
    user_id: int,
    dimension: AnalyticsDimension,
    from_: datetime,
    to: datetime,
    limit: int,
) -> list[dict[str, Any]]:
    if limit < 1 or limit > 100:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="limit must be between 1 and 100",
        )

    if dimension not in DIMENSION_SQL:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported dimension: {dimension}",
        )

    link = await get_owned_link(
        db=db,
        short_code=short_code,
        user_id=user_id,
    )

    dimension_expr = DIMENSION_SQL[dimension]

    result = await db.execute(
        text(
            f"""
            WITH grouped AS (
                SELECT
                    {dimension_expr} AS label,
                    COUNT(c.id)::int AS clicks
                FROM clicks AS c
                WHERE c.link_id = :link_id
                  AND c.clicked_at >= :from_ts
                  AND c.clicked_at < :to_ts
                GROUP BY label
            ),
            total AS (
                SELECT COALESCE(SUM(clicks), 0)::int AS total_clicks
                FROM grouped
            )
            SELECT
                grouped.label,
                grouped.clicks,
                CASE
                    WHEN total.total_clicks = 0 THEN 0
                    ELSE ROUND(
                        (grouped.clicks::numeric / total.total_clicks::numeric) * 100,
                        2
                    )
                END::float AS percentage
            FROM grouped
            CROSS JOIN total
            ORDER BY grouped.clicks DESC, grouped.label ASC
            LIMIT :limit
            """
        ),
        {
            "link_id": link["id"],
            "from_ts": from_,
            "to_ts": to,
            "limit": limit,
        },
    )

    return [dict(row) for row in result.mappings().all()]


async def get_user_analytics_overview(
    *,
    db: AsyncSession,
    user_id: int,
    from_: datetime,
    to: datetime,
) -> dict[str, Any]:
    result = await db.execute(
        text(
            """
            SELECT
                COUNT(DISTINCT l.id)::int AS link_count,
                COUNT(c.id)::int AS event_count,
                COUNT(DISTINCT NULLIF(c.country, ''))::int AS unique_countries,
                COUNT(DISTINCT NULLIF(c.browser, ''))::int AS unique_browsers,
                MIN(c.clicked_at) AS first_click_at,
                MAX(c.clicked_at) AS last_click_at
            FROM links AS l
            LEFT JOIN clicks AS c
              ON c.link_id = l.id
             AND c.clicked_at >= :from_ts
             AND c.clicked_at < :to_ts
            WHERE l.user_id = :user_id
            """
        ),
        {
            "user_id": user_id,
            "from_ts": from_,
            "to_ts": to,
        },
    )

    row = dict(result.mappings().one())

    return {
        "link_count": row["link_count"] or 0,
        "event_count": row["event_count"] or 0,
        "unique_countries": row["unique_countries"] or 0,
        "unique_browsers": row["unique_browsers"] or 0,
        "first_click_at": row["first_click_at"],
        "last_click_at": row["last_click_at"],
    }
