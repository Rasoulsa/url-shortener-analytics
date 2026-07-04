from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.models.user import User
from app.schemas.user import UserCreate, UserLogin


async def register_user(db: AsyncSession, payload: UserCreate) -> User:
    existing = (
        await db.execute(select(User).where(User.email == payload.email))
    ).scalar_one_or_none()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Email '{payload.email}' is already registered.",
        )

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def authenticate_user(db: AsyncSession, payload: UserLogin) -> User:
    if payload.api_key:
        user = (
            await db.execute(select(User).where(User.api_key == payload.api_key))
        ).scalar_one_or_none()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired API key.",
            )
        return user

    user = (await db.execute(select(User).where(User.email == payload.email))).scalar_one_or_none()
    if (
        not user
        or payload.password is None
        or not verify_password(payload.password, user.hashed_password)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )
    return user
