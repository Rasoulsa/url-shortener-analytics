from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1 import analytics, auth, links, redirect
from app.core.config import settings
from app.core.envelope import error_body, errors_body
from app.core.exceptions import AppError
from app.core.redis_client import redis_client
from app.middleware.rate_limit import RateLimitMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await redis_client.close()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "A production-minded URL shortener with intelligent Redis caching, "
        "non-blocking analytics (Celery + GeoIP), and a live dashboard."
    ),
    lifespan=lifespan,
)

# ── Middleware ────────────────────────────────────────────────
app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Exception handlers (canonical envelope for ALL errors) ────
@app.exception_handler(AppError)
async def handle_app_exception(request: Request, exc: AppError) -> JSONResponse:
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
    # Catches raw HTTPException still raised in routers (409 in links.py)
    # and FastAPI's built-in 404 for unknown routes.
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
        content=error_body(
            code="internal_error",
            message="An unexpected error occurred.",
        ),
    )


# ── API Routers ───────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(links.router)
app.include_router(analytics.router)


@app.get("/health", tags=["System"], summary="Health check")
async def health():
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


# ── Catch-all Redirect (MUST be last) ─────────────────────────
app.include_router(redirect.router)
