from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.click import Click


async def create_click_event(
    db: AsyncSession,
    *,
    link_id: int,
    clicked_at: datetime,
    ip_anonymized: str | None,
    user_agent: str | None,
    referrer: str | None,
    country: str | None,
    city: str | None,
    browser: str | None,
    os: str | None,
    device_type: str | None,
) -> Click:
    """
    Persist one enriched Phase 3 click event.

    Important:
    - raw IP is never stored
    - ip_anonymized should already be anonymized before calling this function
    - GeoIP/User-Agent enrichment should be done by the Celery task
    """
    click = Click(
        link_id=link_id,
        clicked_at=clicked_at,
        ip_anonymized=ip_anonymized,
        user_agent=user_agent,
        referrer=referrer,
        country=country,
        city=city,
        browser=browser,
        os=os,
        device_type=device_type,
    )

    db.add(click)
    await db.commit()
    await db.refresh(click)

    return click
