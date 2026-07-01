from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(tags=["Dashboard UI"])

templates = Jinja2Templates(directory="app/templates")


@router.get("/dashboard", include_in_schema=False)
async def dashboard_root() -> RedirectResponse:
    return RedirectResponse(url="/dashboard/", status_code=302)


@router.get("/dashboard/", response_class=HTMLResponse, include_in_schema=False)
async def dashboard_index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "dashboard/index.html",
        {},
    )


@router.get("/dashboard/compare", response_class=HTMLResponse, include_in_schema=False)
async def dashboard_compare(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "dashboard/compare.html",
        {},
    )
