from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import auth, links, redirect
from app.core.config import settings
from app.core.redis_client import redis_client


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

# CORS (tighten origins in production — Day 4)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ──────────────────────────────────────────────────
# /api/* MUST be registered before /{short_code} catch-all
app.include_router(auth.router)
app.include_router(links.router)
app.include_router(redirect.router)  # catch-all — always last


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
