"""
Redirect endpoint — the hot path of the service.

Day 1: DB-only (simple, fully working).
Day 2: Redis cache-aside inserted before DB lookup.
Day 3: Click recording moved to async Celery task.

TODO markers show exactly where each upgrade slots in.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import verify_password
from app.models.link import Link

router = APIRouter(tags=["Redirect"])


def _is_expired(expires_at: datetime | None) -> bool:
    return expires_at is not None and expires_at < datetime.now(UTC)


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
        302: {"description": "Redirect (temporary)"},
        301: {"description": "Redirect (permanent)"},
        404: {"description": "Short code not found"},
        410: {"description": "Link has expired"},
    },
)
async def redirect(
    short_code: str,
    request: Request,  # kept for Day 3 — IP + UA extraction
    db: AsyncSession = Depends(get_db),
):
    # TODO(Day 2): Redis cache-aside lookup before DB
    # cached = await cache_service.get(short_code)
    # if cached: fire_click_task(); return RedirectResponse(cached)

    link = (
        await db.execute(select(Link).where(Link.short_code == short_code))
    ).scalar_one_or_none()

    if not link:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"'{short_code}' not found.",
        )

    # Lazy expiry check (no cron needed — checked on access)
    # TODO(Day 2): also invalidate Redis cache entry here
    if _is_expired(link.expires_at):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="This link has expired.",
        )

    if link.password_hash:
        return HTMLResponse(_password_gate_html(short_code))

    # TODO(Day 2): replace with Redis INCR write-through counter
    # TODO(Day 3): fire record_click.delay(link.id, ip, ua, referrer)
    link.click_count += 1
    await db.commit()

    redirect_code = (
        status.HTTP_301_MOVED_PERMANENTLY if link.is_permanent else status.HTTP_302_FOUND
    )
    return RedirectResponse(url=link.long_url, status_code=redirect_code)


@router.post(
    "/{short_code}/unlock",
    include_in_schema=False,  # internal form endpoint
)
async def unlock(
    short_code: str,
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    link = (
        await db.execute(select(Link).where(Link.short_code == short_code))
    ).scalar_one_or_none()

    if not link:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Link not found")
    if _is_expired(link.expires_at):
        raise HTTPException(status.HTTP_410_GONE, "This link has expired")
    if not link.password_hash or not verify_password(password, link.password_hash):
        return HTMLResponse(
            _password_gate_html(short_code, "Incorrect password. Try again."),
            status_code=status.HTTP_403_FORBIDDEN,
        )

    link.click_count += 1
    await db.commit()

    return RedirectResponse(url=link.long_url, status_code=status.HTTP_302_FOUND)
