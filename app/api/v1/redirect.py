from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.redis_client import redis_client
from app.core.security import verify_password
from app.models.link import Link
from app.services.analytics_queue import enqueue_click_event
from app.services.cache import (
    CachedLink,
    delete_cached_link,
    get_cached_link,
    is_expired,
    set_cached_link,
)
from app.services.counters import increment_link_click_counter

router = APIRouter(tags=["Redirect"])


def _redirect_status(is_permanent: bool) -> int:
    return status.HTTP_301_MOVED_PERMANENTLY if is_permanent else status.HTTP_302_FOUND


def _to_cached_link(link: Link) -> CachedLink:
    return CachedLink(
        short_code=link.short_code,
        long_url=str(link.long_url),
        expires_at=link.expires_at,
        is_permanent=bool(link.is_permanent),
        password_hash=link.password_hash,
    )


async def _record_successful_redirect(
    *,
    db: AsyncSession,
    short_code: str,
    request: Request,
) -> None:
    """
    Record successful redirect side effects.

    Phase 2:
    - increment Redis click counter
    - fall back to Postgres click_count increment if Redis fails

    Phase 3:
    - enqueue detailed analytics event for Celery processing

    Important:
    - enqueue_click_event fails open internally
    - redirect should still work if Celery/Redis broker is unavailable
    """
    await _record_click(db, short_code)
    enqueue_click_event(short_code=short_code, request=request)


async def _record_click(
    db: AsyncSession,
    short_code: str,
) -> None:
    """
    Record a redirect click.

    Preferred:
    - Redis counter increment for the fast redirect path.

    Fallback:
    - direct Postgres increment if Redis counter increment fails.
    """
    counter_value = await increment_link_click_counter(redis_client, short_code)

    if counter_value is None:
        await _increment_click_count(db, short_code)


async def _increment_click_count(
    db: AsyncSession,
    short_code: str,
) -> None:
    """
    Fallback direct Postgres click increment.

    Normal redirect traffic increments Redis counters first. This function is
    only used if Redis is unavailable or the counter increment fails.
    """
    await db.execute(
        update(Link).where(Link.short_code == short_code).values(click_count=Link.click_count + 1),
    )
    await db.commit()


async def _load_link_from_db(
    db: AsyncSession,
    short_code: str,
) -> Link | None:
    result = await db.execute(select(Link).where(Link.short_code == short_code))
    return result.scalar_one_or_none()


async def _delete_expired_link(
    db: AsyncSession,
    short_code: str,
    link: Link,
) -> None:
    """
    Lazy deletion.

    Expired links are removed when discovered during redirect lookup instead
    of by scheduled cron.
    """
    await delete_cached_link(redis_client, short_code)
    await db.delete(link)
    await db.commit()


templates = Jinja2Templates(directory="app/templates")


def _password_gate_response(
    request: Request,
    short_code: str,
    error: str = "",
    status_code: int = status.HTTP_200_OK,
) -> HTMLResponse:
    """Render the branded password gate page."""
    return templates.TemplateResponse(
        request=request,
        name="public/password_gate.html",
        context={"short_code": short_code, "error": error},
        status_code=status_code,
    )


@router.get(
    "/{short_code}",
    summary="Redirect to original URL",
    responses={
        302: {"description": "Redirect temporary"},
        301: {"description": "Redirect permanent"},
        404: {"description": "Short code not found"},
        410: {"description": "Link has expired"},
    },
)
async def redirect(
    short_code: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Redirect using Redis cache-aside.

    Flow:
    1. Try Redis metadata cache.
    2. If cache hit, redirect or show password gate.
    3. If cache miss, load from DB.
    4. If expired, lazily delete and return 410.
    5. If valid, cache metadata and redirect or show password gate.
    6. On successful redirect, enqueue Phase 3 analytics processing.
    """
    cached = await get_cached_link(redis_client, short_code)

    if cached is not None:
        if cached.password_hash:
            return _password_gate_response(request, short_code)

        await _record_successful_redirect(
            db=db,
            short_code=cached.short_code,
            request=request,
        )

        return RedirectResponse(
            url=cached.long_url,
            status_code=_redirect_status(cached.is_permanent),
        )

    link = await _load_link_from_db(db, short_code)

    if link is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"'{short_code}' not found.",
        )

    if is_expired(link.expires_at):
        await _delete_expired_link(db, short_code, link)

        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="This link has expired.",
        )

    await set_cached_link(redis_client, link)
    cached = _to_cached_link(link)

    if cached.password_hash:
        return _password_gate_response(request, short_code)

    await _record_successful_redirect(
        db=db,
        short_code=cached.short_code,
        request=request,
    )

    return RedirectResponse(
        url=cached.long_url,
        status_code=_redirect_status(cached.is_permanent),
    )


@router.post(
    "/{short_code}/unlock",
    include_in_schema=False,
)
async def unlock(
    short_code: str,
    request: Request,
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Unlock password-protected links.

    This also uses cache-aside metadata so the protected link flow benefits
    from Redis after the first lookup.

    On successful unlock, the redirect is counted and a Phase 3 analytics
    event is enqueued.
    """
    cached = await get_cached_link(redis_client, short_code)

    if cached is None:
        link = await _load_link_from_db(db, short_code)

        if link is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Link not found",
            )

        if is_expired(link.expires_at):
            await _delete_expired_link(db, short_code, link)

            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="This link has expired",
            )

        await set_cached_link(redis_client, link)
        cached = _to_cached_link(link)

    if not cached.password_hash or not verify_password(password, cached.password_hash):
        return _password_gate_response(
            request,
            short_code,
            error="Incorrect password. Try again.",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    await _record_successful_redirect(
        db=db,
        short_code=cached.short_code,
        request=request,
    )

    return RedirectResponse(
        url=cached.long_url,
        status_code=_redirect_status(cached.is_permanent),
    )
