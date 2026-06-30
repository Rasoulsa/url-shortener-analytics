# Design Decisions

Trade-offs made during development.
Updated daily as new decisions are made.

---

## 1. Short-Code Generation Algorithm

### Options considered

| Approach | Throughput | Privacy | Complexity | Verdict |
|----------|-----------|---------|------------|---------|
| Counter + Base62 | Highest | ❌ Sequential = guessable | Low | Rejected |
| Pre-generated pool | Highest at request time | ✅ Unpredictable | High | Rejected |
| **Random + SETNX** | Very high | ✅ Unpredictable | Low | ✅ Chosen |

### Why Random + SETNX

**Privacy:** Counter codes are sequential. An attacker iterates
`abc0001`, `abc0002` → harvests all destination URLs.
Random codes from 62^7 ≈ 3.5T keyspace are not enumerable.

**Scalability:** No global counter → no coordination point.
Multiple API instances generate codes independently.

**Collision safety (two layers):**
1. `Redis SET key NX EX=60` — atomic reservation. Only the first
   requester for a given code succeeds. Others retry immediately.
2. `UNIQUE` on `links.short_code` — database final safety net.

**Pressure relief:** After N failed retries at length L, transparently
grow to L+1. Graceful degradation with no manual intervention.

### Trade-off accepted
Non-zero (astronomically small) collision probability vs a counter's
mathematical zero. The two-layer defense makes an actual persisted
duplicate impossible in practice.

---

## 2. Cursor (Keyset) Pagination

**Rejected:** `LIMIT 20 OFFSET 1000`
- Postgres scans and discards 1000 rows on every page request
- Slower as pages go deeper
- Page drift: new inserts shift items between page loads

**Chosen:** `WHERE id < cursor ORDER BY id DESC LIMIT 20`
- Uses primary key index directly — O(log n) at any depth
- Stable: new inserts never cause drift
- `meta.next_cursor` in envelope tells client where to continue

---

## 3. Response Envelope `{data, meta, errors}`

Established on Day 1, not added later. Reason: retrofitting an
envelope on a live API breaks all existing clients.

Benefits:
- One response handler on the frontend for every endpoint
- Pagination always lives in `meta`, never mixed into `data`
- `errors` array supports multiple validation messages at once

---

## 4. Lazy Deletion for Expired Links

**Rejected:** Background cron that periodically deletes expired rows
- Extra service to deploy and monitor
- Links are effectively dead at `expires_at` anyway

**Chosen:** Check expiry on access, return 410 Gone
- Zero extra infrastructure
- Dead the instant `expires_at` passes
- Day 2 upgrade: also invalidate Redis cache on expiry detection

---

## 5. 301 vs 302 Redirect

Exposed as `is_permanent: bool` on each link.

| | 301 Permanent | 302 Temporary |
|---|---|---|
| Browser | Caches redirect | Re-requests every visit |
| Analytics | Fires once per browser | Fires on every visit |
| Use case | Stable permanent links | Campaign / tracked links |
| Default | — | ✅ (false) |

Default is `false` (302) because most use cases involve analytics
where every visit should be counted.

---

## 6. `main`-Only Branching Strategy

`develop` exists to protect `main` from broken integration between
multiple developers. This is a solo project — that problem
doesn't apply.

Feature branches → PR → `main` gives:
- Always-green, always-deployable `main`
- Full PR history showing process and decisions
- No unnecessary ceremony for a solo build

---

## 7. Phase 2: Redis Caching, Counters, Rate Limiting, and Celery

Phase 2 introduces Redis-backed infrastructure around the core URL shortening service:

- Cache-aside link metadata for fast redirects
- Redis write-through click counters
- Redis sliding-window rate limiting
- Celery + Redis for non-blocking analytics processing
- Separate Redis logical databases for cache, Celery broker, and Celery results

---

### 7.1 Redis Database Separation

The service uses separate Redis logical databases:

```text
┌──────────┬────────────────────────┬───────────────────────────────────────────────────────────----─┐
│ REDIS DB │ URL                    │ PURPOSE                                                        │
├──────────┼────────────────────────┼────────────────────────────────────────────────────────────----┤
│ DB 0     │ `redis://redis:6379/0` │ API cache, click counters, rate-limit keys, analytics counters │
├──────────┼────────────────────────┼────────────────────────────────────────────────────────────----┤
│ DB 1     │ `redis://redis:6379/1` │ Celery broker                                                  │
├──────────┼────────────────────────┼────────────────────────────────────────────────────────────----┤
│ DB 2     │ `redis://redis:6379/2` │ Celery result backend                                          │
└──────────┴────────────────────────┴────────────────────────────────────────────────────────────----┘
```

This prevents application cache keys from mixing with Celery queue/result keys.

Environment variables:
```apache
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2
```

### 7.2 Cache-Aside Link Metadata

Redirects are the hottest path in the service. To reduce PostgreSQL load,
link metadata is cached in Redis.

Cache key:
```text
link:{short_code}:meta
```
The cached value contains only redirect-required fields:
```json
{
  "short_code": "abc123",
  "long_url": "https://example.com",
  "expires_at": null,
  "is_permanent": false,
  "password_hash": null
}
```
The redirect flow is:

1. Check Redis for `link:{short_code}:meta`.
2. On cache hit, redirect without querying PostgreSQL.
3. On cache miss, load from PostgreSQL.
4. Store metadata in Redis with TTL.
5. Return redirect response.

Redis is treated as a performance layer, not the source of truth.
PostgreSQL remains authoritative.

If Redis is unavailable, the API falls back to PostgreSQL.

### Why cache-aside was chosen

Cache-aside was chosen because it keeps PostgreSQL authoritative while allowing
hot redirect paths to avoid repeated database reads.

Benefits:

- Simple invalidation model
- Redis can be rebuilt from PostgreSQL
- Cache failures do not corrupt source-of-truth data
- Hot links become fast after the first lookup

---

### 7.3 Write-Through Click Counters

Click increments are written to Redis first to avoid synchronous PostgreSQL writes
on every redirect.

Counter key:
```text
link:{short_code}:clicks
```
On successful redirect:

- Increment Redis counter.
- Return redirect quickly.
- If Redis increment fails, fall back to PostgreSQL click increment.
- Redis counters are atomic and efficient for high-volume redirect traffic.

A later background job can periodically flush Redis counters into PostgreSQL if
stronger persistence is required.

### Why Redis counters were chosen

Redis counters were chosen because they are:

- Atomic
- Fast
- Lightweight
- Better suited for high-volume increments than row-by-row database updates

Trade-off accepted:

- Redis counters are less durable than immediate PostgreSQL writes.
- This is acceptable for Day 2 because redirect latency and write-pressure reduction are more important.
- PostgreSQL fallback exists when Redis is unavailable.

---

### 7.4 Sliding-Window Rate Limiting

Rate limiting is implemented as FastAPI middleware using Redis sorted sets and a
Lua script.

Route classes:

```text
┌──────────────────────────--──┬─────────────────────────────┬──────────────────────────────────────┐
│ ROUTE TYPE                   │ IDENTIFIER                  │ PURPOSE                              │
├───────────────────────────--─┼─────────────────────────────┼──────────────────────────────────────┤
│ `POST /api/v1/auth/register` │ Client IP                   │ Strict registration abuse protection │
├────────────────────────────--┼─────────────────────────────┼──────────────────────────────────────┤
│ `/api/v1/*`                  │ API key, fallback to IP     │ API abuse protection                 │
├───────────────────────────--─┼─────────────────────────────┼──────────────────────────────────────┤
│ `/{short_code}`              │ Client IP                   │ Redirect abuse protection            │
└────────────────────────────--┴─────────────────────────────┴──────────────────────────────────────┘
```

Rate-limit keys:
```text
rate_limit:auth:{identifier_hash}
rate_limit:api:{identifier_hash}
rate_limit:redirect:{identifier_hash}
```
Identifiers are hashed before being stored in Redis keys to avoid storing raw API
keys or raw IP addresses.

A sliding-window algorithm was chosen instead of fixed-window because it avoids
boundary bursts.

Example fixed-window issue:
```text
59 requests at 12:00:59
59 requests at 12:01:00
```

This could allow almost double the intended rate in two seconds.
Sliding-window enforcement is smoother.

When the limit is exceeded, the API returns:
```http
HTTP/1.1 429 Too Many Requests
Retry-After: <seconds>
X-RateLimit-Limit: <limit>
X-RateLimit-Remaining: 0
```

If Redis is unavailable, rate limiting fails open to preserve API availability.

### Why sliding-window was chosen

Sliding-window rate limiting was chosen because it is more accurate than
fixed-window limiting and avoids request bursts at window boundaries.

Trade-off accepted:

- Sliding-window with sorted sets is more complex than fixed-window counters.
- The smoother enforcement is worth the added implementation complexity for an API that protects both authenticated routes and public redirect routes.

---

### 7.5 Celery Analytics Pipeline

Redirects should remain fast. Analytics processing is therefore pushed to Celery.

Flow:
```text
User requests /{short_code}
        |
        v
API resolves link
        |
        v
API records fast Redis counter
        |
        v
API enqueues analytics.process_click_event
        |
        v
API returns 301/302 redirect
        |
        v
Celery worker processes analytics asynchronously
```
Celery uses Redis as broker and result backend:
```apache
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2
```

Registered tasks:
```text
health.ping
analytics.process_click_event
```
The worker healthcheck uses Celery inspection:
```bash
celery -A app.tasks.celery_app:celery_app inspect ping --timeout=5
```
An HTTP healthcheck such as curl localhost:8000 is not valid for the worker
because the Celery worker does not run an HTTP server.

### Why Celery was chosen

Celery was chosen for analytics because redirect latency should not depend on:

- Analytics enrichment
- GeoIP lookup
- User-agent parsing
- Future webhook processing
- Future time-series aggregation

The redirect path should return as soon as the link is resolved and the fast
counter/queue operation is attempted.

Trade-off accepted:

- Analytics processing becomes eventually consistent.
- This is acceptable because redirect correctness is more important than immediate analytics availability.

---

### 7.6 Failure Behavior

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

Design principle:

```text
Redirect availability should not depend on optional analytics processing.
```

PostgreSQL remains the source of truth. Redis and Celery improve performance and
scalability but should not make simple redirects fragile.

---

## 7.7 Phase 2 Design Trade-offs Summary

#### Cache-aside metadata

Chosen because PostgreSQL remains the source of truth and Redis is only a
performance optimization.

#### Redis click counters

Chosen because Redis increments are atomic, fast, and reduce database write
pressure during high-volume redirects.

#### Sliding-window rate limiting

Chosen because it is more accurate than fixed-window limiting and avoids boundary
bursts.

#### Celery analytics pipeline

Chosen because redirect latency should not depend on analytics enrichment,
GeoIP lookup, user-agent parsing, or future webhook processing.

#### Separate Redis databases

Chosen because application keys, Celery broker keys, and Celery result keys have
different lifecycles and should not be mixed.

## 8. Async Analytics Pipeline *(Phase 3)*

Phase 2 establishes the Celery foundation with `analytics.process_click_event`.

Phase 3 will extend this into the full analytics pipeline:

- Persist click events
- Anonymize IP addresses
- Parse user agents
- Add GeoIP enrichment
- Build time-series stats endpoints
- Support future webhook threshold events
