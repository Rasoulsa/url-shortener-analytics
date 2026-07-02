# Technologies, Frameworks & Libraries

## Core Stack

| Tool | Version | Purpose | Why chosen |
|------|---------|---------|------------|
| **FastAPI** | ≥0.111 | Web framework | Async-native, type-driven, auto Swagger/OpenAPI |
| **PostgreSQL** | 16 | Primary database | ACID, composite indexes, reliable, widely supported |
| **Redis** | 7 | Cache / counters / rate-limit / SETNX | Sub-ms latency, atomic operations |
| **Celery** | ≥5.4 | Async task queue + periodic scheduler (Beat) | Non-blocking analytics, retry/backoff built-in, Beat handles scheduled counter flushing |
| **SQLAlchemy** | ≥2.0 | Async ORM | Modern typed `mapped_column`, async engine |
| **Alembic** | ≥1.13 | DB migrations | Autogenerate, versioned, rollback support |
| **Pydantic v2** | ≥2.7 | Validation + settings | Fast, typed, `pydantic-settings` for env config |
| **asyncpg** | ≥0.29 | Async Postgres driver | Fastest async Postgres driver for Python |

## Analytics & Enrichment

| Tool | Version | Purpose | Why chosen |
|------|---------|---------|------------|
| **geoip2** | ≥4.8 | IP → country/city | Offline (MaxMind file), no external API dependency; fails open (returns empty country/city) if the database file or package is unavailable, so it's never a hard dependency |
| **user-agents** | ≥2.2 | UA string parsing | Browser, OS, and device-type (desktop/mobile/tablet) extraction |

## Security

| Tool | Version | Purpose | Why chosen |
|------|---------|---------|------------|
| **passlib[bcrypt]** | ≥1.7 | Password hashing | Industry standard, bcrypt is time-tested |
| **secrets** (stdlib) | — | API key + code gen | Cryptographically secure randomness, no extra dep |

## Infrastructure

| Tool | Purpose | Why chosen |
|------|---------|------------|
| **Docker** | Containerization | Reproducible environments everywhere |
| **Docker Compose** | Local orchestration (`api`, `worker`, `beat`, `db`, `redis`) | One-command dev stack |
| **Uvicorn** | ASGI server (dev) | Fast, supports `--reload` |
| **Gunicorn** | Process manager (production) | Worker management, battle-tested |

## Developer Tooling

| Tool | Version | Purpose | Why chosen |
|------|---------|---------|------------|
| **uv** | latest | Package manager + lock file | 10-100x faster than pip, exact lock file |
| **Ruff** | ≥0.15 | Lint + format | Replaces flake8 + isort + black in one tool, extremely fast |
| **mypy** | ≥1.10 | Static type checking | Catches type errors before runtime |
| **pytest** | ≥8.2 | Testing | Industry standard, async support |
| **pytest-asyncio** | ≥0.23 | Async test runner | Required for async FastAPI endpoints |
| **pre-commit** | ≥3.7 | Git hooks | Enforces quality on every commit |
| **GitHub Actions** | — | CI/CD | Free, native GitHub integration |
| **respx** | ≥0.21 | Mock `httpx` in tests | Test webhook delivery without real HTTP calls |

## Redis

Redis is used for:

- Link metadata cache
- Click counters (write-through buffer, drained by Celery Beat)
- Rate-limit state
- Lightweight analytics counters
- Celery broker/result backend through separate Redis DBs

Redis DB usage:

| DB | Purpose |
|---|---|
| 0 | Application cache/counters/rate limits/analytics |
| 1 | Celery broker |
| 2 | Celery result backend |

Celery handles three kinds of non-blocking background work:

- **`analytics.process_click_event`** — enriches each click (GeoIP lookup,
  User-Agent parsing, IP anonymization) and persists it to the PostgreSQL
  `clicks` table. Triggered per-request; the redirect path enqueues the event
  and returns the response without waiting for it.
- **`analytics.flush_click_counters`** — scheduled by **Celery Beat** every
  ~30 seconds. Atomically drains (`GETDEL`) Redis click counters into
  `links.click_count` in PostgreSQL. On failure, the counter value is restored
  to Redis and the task retries with backoff, so counts are never lost. Also
  detects click-threshold crossings and enqueues webhook delivery.
- **`webhooks.send_webhook_event`** — POSTs an HMAC-signed payload to the configured
  `webhook_url` when a link's `click_count` crosses `webhook_threshold`.
  Runs with retry/backoff for transient failures. The `webhook_fired` flag
  ensures delivery happens at most once per link.

Celery Beat runs as its own `beat` service in Docker Compose — it only
schedules tasks, it doesn't execute them; execution happens in `worker`.

## Frontend

| Tool | Purpose |
|------|---------|
| **Chart.js** | Line charts, multi-link comparison chart — consumes the Phase 3 analytics API |
| **Jinja2** | Server-side HTML templating for the `/dashboard` route |

Dashboard views: visits line chart (7/30/90-day toggle), geographic breakdown
country table, top referrers, top browsers, and multi-link comparison chart.
No external map library or build pipeline is required.

## Webhooks

| Tool | Version | Purpose | Why chosen |
|------|---------|---------|------------|
| **httpx** | ≥0.27 | Async HTTP client for webhook delivery | Native asyncio support, connection pooling, matches async stack |
| **hmac / hashlib** (stdlib) | — | Webhook payload signing | No extra dependency; standard HMAC-SHA256 receiver verification pattern |
| **secrets** (stdlib) | — | Per-webhook signing secret generation | Already used for API keys/short codes; cryptographically secure |

Webhook delivery runs as a Celery task on the existing `worker` service — no
new container required. Delivery is triggered from `analytics.flush_click_counters`
at the moment a link's persisted `click_count` crosses the configured threshold.

Key properties:
- **Idempotent:** `webhook_fired` is set before the task is enqueued so the
  event is scheduled at most once per link even if flush runs overlap.
- **Resilient:** retry/backoff for transient receiver failures; a permanently
  failing receiver is logged and does not spam the link owner.
- **Signed:** `X-Webhook-Signature: sha256=<hmac_hex_digest>` lets receivers
  verify authenticity without a separate secret exchange mechanism.
- **Non-blocking:** threshold detection and delivery never touch the redirect
  hot path; the redirect only performs `INCR`.
