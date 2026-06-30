"""
Redirect endpoint — the hot path of the service.

Day 1: DB-only redirect path.
Day 2 Branch 1: Redis cache-aside for redirect metadata.
Day 2 Branch 2: Redis write-through click counters.

This branch adds:
- Redis lookup before DB lookup
- TTL-aligned metadata cache
- Lazy deletion for expired links discovered on cache miss
- Cache-aware password unlock
- Redis click counter increments on successful redirects
- Postgres click-count fallback if Redis counter increment fails
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
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


async def _record_click(
    db: AsyncSession,
    short_code: str,
) -> None:
    """
    Record a redirect click.

    Day 2 behavior:
    - Prefer Redis counter increment for fast redirect path.
    - Fall back to direct Postgres increment if Redis is unavailable.
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
        update(Link).where(Link.short_code == short_code).values(click_count=Link.click_count + 1)
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


def _password_gate_html(short_code: str, error: str = "") -> str:
    """Clean HTML form for password-protected links."""
    error_block = (
        f'<p style="color:#e74c3c;margin:8px 0;font-size:14px">{error}</p>' if error else ""
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>Protected Link</title>
  <style>
    *{{box-sizing:border-box}}
    body{{
      font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
      display:flex;align-items:center;justify-content:center;
      min-height:100vh;margin:0;background:#f0f2f5
    }}
    .card{{
      background:#fff;border-radius:12px;padding:40px;
      box-shadow:0 4px 20px rgba(0,0,0,.1);
      text-align:center;width:100%;max-width:380px
    }}
    .icon{{font-size:48px;margin-bottom:16px}}
    h2{{margin:0 0 8px;color:#1a1a2e}}
    .sub{{color:#666;margin:0 0 24px;font-size:14px}}
    input[type=password]{{
      width:100%;padding:12px 16px;
      border:2px solid #e0e0e0;border-radius:8px;
      font-size:16px;outline:none;transition:border-color .2s
    }}
    input[type=password]:focus{{border-color:#4e79a7}}
    button{{
      width:100%;margin-top:12px;padding:12px;
      background:#4e79a7;color:#fff;border:none;
      border-radius:8px;font-size:16px;cursor:pointer;
      transition:background .2s
    }}
    button:hover{{background:#3d6292}}
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">🔒</div>
    <h2>Protected Link</h2>
    <p class="sub">Enter the password to continue.</p>
    {error_block}
    <form method="post" action="/{short_code}/unlock">
      <input type="password" name="password"
             placeholder="Password" autofocus required/>
      <button type="submit">Unlock →</button>
    </form>
  </div>
</body>
</html>"""


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
    """
    _ = request

    cached = await get_cached_link(redis_client, short_code)

    if cached is not None:
        if cached.password_hash:
            return HTMLResponse(_password_gate_html(short_code))

        await _record_click(db, cached.short_code)
        enqueue_click_event(short_code=cached.short_code, request=request)

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
        return HTMLResponse(_password_gate_html(short_code))

    await _record_click(db, cached.short_code)
    enqueue_click_event(short_code=cached.short_code, request=request)

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
        return HTMLResponse(
            _password_gate_html(short_code, "Incorrect password. Try again."),
            status_code=status.HTTP_403_FORBIDDEN,
        )

    await _record_click(db, cached.short_code)
    enqueue_click_event(short_code=cached.short_code, request=request)

    return RedirectResponse(
        url=cached.long_url,
        status_code=_redirect_status(cached.is_permanent),
    )
