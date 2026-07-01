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
| **Gunicorn** | Process manager (prod, Phase 4) | Worker management, battle-tested |

## Developer Tooling

| Tool | Version | Purpose | Why chosen |
|------|---------|---------|------------|
| **uv** | latest | Package manager + lock file | 10-100x faster than pip, exact lock file |
| **Ruff** | ≥0.4 | Lint + format | Replaces flake8 + isort + black in one tool, extremely fast |
| **mypy** | ≥1.10 | Static type checking | Catches type errors before runtime |
| **pytest** | ≥8.2 | Testing | Industry standard, async support |
| **pytest-asyncio** | ≥0.23 | Async test runner | Required for async FastAPI endpoints |
| **pre-commit** | ≥3.7 | Git hooks | Enforces quality on every commit |
| **GitHub Actions** | — | CI/CD | Free, native GitHub integration |

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

## Celery

Celery handles two kinds of non-blocking background work:

- **`analytics.process_click_event`** — enriches each click (GeoIP lookup,
  User-Agent parsing, IP anonymization) and persists it to the PostgreSQL
  `clicks` table. Triggered per-request; the redirect path enqueues the event
  and returns the response without waiting for it.
- **`analytics.flush_click_counters`** — scheduled by **Celery Beat** every
  ~30 seconds. Atomically drains (`GETDEL`) Redis click counters into
  `links.click_count` in PostgreSQL. On failure, the counter value is restored
  to Redis and the task retries with backoff, so counts are never lost.

Celery Beat runs as its own `beat` service in Docker Compose — it only
schedules tasks, it doesn't execute them; execution happens in `worker`.

## Frontend (Phase 4)

| Tool | Purpose |
|------|---------|
| **Chart.js** | Analytics dashboard charts (time-series, country/browser/device breakdowns) |
| **Jinja2** | Server-side HTML templating |

Also planned for Phase 4: optional webhook firing when a link's click count
crosses a configured threshold (not yet implemented as of Phase 3).
