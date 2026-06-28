from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.user import User


async def get_current_user(
    x_api_key: str | None = Header(default=None, alias="x-api-key"),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Authenticate via X-API-Key header.
    Raises 401 if missing or invalid.
    """
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required. Pass it in the X-API-Key header.",
        )
    user = (await db.execute(select(User).where(User.api_key == x_api_key))).scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
        )
    return user


async def get_optional_user(
    x_api_key: str | None = Header(default=None, alias="x-api-key"),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """
    Like get_current_user but returns None instead of raising.
    For endpoints that serve both anonymous and authenticated users.
    """
    if not x_api_key:
        return None
    return (await db.execute(select(User).where(User.api_key == x_api_key))).scalar_one_or_none()
