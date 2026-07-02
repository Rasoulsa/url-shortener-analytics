# Architecture & Design

## 1. System Overview

```text
              ┌─────────────────────────────────────────────-─┐
  Client ───▶ │  FastAPI Application                          │
              │                                               │
              │  /api/v1/auth      Registration + API key     │
              │  /api/v1/links     CRUD + pagination          │
              │  /api/v1/analytics Time-series stats          │
              │  /{short_code}     Redirect (hot path)        │
              │  /dashboard        Chart.js UI (Phase 4)      |
              │  /health           System status              │
              └──────────────┬──────────────────┬───────────-─┘
                             │                  │
                             │                  │ source of truth
                             │                  │
                 ┌───────────▼───────┐  ┌───────▼───────────-─┐
                 │  Redis DB 0       │  │  PostgreSQL         │
                 │  · metadata cache │  │  · users            │
                 │  · click counters │  │  · links            │
                 │  · rate limits    │  │  · clicks           │
                 │  · SETNX reserve  │  │  · analytics        │
                 │  · analytics tmp  │  └───────▲───────────-─┘
                 └───────────┬───────┘          │
                             │                  │
                             │ enqueue          │ future flush/write
                             │                  │
                 ┌───────────▼────────┐ ┌───────┴──────────-──┐
                 │  Redis DB 1        │ │ Redis DB 2          │
                 │  Celery broker     │ │ Celery results      │
                 └───────────┬────────┘ └───────────────────-─┘
                             │
                 ┌───────────▼─────────────────────────────-──┐
                 │  Celery Worker                             │
                 │  · health.ping                             │
                 │  · analytics.process_click_event           │
                 │  · GeoIP lookup                            │
                 │  · User-agent parsing                      │
                 │  · Counter flush to Postgres (~30s)        │
                 │  · Webhook firing on threshold (Phase 4)   │
                 └──────────────────────────────────────────-─┘
```
The service is built around a FastAPI API layer, PostgreSQL as the primary source of truth, Redis for low-latency infrastructure, and Celery for non-blocking background processing.

Phase 3 adds the Redis and Celery foundation:

- Celery task enriches each click with GeoIP country/city and parsed User-Agent
- Raw IP is used for GeoIP accuracy; only the anonymized IP is persisted
- Celery Beat flushes Redis click counters to PostgreSQL every ~30 seconds
- Time-series stats API exposes per-link breakdowns by day, country, browser, OS, device, and referrer

Phase 4 completes the public product surface:

- Versioned public API under `/api/v1/` with OpenAPI/Swagger docs
- Consistent response envelope `{ data, meta, errors }` and unified exception handling
- Cursor-based pagination for link listings
- Click-threshold webhooks delivered asynchronously via Celery (HMAC-signed, retry/backoff, idempotent)
- Analytics dashboard at `/dashboard` (Jinja2 + Chart.js) reusing the Phase 3 analytics API

## 2. Layered Architecture

```text
┌──────────────────────────────────────────────────┐────────────────────────────
│  API Layer         app/api/v1/*                  │  HTTP, auth, validation    |
├──────────────────────────────────────────────────├────────────────────────────┤
│  Middleware        app/middleware/*              │  CORS, rate limiting       |
├─────────────────────────────────────────────────-├────────────────────────────┤
│  Service Layer     app/services/*                │  Business logic            |
│  shortener · cache · counters · rate limiter     │                            |
│  analytics queue                                 │                            |
├──────────────────────────────────────────────────├────────────────────────────┤
│  Task Layer        app/tasks/*                   │  Celery app + tasks        |
├──────────────────────────────────────────────────┤────────────────────────────┤
│  Data Layer        app/models/*                  │  SQLAlchemy ORM            |
├──────────────────────────────────────────────────├────────────────────────────┤
│  Infrastructure    Postgres · Redis · Celery     │             -              |
└──────────────────────────────────────────────────-────────────────────────────
```

Responsibilities:

- **Routers** stay thin: parse input, apply dependencies, delegate to services.
- **Middleware** handles cross-cutting request concerns such as rate limiting.
- **Services** hold business logic such as short-code generation, cache access, counters, and analytics enqueueing.
- **Tasks** perform asynchronous work outside the request/redirect path.
- **Models** own persistence mapping.
- **PostgreSQL** remains the source of truth.
- **Redis** is used as a performance, coordination, and queueing layer.

## 3. Runtime Components

### FastAPI application

FastAPI exposes:

```text
/api/v1/auth
/api/v1/links
/api/v1/analytics
/{short_code}
/health
```

The redirect route is a catch-all route:

```text
/{short_code}
```

Therefore, router registration order matters. API routers and health routes must be registered before the redirect router.

Correct order:

```python
app.include_router(auth.router)
app.include_router(links.router)

@app.get("/health")
async def health():
    ...

app.include_router(redirect.router)
```

### PostgreSQL

PostgreSQL is authoritative for:

- Users
- API keys
- Links
- Link ownership
- Link expiration
- Password protection metadata
- Durable click events (`clicks` table)
- `links.click_count` — eventually consistent counter flushed from Redis

Redis data can be rebuilt or repopulated from PostgreSQL where applicable.

### Redis

Redis is used for:

```text
Redis DB    URL                     Purpose
────────    ───────────────────     ─────────────────────────────────────────────────────────────
DB 0        redis://redis:6379/0     Application cache, click counters, rate-limit keys, analytics counters
DB 1        redis://redis:6379/1     Celery broker
DB 2        redis://redis:6379/2     Celery result backend
```

Environment variables:

```ini
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2
```

This separation prevents Celery broker/result keys from mixing with application cache keys.

### Celery worker + Beat

Celery is used for background analytics work that should not block redirects.

Worker command:

```bash
celery -A app.tasks.celery_app:celery_app worker \
  --loglevel=INFO \
  --concurrency=2 \
  --queues=default,analytics \
  --hostname=celery@%h
```

Beat command (counter flush scheduler):

```bashe
celery -A app.tasks.celery_app:celery_app beat \
  --loglevel=INFO
```

Registered tasks:

```text
analytics.process_click_event     — enrich + persist one click row (per redirect)
analytics.flush_click_counters    — Redis→PostgreSQL counter flush (Beat, ~30s)
webhooks.deliver                  — POST signed threshold event to webhook_url
health.ping                       — worker liveness check
```
The worker is not an HTTP service, so its healthcheck must use Celery inspection, not `curl`.

Correct worker healthcheck:

```bash
celery -A app.tasks.celery_app:celery_app inspect ping --timeout=5
```

## 4. Data Model (ERD)

```text
users                    links                        clicks
─────                    ─────                        ──────
id          PK     ┌──< id           PK          ┌──< id
email       UQ     │    short_code    UQ INDEX   │    link_id       FK → links.id
hashed_pw          │    long_url                 │    clicked_at    timestamptz
api_key     UQ     │    user_id       FK →users  │    ip_anonymized varchar
created_at         │    password_hash            │    country       varchar (nullable)
                   │    expires_at    INDEX      │    city          varchar (nullable)
                   │    is_permanent             │    browser       varchar (nullable)
                   │    click_count              │    os            varchar (nullable)
                   │    webhook_url              │    device_type   varchar
                   │    webhook_threshold        │    referrer      text (nullable)
                   │    webhook_fired            │    user_agent    text
                   │    created_at               │
                   │    updated_at               │  Indexes:
                   └────                         │  (link_id, clicked_at)
                                                 │  (clicked_at)
                                                 └────
```
`clicks` is the Phase 3 time-series event store. Every redirect enqueues
a Celery task that inserts one enriched row. links.click_count is a
denormalized counter flushed from Redis every ~30 seconds.

## 5. Redis Keyspace

### Link metadata cache

```text
link:{short_code}:meta
```
Example:
```text
link:cachetest1782814996:meta
```
Stores JSON metadata needed for redirect decisions:

```json
{
  "short_code": "abc123",
  "long_url": "https://example.com",
  "expires_at": null,
  "is_permanent": false,
  "password_hash": null
}
```
### Click counter (write-through)

```text
link:{short_code}:clicks
```
Atomic `INCR` on every redirect. Flushed to `links.click_count` by
`analytics.flush_click_counters` using `GETDEL` to avoid double-counting.

Pending flush tracking:

```text
pending_click_counter_flush   (Redis Set of short_codes with unflushed counts)
```

### Short-code reservation

```text
code_reserved:{short_code}
```
Used to reduce race conditions and collisions during short-code generation or custom alias reservation.

### Rate limiting
```text
rate_limit:auth:{identifier_hash}
rate_limit:api:{identifier_hash}
rate_limit:redirect:{identifier_hash}
```


### Analytics counters (Phase 3)

```
analytics:clicks:processed
analytics:link:{short_code}:processed
analytics:link:{short_code}:daily:{YYYY-MM-DD}        TTL: 90 days
analytics:link:{short_code}:country:{country}         TTL: 90 days
analytics:link:{short_code}:browser:{browser}         TTL: 90 days
analytics:link:{short_code}:device:{device_type}      TTL: 90 days
analytics:link:{short_code}:last_event                TTL: 30 days
```
All PII (IP, UA, referrer) is SHA-256 hashed before being written to Redis
summary keys. Raw values are never stored in Redis.

## 6. Request Flows

### Create short link
```text
POST /api/v1/links
  → auth dependency validates X-API-Key
  → validate payload with Pydantic
  → if custom_alias:
        validate alias
        reserve/check uniqueness via Redis SETNX + DB UNIQUE
  → else:
        generate unique Base62 short code
        reserve/check uniqueness via Redis SETNX + DB UNIQUE
  → INSERT links row in PostgreSQL
  → SET link:{short_code}:meta in Redis cache
  → 201 { data: LinkOut }
```

### Redirect — Phase 3 full flow
```text
GET /{short_code}
  → RateLimitMiddleware (sliding-window, Redis sorted set + Lua)
  → Redis GET link:{short_code}:meta
  → HIT:
        validate cached metadata (expiry, password)
        Redis INCR link:{short_code}:clicks
        enqueue analytics.process_click_event(short_code, ip, ua, referrer)
        return 301 or 302 immediately
  → MISS:
        PostgreSQL lookup
        if not found: 404
        if expired: 410
        Redis SET link:{short_code}:meta
        Redis INCR link:{short_code}:clicks
        enqueue analytics.process_click_event(short_code, ip, ua, referrer)
        return 301 or 302 immediately

[Celery worker — analytics queue]
  → parse User-Agent → browser, os, device_type
  → GeoIP lookup on RAW ip → country, city
  → anonymize ip → ip_anonymized (last octet zeroed)
  → INSERT clicks row in PostgreSQL
  → update Redis analytics counters

[Celery Beat — every ~30s]
  → analytics.flush_click_counters
  → GETDEL link:{short_code}:clicks
  → UPDATE links SET click_count = click_count + N
```

**Privacy rule enforced in the worker:**
```python
geoip_info    = lookup_geoip(ip_address)   # raw IP → accurate lookup
ip_anonymized = anonymize_ip(ip_address)   # 8.8.8.8 → 8.8.8.0 (stored)
```

**Webhook firing — Phase 4 flow:**
```text
[Celery Beat — flush_click_counters, every ~30s]
  → GETDEL link:{short_code}:clicks
  → UPDATE links SET click_count = click_count + N
  → for each affected link with webhook_url set:
        if click_count >= webhook_threshold and webhook_fired == false:
            UPDATE links SET webhook_fired = true        # idempotency guard (single-flight)
            enqueue webhooks.deliver(short_code, click_count, threshold)

[Celery worker — webhooks.deliver]
  → build payload { event, short_code, click_count, threshold, occurred_at }
  → sign body: X-Webhook-Signature = sha256=HMAC(secret, body)
  → POST payload to webhook_url
  → on transient failure (timeout / connection / 5xx): retry with backoff
  → on permanent failure: log and stop (webhook_fired stays true)
```

**Idempotency rule:** `webhook_fired` is set to `true` before enqueueing
delivery, inside the same flush transaction that observes the threshold
crossing. This guarantees the threshold event is scheduled at most once, even if
multiple counter flushes run close together.

**Non-blocking rule:** Webhook delivery never runs on the redirect hot path.
The redirect only performs `INCR`; threshold detection and delivery happen in
the background flush + worker.

## 7. Rate Limiting Architecture

Rate limiting is implemented as FastAPI middleware before route handling.

The limiter uses Redis sorted sets and a Lua script for atomic sliding-window checks.

Route classes:

```text
┌────────────────────────────┬─────────────────────────────-─┬──────────────────────────────────┐
│ Route type                 │ Identifier                    │ Purpose                          │
├────────────────────────────┼─────────────────────────────-─┼──────────────────────────────────┤
│ POST /api/v1/auth/register │ Client IP                     │ Registration abuse protection    │
│ /api/v1/*                  │ API key, fallback to client IP│ API abuse protection             │
│ /{short_code} redirects    │ Client IP                     │ Redirect abuse protection        │
└────────────────────────────┴─────────────────────────────-─┴──────────────────────────────────┘
```

Skipped paths:
```text
/health
/docs
/redoc
/openapi.json
/favicon.ico
```

Sliding-window flow:
```text
request
  → build rate_limit:* key
  → remove entries older than window
  → count current entries
  → if count >= limit: return 429
  → else add current request and continue
```

## 8. Public API & Dashboard Architecture (Phase 4)

### Response envelope

All `/api/v1/*` responses are normalized into a single envelope so clients,
tests, and the dashboard parse responses consistently:

```json
{
  "data": {},
  "meta": {},
  "errors": []
}
```

- Success → payload in `data`, pagination/context in `meta`, `errors: []`
- Failure → `data: null`, structured objects in `errors`

Unified exception handlers map application and framework errors to this shape:

```text
┌────────┬──────────────────────┬─────────────────────────────────────────────┐
│ Status │ Code                 │ Meaning                                     │
├────────┼──────────────────────┼─────────────────────────────────────────────┤
│ 400    │ bad_request          │ Malformed request                           │
│ 401    │ unauthorized         │ Missing / invalid API key                   │
│ 404    │ not_found            │ Resource does not exist / not owned         │
│ 410    │ gone                 │ Link expired                                │
│ 422    │ validation_error     │ Pydantic validation failed                  │
│ 429    │ rate_limit_exceeded  │ Rate limit hit                              │
│ 500    │ internal_server_error│ Unexpected error                            │
└────────┴──────────────────────┴─────────────────────────────────────────────┘
```

### Cursor pagination

Link listings use keyset/cursor pagination instead of offset pagination. The
cursor is the last seen link `id`; results are ordered by descending `id`.

```text
GET /api/v1/links?limit=20                 → newest 20, meta.next_cursor = last id
GET /api/v1/links?cursor=41&limit=20       → items with id < 41
```

Benefits: stable pages while rows are inserted/deleted, and no expensive
high-offset scans as the table grows. The cursor is treated as opaque by clients.

### Dashboard layer

```text
Browser (/dashboard)
  → Jinja2-rendered HTML shell + Chart.js
  → fetch() calls to /api/v1/analytics/* with the user's API key
        · timeseries        → line chart (7 / 30 / 90 days)
        · breakdown=country → country table
        · breakdown=referrer→ top referrers
        · breakdown=browser → top browsers
        · compare           → multi-link comparison chart
```

Design intent: aggregation stays in the backend (consistent windows,
zero-filled days, GeoIP handling). The dashboard UI stays thin and reuses the
Phase 3 analytics endpoints wherever possible. A country **table** is used for
the geographic breakdown — no map dependency is required for this project scope.

Production website: `www.matinrayaneharyan.ir`

---


### 9. Cache and Queue Failure Behavior

```text
┌────────────────────────────────────┬──────────────────────────────────────────--------────┐
│ Component failure                  │ Expected behavior                                    │
├────────────────────────────────────┼───────────────────────────────────────────--------───┤
│ Redis metadata cache unavailable   │ Fall back to PostgreSQL lookup                       │
├────────────────────────────────────┼───────────────────────────────────────────--------───┤
│ Redis click counter unavailable    │ Fall back to PostgreSQL click increment              │
├────────────────────────────────────┼───────────────────────────────────────────--------───┤
│ Redis rate limiter unavailable     │ Fail open and allow request                          │
├────────────────────────────────────┼───────────────────────────────────────────--------───┤
│ Celery broker unavailable          │ Log warning; redirect still succeeds                 │
├────────────────────────────────────┼──────────────────────────────────────────--------────┤
│ Celery worker unavailable          │ Tasks may queue; redirect still succeeds             │
├────────────────────────────────────┼────────────────────────────────────────────--------──┤
│ GeoIP database missing             │ Click stored with country/city = NULL                │
├────────────────────────────────────┼────────────────────────────────────────────--------──┤
│ Webhook receiver slow / down       │ Celery retries with backoff; redirect unaffected     │
├────────────────────────────────────┼────────────────────────────────────────────--------──┤
│ Webhook permanently failing        │ Logged; webhook_fired stays true (no duplicate spam) │
├────────────────────────────────────┼──────────────────────────────────────────--------────┤
│ PostgreSQL unavailable             │ API management and cache misses fail normally        │
└────────────────────────────────────┴────────────────────────────────────────--------──────┘
```

Design principle:
```text
Redirect availability should not depend on optional analytics processing.
```
PostgreSQL remains the source of truth. Redis and Celery improve performance and scalability but should not make simple redirects fragile.

## 10. Operational Validation

### Check service health
```bash
docker compose ps
```
Expected:
```text
api      healthy
db       healthy
redis    healthy
worker   healthy
beat
```

### Verify Redis DB separation

```bash
docker compose exec redis redis-cli -n 0 keys '*'
docker compose exec redis redis-cli -n 1 keys '*'
docker compose exec redis redis-cli -n 2 keys '*'
docker compose exec redis redis-cli info keyspace
```
Expected:
```text
db0 -> application cache/counter/rate-limit/analytics keys
db1 -> Celery broker keys
db2 -> Celery result keys
```

### Verify Celery worker

```bash
docker compose exec worker celery -A app.tasks.celery_app:celery_app inspect registered
```

Expected tasks:
```bash
analytics.flush_click_counters
analytics.process_click_event
health.ping
```

### Health ping:
```bash
docker compose exec -T api python - <<'PY'
from app.tasks.health import ping

result = ping.delay()
print(result.get(timeout=10))
PY
```

Expected:
```text
pong
```

### Verify GeoIP service
```bash
docker compose exec -T worker python - <<'PY'
from app.services.geoip import lookup_geoip
for ip in ["8.8.8.8", "81.2.69.142", "127.0.0.1"]:
    print(ip, lookup_geoip(ip))
PY
```

Expected when GeoIP database is present:
```text
8.8.8.8     GeoIPLocation(country='United States', city=None)
81.2.69.142 GeoIPLocation(country='United Kingdom', city='London')
127.0.0.1   GeoIPLocation(country=None, city=None)
```
If all return `country=None`, the MaxMind database file is missing.
See [docs/GEOIP_SETUP.md](docs/GEOIP_SETUP.md).

### Verify redirect cache/counter
```bash
ALIAS="archtest$(date +%s)"

curl -i -X POST \
  'http://localhost:8001/api/v1/links' \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $API_KEY" \
  -d "{
    \"long_url\": \"https://example.com/architecture-test\",
    \"custom_alias\": \"${ALIAS}\"
  }"

curl -i "http://localhost:8001/${ALIAS}"

docker compose exec redis redis-cli -n 0 get "link:${ALIAS}:meta"
docker compose exec redis redis-cli -n 0 get "link:${ALIAS}:clicks"
```

> When using `zsh`, always use braces around variables followed by more text:
> `"link:${ALIAS}:clicks"` not `"link:$ALIAS:clicks"`.
> Because it can expand to an unexpected key string.

### Verify analytics pipeline end-to-end
```bash
# Fire a click with a resolvable public IP
curl -i \
  -H "X-Forwarded-For: 81.2.69.142" \
  -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36" \
  -H "Referer: https://google.com" \
  "http://localhost:8001/${ALIAS}"

# Confirm the click row was persisted
docker compose exec db psql -U postgres -d urlshort -c \
"SELECT id, clicked_at, ip_anonymized, country, city, browser, os, device_type, referrer
 FROM clicks ORDER BY clicked_at DESC LIMIT 3;"

# Wait for counter flush, then confirm click_count
sleep 35
docker compose exec db psql -U postgres -d urlshort -c \
"SELECT short_code, click_count FROM links WHERE short_code = '${ALIAS}';"
```

## 11. Design Decisions
see:
→ [DESIGN_DECISIONS.md](DESIGN_DECISIONS.md)
