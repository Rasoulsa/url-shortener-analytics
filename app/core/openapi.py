"""OpenAPI / Swagger customization.

Centralizes all schema-level metadata: tags, security schemes, servers,
and the post-processing hook that injects the X-API-Key security
requirement onto every protected route.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

# ── Tag definitions (order controls Swagger UI grouping) ─────────────────────

TAGS_METADATA = [
    {
        "name": "Authentication",
        "description": (
            "Register a new account and retrieve your **API key**. "
            "All other endpoints require the key in the `X-API-Key` header."
        ),
    },
    {
        "name": "Links",
        "description": (
            "Create, read, update and delete short links. "
            "Responses use **cursor/keyset pagination** — pass `cursor` "
            "(the `id` of the last item) to retrieve the next page. "
            "All timestamps are **UTC ISO-8601**."
        ),
    },
    {
        "name": "Analytics",
        "description": (
            "Per-link and portfolio-level click analytics. "
            "Supports date-range filtering (`from` / `to` / `days`), "
            "daily time-series, and dimension breakdowns "
            "(country, city, browser, OS, device type, referrer)."
        ),
    },
    {
        "name": "System",
        "description": "Health check and liveness probes. No authentication required.",
    },
]

# ── Security scheme ───────────────────────────────────────────────────────────

API_KEY_SCHEME_NAME = "ApiKeyHeader"

SECURITY_SCHEMES = {
    API_KEY_SCHEME_NAME: {
        "type": "apiKey",
        "in": "header",
        "name": "X-API-Key",
        "description": (
            "Pass your API key in the X-API-Key header. "
            "Obtain a key by calling POST /api/v1/auth/register."
        ),
    }
}

# ── Routes that do NOT require authentication ─────────────────────────────────

_PUBLIC_PATHS = {
    "/health",
    "/api/v1/auth/register",
}


def _is_public(path: str) -> bool:
    """Return True for endpoints that require no API key."""
    if path in _PUBLIC_PATHS:
        return True
    parts = [p for p in path.split("/") if p]
    if len(parts) == 1 and not parts[0].startswith("api"):
        return True
    return False


# ── Long-form API description (shown at top of /docs) ────────────────────────

_API_DESCRIPTION = """
URL Shortener & Analytics API — v1

A production-minded URL shortening service with intelligent Redis caching,
non-blocking analytics (Celery + GeoIP), and a live dashboard.

Authentication
--------------
Every protected endpoint requires an API key in the request header:

    X-API-Key: <your-key>

Obtain a key:

    POST /api/v1/auth/register
    Content-Type: application/json
    { "email": "you@example.com", "password": "s3cur3!" }

Versioning
----------
All API routes are prefixed with /api/v1/

Policy:
- Breaking changes increment the version (/api/v2/).
- Additive changes (new optional fields, new endpoints) are made in-place.
- A deprecated version will be announced with a Sunset response header
  6 months before removal.

Response Envelope
-----------------
Every response — success and error — uses the same envelope:

    {
      "data":   "<payload or null>",
      "meta":   { "next_cursor": "123", "count": 20 },
      "errors": [ { "code": "not_found", "message": "...", "field": null } ]
    }

  Field    | Success        | Error
  ---------|----------------|---------------------------
  data     | Payload        | null
  meta     | Pagination     | {}
  errors   | []             | [{code, message, field?}]

Pagination
----------
Link listings use cursor / keyset pagination:

    GET /api/v1/links?limit=20
    -> meta.next_cursor = "42"

    GET /api/v1/links?limit=20&cursor=42
    -> next page

- cursor is the id of the last item on the previous page.
- limit range: 1-100, default 20.
- Results are ordered newest-first.

Rate Limiting
-------------
  Scope                        | Limit
  -----------------------------|----------------------
  Redirect GET /{short_code}   | 60 req / 60 s per IP
  API endpoints                | Configurable via RATE_LIMIT_* env vars

Rate-limited responses return HTTP 429:

    {
      "data": null,
      "meta": { "retry_after_seconds": 45, "limit": 60, "remaining": 0 },
      "errors": [{ "code": "rate_limit_exceeded", "message": "Too many requests." }]
    }

Error Codes
-----------
  HTTP | code               | Meaning
  -----|--------------------|--------------------------
  401  | unauthorized       | Missing or invalid API key
  403  | forbidden          | Valid key but wrong owner
  404  | not_found          | Resource does not exist
  409  | conflict           | Alias already taken
  410  | gone               | Link has expired
  422  | validation_error   | Request body / query failed validation
  429  | rate_limit_exceeded| Too many requests
  500  | internal_error     | Unexpected server error
"""


# ── Custom schema builder ─────────────────────────────────────────────────────


def build_openapi_schema(app: FastAPI) -> dict:  # type: ignore[type-arg]
    """Generate and cache the OpenAPI schema with security + metadata injected.

    Called once from main.py's app.openapi override. FastAPI caches the
    result on app.openapi_schema after the first call.
    """
    if app.openapi_schema:
        return app.openapi_schema  # type: ignore[return-value]

    schema = get_openapi(
        title="URL Shortener & Analytics API",
        version="1.0.0",
        summary="Production-grade URL shortener with GeoIP analytics.",
        description=_API_DESCRIPTION,
        routes=app.routes,
        tags=TAGS_METADATA,
        servers=[
            {
                "url": "http://localhost:8001",
                "description": "Local development",
            },
            {
                "url": "https://api.example.com",
                "description": "Production (replace with your domain)",
            },
        ],
    )

    # ── Inject security scheme definition into components ─────────────────
    schema.setdefault("components", {})
    schema["components"].setdefault("securitySchemes", {})
    schema["components"]["securitySchemes"].update(SECURITY_SCHEMES)

    # ── Stamp every operation with the correct security requirement ────────
    for path, path_item in schema.get("paths", {}).items():
        for method, operation in path_item.items():
            if method not in {"get", "post", "put", "patch", "delete", "head", "options"}:
                continue
            if not isinstance(operation, dict):
                continue

            if _is_public(path):
                operation["security"] = []
            else:
                operation["security"] = [{API_KEY_SCHEME_NAME: []}]

    app.openapi_schema = schema
    return schema  # type: ignore[return-value]
