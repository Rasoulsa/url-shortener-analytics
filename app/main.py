from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import analytics, auth, links, redirect
from app.core.config import settings
from app.core.redis_client import redis_client
from app.middleware.rate_limit import RateLimitMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup — Day 2+ will warm the cache here
    yield
    # Graceful shutdown
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
# NOTE: Starlette runs middleware in reverse order of registration.
# Registering RateLimitMiddleware AFTER CORS means CORS runs first
# (outermost), so 429 responses still get CORS headers.
app.add_middleware(RateLimitMiddleware)

# CORS (tighten origins in production — Day 4)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API Routers ───────────────────────────────────────────────
# /api/* routes should be registered before /{short_code}
app.include_router(auth.router)
app.include_router(links.router)
app.include_router(analytics.router)


@app.get("/health", tags=["System"], summary="Health check")
async def health():
    """Returns service status and dependency health."""
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


# ── Catch-all Redirect ────────────────────────────────────────
# MUST be last because it likely defines "/{short_code}"
app.include_router(redirect.router)
