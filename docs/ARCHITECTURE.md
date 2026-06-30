# Architecture & Design

## 1. System Overview

```text
              ┌─────────────────────────────────────────────-─┐
  Client ───▶ │  FastAPI Application                          │
              │                                               │
              │  /api/v1/auth      Registration + API key     │
              │  /api/v1/links     CRUD + pagination          │
              │  /api/v1/analytics Time-series stats (Day 3)  │
              │  /{short_code}     Redirect (hot path)        │
              │  /dashboard        Chart.js UI (Day 4)        │
              │  /health           System status              │
              └──────────────┬──────────────────┬───────────-─┘
                             │                  │
                             │                  │ source of truth
                             │                  │
                 ┌───────────▼───────┐  ┌───────▼───────────-─┐
                 │  Redis DB 0       │  │  PostgreSQL         │
                 │  · metadata cache │  │  · users            │
                 │  · click counters │  │  · links            │
                 │  · rate limits    │  │  · clicks (Day 3)   │
                 │  · SETNX reserve  │  │  · analytics (Day 3)│
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
                 │  · GeoIP lookup (Day 3)                    │
                 │  · User-agent parsing (Day 3)              │
                 │  · Counter flush to Postgres (Day 3)       │
                 │  · Webhook firing on threshold (Day 3+)    │
                 └──────────────────────────────────────────-─┘
```
The service is built around a FastAPI API layer, PostgreSQL as the primary source of truth, Redis for low-latency infrastructure, and Celery for non-blocking background processing.

Phase 2 adds the Redis and Celery foundation:

- Redis cache-aside link metadata for fast redirects
- Redis write-through click counters
- Redis sliding-window rate limiting
- Celery worker setup for asynchronous analytics tasks
- Separate Redis logical databases for application cache, Celery broker, and Celery results

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

- Routers stay thin: parse input, apply dependencies, delegate to services.
- Middleware handles cross-cutting request concerns such as rate limiting.
- Services hold business logic such as short-code generation, cache access, counters, and analytics enqueueing.
- Tasks perform asynchronous work outside the request/redirect path.
- Models own persistence mapping.
- PostgreSQL remains the source of truth.
- Redis is used as a performance, coordination, and queueing layer.

## 3. Runtime Components

### FastAPI application

FastAPI exposes:

```text
/api/v1/auth
/api/v1/links
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
- Durable click/analytics data in later phases
- Redis data can be rebuilt or repopulated from PostgreSQL where applicable.

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

```apache
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2
```

This separation prevents Celery broker/result keys from mixing with application cache keys.

### Celery worker

Celery is used for background analytics work that should not block redirects.

Worker command:

```bash
celery -A app.tasks.celery_app:celery_app worker \
  --loglevel=INFO \
  --concurrency=2 \
  --queues=default,analytics \
  --hostname=celery@%h
```

Registered Phase 2 tasks:

```text
health.ping
analytics.process_click_event
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
email       UQ     │    short_code    UQ INDEX   │    link_id       FK
hashed_pw          │    long_url                 │    clicked_at
api_key     UQ     │    user_id       FK         │    ip_anonymized
created_at         │    password_hash            │    country
                   │    expires_at    INDEX      │    city
                   │    is_permanent             │    browser
                   │    click_count              │    os
                   │    webhook_url              │    device_type
                   │    webhook_threshold        │    referrer
                   │    webhook_fired            │
                   │    created_at               │  Indexes:
                   │    updated_at               │  (link_id, clicked_at)
                   └────                         │  (link_id, country)
                                                 │  (link_id, browser)
                                                 └────
```
Current durable source-of-truth entities are users and links.

The clicks table is part of the planned analytics model. Day 2 introduces the asynchronous pipeline and Redis analytics counters first. Later phases can persist enriched click events and rollups into PostgreSQL.

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
### Click counter
```text
link:{short_code}:clicks
```
Example:

```text
link:countertest1782823999:clicks
```
Used for fast atomic click increments during redirects.

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
Used by the Redis sliding-window rate limiter.

### Analytics counters

```
analytics:clicks:processed
analytics:link:{short_code}:processed
analytics:link:{short_code}:daily:{YYYY-MM-DD}
analytics:link:{short_code}:last_event
```
Used by Celery analytics tasks for lightweight Day 2 validation and future analytics expansion.

## 6. Request Flows

### Create short link
```text
POST /api/v1/links
  → auth dependency validates X-API-Key
  → validate payload with Pydantic
  → if custom_alias:
        validate alias
        reserve/check uniqueness
  → else:
        generate unique Base62 short code
        reserve/check uniqueness
  → INSERT links row in PostgreSQL
  → optionally cache redirect metadata
  → 201 {data: LinkOut}
```

### Redirect — Phase 1 DB-only baseline
```text
GET /{short_code}
  → DB lookup
  → if not found: 404
  → if expired: 410
  → if password_hash: return unlock/password flow
  → click_count += 1 synchronously
  → return 301 or 302
```

### Redirect — Phase 2 with Redis cache and counters
```text
GET /{short_code}
  → RateLimitMiddleware
  → Redis GET link:{short_code}:meta
  → HIT:
        validate cached metadata
        Redis INCR link:{short_code}:clicks
        enqueue analytics.process_click_event
        return 301/302
  → MISS:
        PostgreSQL lookup
        if not found: 404
        if expired: 410
        Redis SET link:{short_code}:meta
        Redis INCR link:{short_code}:clicks
        enqueue analytics.process_click_event
        return 301/302
```
Fast path on cache hit:
```text
Redis metadata hit
  → Redis counter increment
  → Celery enqueue
  → redirect response
  ```
  This avoids a PostgreSQL read on hot redirects.

### Redirect — Phase 3 full analytics target
```text
GET /{short_code}
GET /{short_code}
  → Redis metadata lookup
  → record fast counter
  → enqueue analytics task
  → return redirect immediately

[worker]
  → GeoIP lookup
  → user-agent parsing
  → anonymize/hash sensitive fields
  → INSERT click event
  → update rollups
  → optionally flush Redis counters to PostgreSQL
  → optionally fire webhook threshold events
```
Phase 2 establishes the queue and worker foundation. Phase 3 can extend the task to persist enriched time-series analytics.

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

When exceeded:
```http
HTTP/1.1 429 Too Many Requests
Retry-After: <seconds>
X-RateLimit-Limit: <limit>
X-RateLimit-Remaining: 0
```
If Redis is unavailable, the rate limiter fails open and allows the request. This preserves service availability.

### 8. Cache and Queue Failure Behavior

```text
┌────────────────────────────────────┬──────────────────────────────────────────────┐
│ Component failure                  │ Expected behavior                            │
├────────────────────────────────────┼──────────────────────────────────────────────┤
│ Redis metadata cache unavailable   │ Fall back to PostgreSQL lookup               │
├────────────────────────────────────┼──────────────────────────────────────────────┤
│ Redis click counter unavailable    │ Fall back to PostgreSQL click increment      │
├────────────────────────────────────┼──────────────────────────────────────────────┤
│ Redis rate limiter unavailable     │ Fail open and allow request                  │
├────────────────────────────────────┼──────────────────────────────────────────────┤
│ Celery broker unavailable          │ Log warning; redirect still succeeds         │
├────────────────────────────────────┼──────────────────────────────────────────────┤
│ Celery worker unavailable          │ Tasks may queue; redirect still succeeds     │
├────────────────────────────────────┼──────────────────────────────────────────────┤
│ PostgreSQL unavailable             │ API management and cache misses fail normally│
└────────────────────────────────────┴──────────────────────────────────────────────┘
```

Design principle:
```text
Redirect availability should not depend on optional analytics processing.
```
PostgreSQL remains the source of truth. Redis and Celery improve performance and scalability but should not make simple redirects fragile.

## 9. Operational Validation

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
analytics.process_click_event
health.ping
Health ping:

bash
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
When using `zsh`, always use braces around variables followed by more text:
```bash
"link:${ALIAS}:clicks"
```
Do not use:
```bash
"link:$ALIAS:clicks"
```
because it can expand to an unexpected key string.

## 10. Design Decisions
see:
→ [DESIGN_DECISIONS.md](DESIGN_DECISIONS.md)
