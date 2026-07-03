from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.core.config import settings
from app.core.envelope import error_body
from app.core.redis_client import redis_client
from app.services.rate_limiter import check_rate_limit


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Redis-backed sliding-window rate limiting middleware."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if not settings.rate_limit_enabled:
            return await call_next(request)

        path = request.url.path

        if _should_skip_rate_limit(path):
            return await call_next(request)

        key, limit = _build_rate_limit_key_and_limit(request)

        result = await check_rate_limit(
            redis_client,
            key=key,
            limit=limit,
            window_seconds=settings.rate_limit_window_seconds,
        )

        if not result.allowed:
            return JSONResponse(
                status_code=429,
                content=error_body(
                    code="rate_limit_exceeded",
                    message="Too many requests. Please try again later.",
                    meta={
                        "limit": result.limit,
                        "remaining": result.remaining,
                        "retry_after_seconds": result.retry_after_seconds,
                    },
                ),
                headers={
                    "Retry-After": str(result.retry_after_seconds),
                    "X-RateLimit-Limit": str(result.limit),
                    "X-RateLimit-Remaining": str(result.remaining),
                },
            )

        response = await call_next(request)

        response.headers["X-RateLimit-Limit"] = str(result.limit)
        response.headers["X-RateLimit-Remaining"] = str(result.remaining)

        return response


def _should_skip_rate_limit(path: str) -> bool:
    skipped_paths = {
        "/health",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/favicon.ico",
        # Server-rendered web pages — never rate-limit HTML page loads
        "/",
        "/login",
        "/register",
        "/create",
        "/dashboard",
        "/compare",
        "/links",
    }

    if path in skipped_paths:
        return True

    # Static assets (JS, CSS, images) — never rate-limit
    if path.startswith("/static/"):
        return True

    if path.startswith("/docs/"):
        return True

    return False


def _build_rate_limit_key_and_limit(request: Request) -> tuple[str, int]:
    path = request.url.path

    if path == "/api/v1/auth/register":
        identifier = _client_ip(request)
        return (
            f"rate_limit:auth:{_hash_identifier(identifier)}",
            settings.rate_limit_auth_requests,
        )

    if path.startswith("/api/v1/"):
        api_key = request.headers.get("X-API-Key")

        if api_key:
            identifier = f"api_key:{api_key}"
        else:
            identifier = f"ip:{_client_ip(request)}"

        return (
            f"rate_limit:api:{_hash_identifier(identifier)}",
            settings.rate_limit_api_requests,
        )

    identifier = _client_ip(request)

    return (
        f"rate_limit:redirect:{_hash_identifier(identifier)}",
        settings.rate_limit_redirect_requests,
    )


def _client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("X-Forwarded-For")

    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    if request.client is None:
        return "unknown"

    return request.client.host


def _hash_identifier(identifier: str) -> str:
    return hashlib.sha256(identifier.encode("utf-8")).hexdigest()
