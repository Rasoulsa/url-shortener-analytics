from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.common import Envelope
from app.schemas.user import UserCreate, UserLogin, UserOut
from app.services import auth_service

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
    user = await auth_service.register_user(db, payload)
    return Envelope(data=UserOut.model_validate(user))


@router.post(
    "/login",
    response_model=Envelope[UserOut],
    status_code=status.HTTP_200_OK,
    summary="Login with email+password or API key",
    description=(
        "Authenticates a user. Provide **either** `email` + `password` "
        "**or** `api_key`. Returns the same profile payload as `/register`, "
        "including the `api_key` to use in the `X-API-Key` header."
    ),
    responses={
        200: {
            "description": "Authenticated",
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
        401: {
            "description": "Invalid credentials",
            "content": {
                "application/json": {
                    "example": {
                        "data": None,
                        "meta": {},
                        "errors": [
                            {
                                "code": "unauthorized",
                                "message": "Invalid email or password.",
                            }
                        ],
                    }
                }
            },
        },
        422: {
            "description": "Neither credential path provided",
            "content": {
                "application/json": {
                    "example": {
                        "data": None,
                        "meta": {},
                        "errors": [
                            {
                                "code": "validation_error",
                                "message": "Provide either 'api_key', or 'email' + 'password'.",
                            }
                        ],
                    }
                }
            },
        },
    },
)
async def login(
    payload: UserLogin,
    db: AsyncSession = Depends(get_db),
) -> Envelope[UserOut]:
    user = await auth_service.authenticate_user(db, payload)
    return Envelope(data=UserOut.model_validate(user))


@router.get(
    "/me",
    response_model=Envelope[UserOut],
    status_code=status.HTTP_200_OK,
    summary="Get the currently authenticated user",
    description="Returns the profile of the user identified by the `X-API-Key` header.",
    responses={401: _401},
)
async def me(user: User = Depends(get_current_user)) -> Envelope[UserOut]:
    return Envelope(data=UserOut.model_validate(user))
