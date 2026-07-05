from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.api.deps import get_optional_user
from app.models.user import User

router = APIRouter(tags=["Analytics UI"])

templates = Jinja2Templates(directory="app/templates")


@router.get(
    "/dashboard/analytics/{short_code}",
    response_class=HTMLResponse,
    include_in_schema=False,
)
async def link_analytics_page(
    request: Request,
    short_code: str,
    user: User | None = Depends(get_optional_user),
) -> Response:
    if user is None:
        return RedirectResponse(url="/?auth=required", status_code=303)

    return templates.TemplateResponse(
        request,
        "dashboard/analytics.html",
        {
            "user_email": user.email,
            "api_key": user.api_key,
            "short_code": short_code,
        },
    )
