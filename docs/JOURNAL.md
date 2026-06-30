# Development Journal

Daily log of decisions, progress, blockers, and trade-offs.
Kept to demonstrate engineering process and reasoning.

---

## Phase 1 — Core Shortening Service

**Goal:** Working end-to-end shorten → redirect with auth,
custom alias, expiry, and password protection.

### What I built

**Project foundation**
- Full folder structure, `pyproject.toml` with `uv`, Ruff lint+format,
  mypy, pre-commit hooks
- Docker Compose: Postgres 16 + Redis 7 + FastAPI, one-command boot
- GitHub: branch protection on `main`, CI workflow, PR/issue templates,
  conventional commits, feature-branch → PR → main workflow

**Database layer**
- `User`, `Link`, `Click` models with SQLAlchemy 2.0 async `mapped_column`
- `Click` designed as a time-series fact table with composite indexes:
  `(link_id, clicked_at)`, `(link_id, country)`, `(link_id, browser)`
  — anticipating Phase 3 aggregation queries from the very start
- Alembic configured with autogenerate; initial migration created

**Authentication**
- API-key model: `secrets.token_urlsafe(32)` at registration
- `get_current_user` and `get_optional_user` FastAPI dependencies
- `POST /api/v1/auth/register` → returns `{data: {id, email, api_key}}`

**Short-code generation**
- Chose **Random Base62 + Redis SETNX** over counter-based approach
- `secrets.choice()` for cryptographic randomness (not `random`)
- SETNX atomically reserves the code before DB insert
  → eliminates the check-then-insert race condition entirely
- DB UNIQUE constraint as the final safety net
- Keyspace: 62^7 ≈ 3.5 trillion — collisions negligible in practice
- Transparent fallback: grow code length after max_tries exhausted

**Link CRUD**
- `POST /api/v1/links` — alias, expiry, password, webhook, 301/302
- `GET /api/v1/links` — cursor/keyset pagination (not offset)
- `GET /api/v1/links/{code}` — single retrieve
- `PATCH /api/v1/links/{code}` — partial update
- `DELETE /api/v1/links/{code}` — hard delete

**Redirect endpoint**
- `GET /{short_code}` — DB lookup → expiry → password gate → 301/302
- `POST /{short_code}/unlock` — password form submission
- Lazy deletion: expiry checked on access (410 Gone), no cleanup cron
- Synchronous click count this phase; TODO markers for Phase 2/3 upgrades
- Clean HTML password gate with bcrypt verification

**Response design**
- `{data, meta, errors}` envelope on every endpoint from Phase 1
- `meta.next_cursor` for cursor pagination

### Key decisions

**Random + SETNX over counter codes**
Counter codes are sequential → enumerable → an attacker can iterate
`abc0001`, `abc0002` and harvest all destination URLs. Random codes
from 62^7 keyspace are not enumerable. SETNX makes reservation atomic.

**Cursor pagination over offset**
`OFFSET 10000 LIMIT 20` forces Postgres to scan and discard 10k rows.
Keyset pagination (`WHERE id < cursor ORDER BY id DESC`) uses the index
directly — constant time at any depth.

**Design the Click table on Phase 1**
Schema changes are cheap before data exists. The composite indexes I
need for Phase 3 aggregations are already in place — no migration
required when analytics land.

**Response envelope from Phase 1**
Retrofitting an envelope on a live API breaks all clients. Consistent
shape from the start means one response handler on the frontend.

**`main`-only branching**
Solo project. `develop` exists to protect `main` from broken
multi-developer integration — that problem doesn't apply here.
Feature branches → PR → main keeps the history clean and professional
without unnecessary complexity.

### Blockers / notes
- Router order critical: `/{short_code}` catch-all must be registered
  **last** in `main.py` or it shadows `/api/*` and `/docs`.
- `python-multipart` required for `Form(...)` in FastAPI. Added to deps.
- `uv sync` generates `uv.lock` automatically — committed to repo for
  reproducible installs in CI and Docker.

### Tomorrow — Phase 2
- Redis cache-aside layer in front of redirect (hot path)
- Write-through click counter (Redis INCR, flushed to DB by Celery)
- Hot-link detection: auto-extend TTL for high-traffic links
- Lazy deletion upgrade: invalidate Redis cache on expired link
- Sliding-window rate limiting (anon by IP, auth by API key)
- Celery worker + beat scaffold (so Phase 3 analytics slot straight in)

---

## Phase 2 — Redis Caching, Counters, Rate Limiting, and Celery

**Goal:** Move the redirect hot path toward a production-style architecture:
fast Redis reads, atomic Redis counters, Redis-backed rate limiting, and
non-blocking analytics task dispatch through Celery.

### What I built

#### Redis cache-aside metadata layer

- Added Redis-backed metadata cache for redirects.

- Cache key format:
```text
link:{short_code}:meta
```

- Cached only redirect-required fields:
    - short_code
    - long_url
    - expires_at
    - is_permanent
    - password_hash

- Redirect flow now checks Redis first.

- On cache hit, redirect can happen without PostgreSQL lookup.

- On cache miss, API loads from PostgreSQL and stores metadata in Redis with TTL.

- PostgreSQL remains the source of truth.

- Redis is only a performance layer.

#### Redis write-through click counters

- Added Redis click counter key:
```text
link:{short_code}:clicks
```

- Redirect path increments Redis with atomic `INCR`.

- If Redis counter increment fails, the API falls back to PostgreSQL increment.

- This reduces PostgreSQL write pressure on high-volume redirects.

- Redis counter flushing to durable PostgreSQL aggregates remains a future
Celery/Day 3 improvement.

#### Sliding-window rate limiting

- Added Redis-backed sliding-window rate limiting.

- Implemented route classes:
```text
┌────────────────────────────┬─────────────────────────────┬──────────────────────────────────────┐
│ ROUTE TYPE                 │ IDENTIFIER                  │ PURPOSE                              │
├────────────────────────────┼─────────────────────────────┼──────────────────────────────────────┤
│ POST /api/v1/auth/register │ Client IP                   │ Strict registration abuse protection │
├────────────────────────────┼─────────────────────────────┼──────────────────────────────────────┤
│ /api/v1/*                  │ API key, fallback to IP     │ API abuse protection                 │
├────────────────────────────┼─────────────────────────────┼──────────────────────────────────────┤
│ /{short_code}              │ Client IP                   │ Redirect abuse protection            │
└────────────────────────────┴─────────────────────────────┴──────────────────────────────────────┘
```

- Rate-limit Redis key formats:
```text
rate_limit:auth:{identifier_hash}
rate_limit:api:{identifier_hash}
rate_limit:redirect:{identifier_hash}
```

- Identifiers are hashed before storage so raw API keys and raw IP addresses are
not stored directly in Redis keys.

- Chose sliding-window instead of fixed-window to avoid boundary bursts.

- Exceeded limits return `429` Too Many Requests with:

    - `Retry-After`
    - `X-RateLimit-Limit`
    - `X-RateLimit-Remaining`

#### Celery worker setup

- Added Celery worker container.
- Redis is used as Celery broker and result backend.
- Registered tasks:
    - `health.ping`
    - `analytics.process_click_event`
- Redirects enqueue analytics work without waiting for enrichment.
- Redirect success does not depend on Celery worker health.
- Worker healthcheck uses Celery inspection, not HTTP.

#### Redis logical DB separation

- Split Redis usage by logical database:
```text
┌──────────┬─────────────────────────┬────────────────────────────────────────────────────────────-──┐
│ REDIS DB │ URL                     │ PURPOSE                                                       │
├──────────┼─────────────────────────┼────────────────────────────────────────────────────────────-──┤
│ DB 0     │ redis://redis:6379/0    │ API cache, click counters, rate-limit keys, analytics counters│
├──────────┼─────────────────────────┼────────────────────────────────────────────────────────────-──┤
│ DB 1     │ redis://redis:6379/1    │ Celery broker                                                 │
├──────────┼─────────────────────────┼────────────────────────────────────────────────────────────-──┤
│ DB 2     │ redis://redis:6379/2    │ Celery result backend                                         │
└──────────┴─────────────────────────┴────────────────────────────────────────────────────────────-──┘
```

- This keeps app cache/counter keys separate from Celery queue/result keys.

#### Failure behavior

- Documented and designed expected degradation paths:
```text
┌──────────────────────────────────┬──────────────────────────────────────────────┐
│ FAILURE                          │ BEHAVIOR                                     │
├──────────────────────────────────┼──────────────────────────────────────────────┤
│ Redis cache unavailable          │ Fall back to PostgreSQL lookup               │
├──────────────────────────────────┼──────────────────────────────────────────────┤
│ Redis click counter unavailable  │ Fall back to PostgreSQL click increment      │
├──────────────────────────────────┼──────────────────────────────────────────────┤
│ Redis rate limiter unavailable   │ Fail open and allow request                  │
├──────────────────────────────────┼──────────────────────────────────────────────┤
│ Celery broker unavailable        │ Log warning; redirect still succeeds         │
├──────────────────────────────────┼──────────────────────────────────────────────┤
│ Celery worker unavailable        │ Tasks may queue; redirect still succeeds     │
├──────────────────────────────────┼──────────────────────────────────────────────┤
│ PostgreSQL unavailable           │ API management and cache misses fail normally│
└──────────────────────────────────┴──────────────────────────────────────────────┘
```

### Validation performed

#### Docker services

- Rebuilt and restarted Docker Compose stack.
- Verified services:
    - `api`
    - `db`
    - `redis`
    - `worker`
- Confirmed containers became healthy after fixing worker healthcheck behavior.

#### Redirect validation

- Created short links through the API.
- Tested redirect endpoint.
- Confirmed expected HTTP `302` response to original long URL.

#### Redis metadata cache validation

- Created aliases such as:
```text
cachetest1782814996
```

- Triggered redirect.

- Checked Redis key:
```text
link:cachetest1782814996:meta
```

- Confirmed metadata was cached with positive TTL.

#### Redis click counter validation

- Created aliases such as:
```text
countertest1782823248
countertest1782823999
```

- Triggered redirects multiple times.

Checked Redis key:
```text
link:{short_code}:clicks
```

- Also inspected PostgreSQL links.click_count during fallback/debugging.

#### Celery validation

- Checked registered tasks with:
```bash
docker compose exec worker celery -A app.tasks.celery_app:celery_app inspect registered
```

- Expected registered tasks:

    - `analytics.process_click_event`
    - `health.ping`

- Tested worker ping with Celery inspection.

- Tested health task from API container and expected result:
```text
pong
```

#### Redis DB separation validation

- Checked DB 0, DB 1, and DB 2 with redis-cli.
- Confirmed DB 0 is for application keys.
- Confirmed DB 1 is for Celery broker keys.
- Confirmed DB 2 is for Celery result backend keys.

### Documentation updated

Updated or prepared documentation for Phase 2:

- `docs/DESIGN_DECISIONS.md`
    - Added Day 2 Redis caching, counters, rate limiting, Celery section.
    - Documented Redis DB separation.
    - Documented cache-aside metadata.
    - Documented click counters.
    - Documented sliding-window rate limiting.
    - Documented Celery analytics flow.
    - Documented failure behavior.

- `docs/ASSUMPTIONS.md`
    - Added Phase 2 infrastructure assumptions.
    - Clarified PostgreSQL as source of truth.
    - Clarified Redis as performance/coordination layer.
    - Clarified failure behavior for Redis and Celery.
    - Clarified analytics eventual consistency.

- `docs/LOCAL_DEVELOPMENT.md`
    - Added Phase 2 Redis/Celery validation commands.
    - Added Redis DB inspection commands.
    - Added metadata cache test.
    - Added click counter test.
    - Added rate-limit test.
    - Added Celery registered task and health task checks.
    - Added worker healthcheck note.

- `docs/API.md`
    - Added rate-limit response documentation.
    - Added `429 Too Many Requests` response shape.
    - Added rate-limit headers.
    - Added route class table.
    - Added Docker local port note.

#### Key decisions

**PostgreSQL remains source of truth**
Redis is intentionally not authoritative. If Redis is cleared, restarted, or
unavailable, link/user data remains correct in PostgreSQL.

**Cache-aside over write-through metadata cache**
Cache-aside keeps the implementation simple and safe. The cache is populated on
miss and can always be rebuilt from PostgreSQL.

**Redis counters over synchronous database writes**
The redirect route is the hottest path. Redis INCR is atomic and much cheaper
than one PostgreSQL update per redirect.

**Sliding-window over fixed-window rate limiting**
Fixed windows allow boundary bursts:
```text
59 requests at 12:00:59
59 requests at 12:01:00
```

That can allow almost double the intended rate in a very short time.
Sliding-window enforcement is smoother and more accurate.

**Rate limiting fails open**
If Redis is unavailable, the limiter allows requests instead of blocking all
traffic. Availability is more important than strict abuse protection during a
Redis outage.

**Celery is optional for redirect correctness**
Analytics should not block redirects. If the broker or worker is unavailable,
redirects should still succeed.

**Separate Redis DBs**
Using DB 0, DB 1, and DB 2 avoids mixing application cache keys with Celery
broker/result keys.

#### Blockers / notes

- Celery worker does not expose HTTP, so curl localhost:8000 is not a valid
worker healthcheck.

- Worker healthcheck should use:
```bash
celery -A app.tasks.celery_app:celery_app inspect ping --timeout=5
```

- In zsh, Redis keys with variables should use braces:
```bash
"link:${ALIAS}:clicks"
```

not:
```bash
"link:$ALIAS:clicks"
```

- Some Docker/PyPI/Docker Hub network operations may fail temporarily due to
connection timeouts or TLS handshake timeouts. Re-running usually resolves it.

- GitHub CI/mypy surfaced type-checking issues around Redis cache service code,
which should stay part of the quality gate.

- Redis `KEYS *` is acceptable for local debugging but should not be used in
production operational paths.

### Current limitations after Phase 2
- `clicks` table is not partitioned yet.
- Redis counters are not durably flushed to PostgreSQL on a schedule yet.
- Analytics enrichment is not complete yet.
- No JWT/OAuth yet.
- No email verification yet.
- No soft delete yet.
- Single-region deployment only.
- GeoIP is optional and may be unavailable if MaxMind database is not installed.

---

## Phase 3 — *(to be completed)*
## Phase 4 — *(to be completed)*
