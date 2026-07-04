from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.user import UserCreate, UserLogin
from app.services import auth_service

router = APIRouter(prefix="/session", tags=["Web Session"])

SESSION_COOKIE = "session_token"
COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 days


def _set_session_cookie(response: JSONResponse, api_key: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=api_key,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=False,  # TODO: flip to True once served over HTTPS in prod
        path="/",
    )


@router.post("/register")
async def session_register(payload: UserCreate, db: AsyncSession = Depends(get_db)):
    user = await auth_service.register_user(db, payload)
    response = JSONResponse({"redirect": "/dashboard/"})
    _set_session_cookie(response, user.api_key)
    return response


@router.post("/login")
async def session_login(payload: UserLogin, db: AsyncSession = Depends(get_db)):
    user = await auth_service.authenticate_user(db, payload)
    response = JSONResponse({"redirect": "/dashboard/"})
    _set_session_cookie(response, user.api_key)
    return response


@router.post("/logout")
async def session_logout():
    response = JSONResponse({"redirect": "/"})
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response
