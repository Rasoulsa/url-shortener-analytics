from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import hash_password
from app.models.user import User
from app.schemas.common import Envelope
from app.schemas.user import UserCreate, UserOut

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=Envelope[UserOut],
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    description=(
        "Creates a new account and returns an **API key**. "
        "Use this key in the `X-API-Key` header for all authenticated endpoints."
    ),
)
async def register(
    payload: UserCreate,
    db: AsyncSession = Depends(get_db),
) -> Envelope[UserOut]:
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

    return Envelope(data=UserOut.model_validate(user))
