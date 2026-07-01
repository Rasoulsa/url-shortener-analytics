from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import hash_password
from app.models.user import User
from app.schemas.common import Envelope
from app.schemas.user import UserCreate, UserOut

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])

_401 = {
    "description": "Missing or invalid API key",
    "content": {
        "application/json": {
            "example": {
                "data": None,
                "meta": {},
                "errors": [
                    {
                        "code": "unauthorized",
                        "message": "API key required. Pass it in the X-API-Key header.",
                    }
                ],
            }
        }
    },
}


@router.post(
    "/register",
    response_model=Envelope[UserOut],
    status_code=status.HTTP_201_CREATED,
    summary="Register a new account",
    description=(
        "Creates a user account and returns an **API key**. "
        "Store the key securely — it cannot be recovered after this response. "
        "Pass it in the `X-API-Key` header on all subsequent requests."
    ),
    responses={
        201: {
            "description": "Account created — API key returned",
            "content": {
                "application/json": {
                    "example": {
                        "data": {
                            "email": "you@example.com",
                            "api_key": "sk_abc123...",
                            "created_at": "2026-07-01T12:00:00Z",
                        },
                        "meta": None,
                        "errors": [],
                    }
                }
            },
        },
        409: {
            "description": "Email already registered",
            "content": {
                "application/json": {
                    "example": {
                        "data": None,
                        "meta": {},
                        "errors": [
                            {
                                "code": "conflict",
                                "message": "Email 'you@example.com' is already registered.",
                            }
                        ],
                    }
                }
            },
        },
        422: {
            "description": "Validation error",
            "content": {
                "application/json": {
                    "example": {
                        "data": None,
                        "meta": {},
                        "errors": [
                            {
                                "code": "validation_error",
                                "message": "Field required",
                                "field": "email",
                            }
                        ],
                    }
                }
            },
        },
    },
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
