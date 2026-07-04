from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.api.deps import get_optional_user
from app.models.user import User

router = APIRouter(tags=["Dashboard UI"])

templates = Jinja2Templates(directory="app/templates")


@router.get("/dashboard", include_in_schema=False)
async def dashboard_root() -> RedirectResponse:
    return RedirectResponse(url="/dashboard/", status_code=302)


@router.get("/dashboard/", response_class=HTMLResponse, include_in_schema=False)
async def dashboard_index(
    request: Request,
    user: User | None = Depends(get_optional_user),
) -> Response:  # ← changed from HTMLResponse
    if user is None:
        return RedirectResponse(url="/?auth=required", status_code=303)

    return templates.TemplateResponse(
        request,
        "dashboard/index.html",
        {"user_email": user.email, "api_key": user.api_key},
    )


@router.get("/dashboard/compare", response_class=HTMLResponse, include_in_schema=False)
async def dashboard_compare(
    request: Request,
    user: User | None = Depends(get_optional_user),
) -> Response:  # ← changed from HTMLResponse
    if user is None:
        return RedirectResponse(url="/?auth=required", status_code=303)

    return templates.TemplateResponse(
        request,
        "dashboard/compare.html",
        {"user_email": user.email, "api_key": user.api_key},
    )
