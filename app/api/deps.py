from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.user import User

SESSION_COOKIE = "session_token"


def _extract_api_key(request: Request, x_api_key: str | None) -> str | None:
    """Header takes priority (API clients); cookie is the browser fallback."""
    return x_api_key or request.cookies.get(SESSION_COOKIE)


async def get_current_user(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="x-api-key"),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Authenticate via X-API-Key header OR session_token cookie.
    Raises 401 if missing or invalid.
    """
    api_key = _extract_api_key(request, x_api_key)
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required. Pass it in the X-API-Key header.",
        )
    user = (await db.execute(select(User).where(User.api_key == api_key))).scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
        )
    return user


async def get_optional_user(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="x-api-key"),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """
    Like get_current_user but returns None instead of raising.
    Used by web pages that need to know auth state without forcing a 401
    (they redirect instead), and by the browser's silent /me check.
    """
    api_key = _extract_api_key(request, x_api_key)
    if not api_key:
        return None
    return (await db.execute(select(User).where(User.api_key == api_key))).scalar_one_or_none()
