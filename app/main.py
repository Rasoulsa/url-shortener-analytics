from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1 import analytics, analytics_dashboard, auth, dashboard_ui, links, redirect
from app.core.config import settings
from app.core.envelope import error_body, errors_body
from app.core.exceptions import AppError
from app.core.openapi import build_openapi_schema
from app.core.redis_client import redis_client
from app.middleware.rate_limit import RateLimitMiddleware
from app.web import public
from app.web import session as web_session


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await redis_client.close()


app = FastAPI(
    title="URL Shortener & Analytics API",
    version="1.0.0",
    # Disable default /docs and /redoc so we can serve custom ones below
    docs_url=None,
    redoc_url=None,
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")


# ── Override OpenAPI schema ──────────────────────────────────────────────────
def custom_openapi() -> dict:  # type: ignore[type-arg]
    return build_openapi_schema(app)


app.openapi = custom_openapi  # type: ignore[method-assign]


# ── Custom /docs and /redoc (lets us set titles, favicon) ────────────────────
@app.get("/docs", include_in_schema=False)
async def swagger_ui() -> HTMLResponse:
    return get_swagger_ui_html(
        openapi_url="/openapi.json",
        title="URL Shortener API — Swagger UI",
        swagger_favicon_url="https://fastapi.tiangolo.com/img/favicon.png",
        swagger_ui_parameters={
            "defaultModelsExpandDepth": 2,
            "defaultModelExpandDepth": 2,
            "docExpansion": "list",  # show endpoints collapsed but listed
            "filter": True,  # enable search bar
            "tryItOutEnabled": True,  # try-it-out open by default
        },
    )


@app.get("/redoc", include_in_schema=False)
async def redoc_ui() -> HTMLResponse:
    return get_redoc_html(
        openapi_url="/openapi.json",
        title="URL Shortener API — ReDoc",
        redoc_favicon_url="https://fastapi.tiangolo.com/img/favicon.png",
    )


# ── Middleware ────────────────────────────────────────────────────────────────
app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Exception handlers ───────────────────────────────────────────────────────
@app.exception_handler(AppError)
async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(code=exc.code, message=exc.message),
    )


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = [
        {
            "code": "validation_error",
            "message": e["msg"],
            "field": ".".join(str(p) for p in e["loc"] if p != "body"),
        }
        for e in exc.errors()
    ]
    return JSONResponse(status_code=422, content=errors_body(errors))


@app.exception_handler(StarletteHTTPException)
async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code_map = {
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        409: "conflict",
        410: "gone",
        429: "rate_limited",
    }
    code = code_map.get(exc.status_code, "http_error")
    message = exc.detail if isinstance(exc.detail, str) else "Request failed."
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(code=code, message=message),
    )


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content=error_body(code="internal_error", message="An unexpected error occurred."),
    )


# ── Routers ──────────────────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(links.router)
app.include_router(analytics.router)
app.include_router(analytics_dashboard.router)
app.include_router(dashboard_ui.router)
app.include_router(public.router)
app.include_router(web_session.router)


@app.get(
    "/health",
    tags=["System"],
    summary="Liveness probe",
    description=(
        "Returns `200 ok` when the API is running. "
        "Returns `200 degraded` if Redis is unreachable (API still serves traffic). "
        "Use this endpoint for container health checks and uptime monitors."
    ),
)
async def health() -> dict:
    redis_ok = True
    try:
        await redis_client.ping()
    except Exception:
        redis_ok = False

    return {
        "status": "ok" if redis_ok else "degraded",
        "version": settings.app_version,
        "dependencies": {"redis": "up" if redis_ok else "down"},
    }


# ── Catch-all Redirect (MUST be last) ────────────────────────────────────────
app.include_router(redirect.router)
