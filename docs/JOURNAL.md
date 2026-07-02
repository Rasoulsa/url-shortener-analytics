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

## Phase 3 — Analytics Collection & Processing

**Goal:** Turn the Phase 2 Celery foundation into a complete, non-blocking
analytics pipeline: enrich every click with GeoIP + User-Agent data, persist
enriched click events to PostgreSQL, durably flush Redis counters, and expose
time-series stats through a versioned API.

### Branch plan

Worked through Phase 3 in ordered feature branches, each merged via PR to `main`:

```text
feat/d3-click-schema           — clicks table + Phase 3 columns + indexes
feat/d3-analytics-enrichment   — GeoIP, User-Agent, privacy helpers
feat/d3-click-recording        — non-blocking click recording in the task
feat/d3-counter-flush          — Redis→PostgreSQL counter flush (Celery Beat)
feat/d3-stats-api              — analytics stats endpoints
docs/d3-analytics              — full Phase 3 documentation
```

### What I built

**Click event schema (`feat/d3-click-schema`)**

- Finalized the clicks table as the time-series event store:
```text
id, link_id (FK), clicked_at, ip_anonymized, country, city,
browser, os, device_type, referrer, user_agent
```

- Indexes for time-series queries:
```sql
CREATE INDEX ix_clicks_link_clicked_at ON clicks (link_id, clicked_at);
CREATE INDEX ix_clicks_clicked_at      ON clicks (clicked_at);
```
- Alembic migration to add the Phase 3 columns and create the table.

**Enrichment helpers (`feat/d3-analytics-enrichment`)**
- `app/services/geoip.py` — MaxMind GeoLite2 lookup returning `GeoIPLocation(country, city)`. **Fails open:** missing database file, missing `geoip2` package, invalid IP, or IP not in DB all return empty values instead of raising.
- `app/services/user_agent.py` — parses the UA string into `browser`, `os`, and a `device_type` classification (desktop / mobile / tablet / unknown).
- IP anonymization helper — IPv4 last octet zeroed (`203.0.113.45 → 203.0.113.0`), IPv6 truncated to the first 4 groups.

**Non-blocking click recording (`feat/d3-click-recording`)**
- Extended `analytics.process_click_event` to do the full enrichment:
```text
parse User-Agent → browser, os, device_type
GeoIP lookup on RAW ip → country, city
anonymize ip → ip_anonymized (stored)
INSERT clicks row in PostgreSQL
update lightweight Redis analytics counters
```
- **Privacy rule:** GeoIP lookup uses the raw IP for accuracy, but only the anonymized IP is ever persisted. The raw IP never touches PostgreSQL, Redis, or logs.
- Redirect path remains unchanged in shape: resolve → INCR counter → enqueue → return 301/302. Enrichment happens entirely in the worker.

**Counter flush (`feat/d3-counter-flush`)**
- Added `analytics.flush_click_counters`, scheduled by **Celery Beat** every ~30 seconds.
- Uses Redis `GETDEL` (atomic get-and-delete) so an `INCR` landing between a `GET` and a `DEL` can never lose a click.
- On DB failure after `GETDEL`, the counter value is restored to Redis and the task retries (max 3, exponential backoff). No clicks lost.
- Added a `beat` service to `docker-compose.yml`.

**Stats API (`feat/d3-stats-api`)**
- New router `app/api/v1/analytics.py` under `/api/v1/analytics`, four focused endpoints:
```text
GET /api/v1/analytics/overview
GET /api/v1/analytics/links/{short_code}/overview
GET /api/v1/analytics/links/{short_code}/timeseries
GET /api/v1/analytics/links/{short_code}/breakdown?dimension=...
```
- `breakdown` supports six dimensions via a single `dimension` enum: `country`, `city`, `browser`, `os`, `device_type`, `referrer`.
- Shared query params: `days` (1–365, default 30), or explicit `from`/`to` ISO-8601 datetimes; `breakdown` adds `limit` (1–100, default 10).
- All queries hit the PostgreSQL `clicks` table directly (full enriched data), not the Redis counters. Every response carries the exact date range in `meta`.

### Key decisions

**GeoIP lookup on raw IP, store anonymized IP**
Anonymizing before lookup would zero the last octet and destroy subnet-level
precision, badly degrading city accuracy. So lookup uses the raw IP; only the
anonymized form is stored. The raw IP is transient in worker memory only.

**GeoIP fails open**
GeoIP is optional context. A missing MaxMind file must never stop a click from
being recorded. Every failure mode returns NULL country/city and the click is
still persisted.

**`GETDEL` for counter flush**
`GET` + `DEL` is a race: an `INCR` between the two erases a click. `GETDEL` is
one atomic op. Combined with restore-on-failure, the flush is both race-free
and lossless.

**Four focused stats endpoints over one combined endpoint**
Each endpoint maps to one query — simpler to test and cache. `breakdown`
folds all six dimensions into one route via an enum rather than proliferating
endpoints. Clients (and the Phase 4 dashboard) fetch only what they render.

**Stats query PostgreSQL, not Redis counters**
Redis counters are a hot-path optimization without the enriched fields.
PostgreSQL `clicks` has the full data and SQL `GROUP BY` handles arbitrary
ranges cleanly. Avoids Redis/PG dual-consistency concerns for reads.

**Index the `clicks` table, don’t partition yet**
Composite indexes are sufficient at evaluation scale and far simpler than
partition management. Monthly `RANGE` partitions on `clicked_at` are documented
as the future path once rows reach millions.

### Validation performed

**Click enrichment end-to-end**

- Fired redirects with a spoofed public test IP and a real browser UA:
```bash
curl -i \
  -H "X-Forwarded-For: 81.2.69.142" \
  -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126 Safari/537.36" \
  -H "Referer: https://google.com" \
  http://localhost:8000/{short_code}
```
- Confirmed the `clicks` row: `ip_anonymized = 81.2.69.0`, `country = United Kingdom`, `city = London`, `browser = Chrome`, `os = Windows`, `device_type = desktop`, referrer captured.

**GeoIP service directly**
```bash
docker compose exec -T worker python - <<'PY'
from app.services.geoip import lookup_geoip
for ip in ["8.8.8.8", "81.2.69.142", "127.0.0.1"]:
    print(ip, lookup_geoip(ip))
PY
```
- `81.2.69.142` → London, UK (city works).
- `8.8.8.8` / `1.1.1.1` → country only, no city — expected for infra/CDN IPs.
- `127.0.0.1` and Docker `172.x.x.x` → empty — expected for private IPs.

**Counter flush**

- Confirmed `analytics.flush_click_counters` registered and firing on the Beat schedule; watched a Redis counter drain to `links.click_count` after ~30s.
Verified a spot check: short_code `statstest1782867762` reached `click_count = 30`.

**Stats API**
```bash
curl "http://localhost:8000/api/v1/analytics/links/{short_code}/overview"     -H "X-API-Key: $API_KEY"
curl "http://localhost:8000/api/v1/analytics/links/{short_code}/timeseries?days=7" -H "X-API-Key: $API_KEY"
curl "http://localhost:8000/api/v1/analytics/links/{short_code}/breakdown?dimension=country" -H "X-API-Key: $API_KEY"
```
- Confirmed correct envelopes, `meta` date ranges, and all six breakdown dimensions.

**Test suite**

- Full suite green: 54 tests passing.

### Documentation updated
- `README.md` — flipped Phase 3 features to done, added analytics API section, analytics validation block, updated tasks list and limitations.
- `docs/ANALYTICS.md` — **new** — full pipeline doc (flow, schema, Redis keys, tasks, stats API, validation, failure behavior, checklist).
- `docs/ARCHITECTURE.md` — Phase 3 diagram, `flush_click_counters` task, Beat, clicks ERD, analytics keyspace, full request flow, GeoIP validation.
- `docs/ASSUMPTIONS.md` — moved completed items out of limitations, added raw-IP-lookup and `GETDEL` flush assumptions, added GeoIP coverage note.
- `docs/DESIGN_DECISIONS.md` — added six Phase 3 decisions (raw-IP lookup, fail-open GeoIP, `GETDEL` flush, four-endpoint stats API, PG-not-Redis reads, index-not-partition) plus a trade-offs summary.
- `docs/GEOIP_SETUP.md` — download/extract/mount/restart flow, verification snippet, troubleshooting table, raw-lookup/anonymized-storage privacy note.
- `docs/API.md` — replaced the analytics placeholder with all four real endpoints and full parameter tables.

### Blockers / notes
- `clicks` **table missing / DuplicateTable during migration**. Hit an Alembic ordering issue where an enrichment migration referenced `clicks` before it existed, and later a `DuplicateTable` because the table already existed. Resolved by ordering the schema migration (`feat/d3-click-schema`) first and reconciling revision history.
- **`permission denied ... /home/appuser/.cache/uv` when running Alembic via `uv run` inside the container.** Worked around by invoking `alembic` directly: `docker compose exec api alembic upgrade head`.
- **CI mypy error** in `_run_async` in `app/tasks/analytics.py` around missing type parameters — fixed so the quality gate stays green.
- **`c.ip_address column does not exist`** — early query referenced the raw-IP column name; corrected to `ip_anonymized` (the raw IP is never stored).
- **Empty country/city for `8.8.8.8`, `1.1.1.1`, `127.0.0.1`**. Confirmed this is expected: local IPs are not public, and infra/CDN IPs often lack city data in GeoLite2. Used `81.2.69.142` (MaxMind test IP → London) to prove city lookup works.
- **`curl -I` (HEAD) may not register a click** — used `GET` for click tests.
- **GeoIP service placement** — decided to put lookup logic in `app/services/geoip.py`(service layer) and keep the root `geoip/` directory strictly for the gitignored `.mmdb` data file.

### Current limitations after Phase 3
- Webhooks on click thresholds not implemented yet (future).
- Analytics dashboard is Phase 4 work.
- `clicks` table is indexed but not partitioned yet.
- GeoIP city coverage depends on MaxMind data; some IPs return country only.
- No JWT/OAuth yet.
- No email verification yet.
- No soft delete yet.
- Single-region deployment only.

## Phase 4 — Public API, Webhooks & Analytics Dashboard

**Goal:** Turn the service into a documented public product: a versioned API
with a stable contract, OpenAPI/Swagger docs, cursor-pagination verified across
listings, click-threshold webhooks delivered asynchronously, and an analytics
dashboard that visualizes the Phase 3 stats.

### Branch plan

Worked through Phase 4 in ordered feature branches, each merged via PR to `main`:

```text
feat/d4-openapi-docs    — OpenAPI/Swagger polish + formalize /api/v1 versioning
feat/d4-api-envelope    — response envelope audit + cursor pagination verify
feat/d4-webhooks        — click-threshold webhooks (HMAC, Celery retry, idempotent)
feat/d4-dashboard-api   — aggregation endpoints (multi-link compare) for charts
feat/d4-dashboard-ui    — Jinja2 + Chart.js dashboard at /dashboard
test/d4-tests           — cross-cutting tests (envelope, webhooks, dashboard)
ci/d4-pipeline          — keep CI green (ruff, ruff-format, mypy, pytest)
docs/d4-final           — final documentation pass across all docs
```

### What I built

**OpenAPI docs & versioning (`feat/d4-openapi-docs`)**
- Formalized all public routes under `/api/v1/` as the stable API surface.
- Added router tags, summaries, descriptions, and response-model examples so
  `/docs` (Swagger) and `/redoc` render a clean, self-describing API.
- Documented the API-key security scheme so protected endpoints show the auth
  requirement in Swagger.
- `/openapi.json` is generated directly from the Pydantic models and route
  signatures, so docs stay in sync with the code.

**Envelope audit & pagination (`feat/d4-api-envelope`)**
- Audited every endpoint to guarantee the `{ data, meta, errors }` envelope,
  including error paths.
- Added/confirmed unified exception handlers mapping `400`, `401`, `404`,
  `410`, `422`, `429`, and `500` into the same envelope shape with a
  machine-readable `code`.
- Verified cursor pagination `meta` shape (`next_cursor`, `limit`) is
  consistent across link listings.

**Webhooks (`feat/d4-webhooks`)**
- Added `webhook_url`, `webhook_threshold`, and `webhook_fired` handling on links.
- Wired threshold detection into `analytics.flush_click_counters` — the task
  that owns the authoritative `click_count` update — so webhooks fire off the
  background flush, never the redirect hot path.
- `webhook_fired` is set to `true` inside the same flush transaction that
  detects the crossing, *before* enqueueing delivery — a single-flight
  idempotency guard so the event is scheduled at most once per link.
- Delivery runs in a dedicated Celery task with retry/backoff for transient
  failures (timeouts, connection errors, receiver `5xx`).
- Payloads are signed with HMAC SHA-256 and sent as
  `X-Webhook-Signature: sha256=<hex>` so receivers can verify authenticity.

**Dashboard data (`feat/d4-dashboard-api`)**
- Added a multi-link comparison endpoint returning aligned, zero-filled series
  for several short codes over one shared window, so the chart receives a
  single ready-to-render payload.
- Reused the Phase 3 stats endpoints (`timeseries`, `breakdown`) for the line
  chart, country table, top referrers, and top browsers.

**Dashboard UI (`feat/d4-dashboard-ui`)**
- Built `/dashboard` with Jinja2 templates and Chart.js.
- Views: 7/30/90-day visits line chart, geographic breakdown as a country
  **table**, top referrers, top browsers, and a multi-link comparison chart.
- The UI stays thin — it calls the `/api/v1/analytics/*` endpoints and renders
  the results; all aggregation stays in the backend.

**Tests (`test/d4-tests`)**
- Added cross-cutting tests for the response envelope contract, webhook
  behavior, and dashboard endpoints to cover the Phase 4 code paths.

**CI (`ci/d4-pipeline`)**
- Kept the pipeline green across `ruff`, `ruff-format`, `mypy`, and `pytest`
  with the new code.

### Key decisions

**Explicit `/api/v1/` versioning**
URL-based versioning gives clients a stable, visible contract and leaves room
for `/api/v2/` later without breaking existing integrations.

**OpenAPI as the living contract**
Generating docs from the code (models + route signatures) avoids a separate
spec that drifts. Tags, summaries, and response models keep Swagger useful.

**Webhooks fire from the flush task, not the redirect**
The redirect only does `INCR`; it must never make outbound HTTP calls. The
flush task owns the durable `click_count`, making it the correct place to
observe threshold crossings. Trade-off: webhooks are eventually consistent —
they fire on the next flush after the threshold, not during the exact click.

**`webhook_fired` idempotency guard**
Setting the flag before enqueueing, inside the flush transaction, guarantees a
single delivery per link even if flushes overlap or the task retries.

**HMAC-signed payloads**
A GitHub-style `sha256=` signature lets receivers verify authenticity and
integrity cheaply. Receivers must implement verification — a standard cost.

**Backend multi-link aggregation**
Aligning dates and zero-filling missing days once on the server produces a
correct, single chart payload and avoids N client requests plus browser-side
merge logic.

**Jinja2 + Chart.js, country table (no map)**
No separate frontend build pipeline; FastAPI serves both API and dashboard. A
country table satisfies the requirement without a map library, external map
API keys, or handling incomplete GeoIP data.

### Validation performed

**Webhook end-to-end**
- Ran a local receiver on `http://0.0.0.0:9999/webhook`:
```bash
python - <<'PY'
from http.server import BaseHTTPRequestHandler, HTTPServer
class H(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("Content-Length", "0"))
        print("HEADERS:", dict(self.headers))
        print("BODY:", self.rfile.read(n).decode())
        self.send_response(200); self.end_headers(); self.wfile.write(b"ok")
HTTPServer(("0.0.0.0", 9999), H).serve_forever()
PY
```
- Created a link with `webhook_url` and `webhook_threshold=3`, drove clicks
  past the threshold, and confirmed the receiver printed the signed payload
  (`event`, `short_code`, `click_count`, `threshold`, `occurred_at`) with the
  `X-Webhook-Signature` header. Confirmed it fired exactly once (idempotency).

**Dashboard & stats**
- Loaded `/dashboard` and verified the 7/30/90-day line chart, country table,
  top referrers, top browsers, and multi-link comparison chart render from the
  analytics endpoints.
- Spot-checked `timeseries` for short code `webhooktest1782936524` showing
  clicks on `2026-07-01`.
- Confirmed comparison and analytics endpoints return `404 Link not found` for
  unknown codes (e.g. `othercode`).

**API docs & envelope**
- Verified `/docs`, `/redoc`, and `/openapi.json` render the versioned routes,
  auth scheme, and response models.
- Confirmed success and error responses share the `{ data, meta, errors }`
  shape.

**CI**
- `ruff check`, `ruff format --check`, `mypy`, and `pytest` all green.

### Documentation updated
- `README.md` — flipped Phase 4 features to done, added Phase 4 section
  (Public API, dashboard, webhooks, branch map), webhook usage example, updated
  limitations.
- `docs/PHASE4_FINAL.md` — **new** — consolidated Phase 4 summary.
- `docs/API.md` — added Dashboard Data (multi-link compare) and Webhooks
  sections, documented webhook fields in the create response, added `/dashboard`.
- `docs/ARCHITECTURE.md` — added the webhook firing flow, a Public API &
  Dashboard architecture section (envelope, cursor pagination, dashboard layer),
  webhook task in the registered list, and webhook failure rows.
- `docs/DESIGN_DECISIONS.md` — added the Phase 4 decisions (versioning, OpenAPI,
  envelope audit, webhook trigger point, idempotency, HMAC, backend
  aggregation, dashboard) plus a Phase 4 trade-offs summary.
- `docs/ANALYTICS.md` / `docs/ASSUMPTIONS.md` / `docs/LOCAL_DEVELOPMENT.md` —
  Phase 4 dashboard/webhook notes and validation steps.

### Blockers / notes
- **Ruff version mismatch between `uv` and pre-commit.** `uv run ruff format`
  formatted files with Ruff `0.15.20`, but the `ruff-format` pre-commit hook
  reformatted them again with an old pinned `v0.4.4`, causing a CI format loop.
  Fixed by aligning the pre-commit hook `rev` to `v0.15.20` and cleaning the
  pre-commit cache.
- **`ruff format --check` vs `ruff format`.** The `--check` command only reports
  what *would* change; it does not modify files. Running the plain
  `ruff format` was required to actually fix `tests/test_d4_api_contracts.py`.
- **`httpx` + `starlette.testclient` deprecation warning** surfaced in the test
  run; noted for a follow-up but not blocking (tests pass).
- Coverage tuning on Phase 4 code paths was intentionally deferred as a later
  maintenance task; functional Phase 4 work is complete.

### Current limitations after Phase 4
- Single threshold event per link (no multiple thresholds or repeatable events yet).
- `clicks` table is indexed but not partitioned yet.
- GeoIP city coverage depends on MaxMind data; some IPs return country only.
- Dashboard uses a country table rather than a map visualization.
- No JWT/OAuth yet (API-key auth only).
- No email verification yet.
- No soft delete yet.
- Single-region deployment only.

### Project status
Phase 4 complete. The service now provides a documented, versioned public API
with a consistent envelope and cursor pagination, reliable asynchronous
click-threshold webhooks, and an analytics dashboard — closing out the planned
scope for the project.
