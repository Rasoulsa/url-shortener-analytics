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

> Phase 4 verified this contract across all listing endpoints and standardized
> the `meta` shape (`next_cursor`, `limit`). See section 10.

---

## 3. Response Envelope `{data, meta, errors}`

Established on Day 1, not added later. Reason: retrofitting an
envelope on a live API breaks all existing clients.

Benefits:
- One response handler on the frontend for every endpoint
- Pagination always lives in `meta`, never mixed into `data`
- `errors` array supports multiple validation messages at once

> Phase 4 audited every endpoint for envelope consistency and added unified
> exception handlers so error responses share the same shape. See section 10.

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
```ini
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
PostgreSQL remains authoritative. If Redis is unavailable, the API falls back to PostgreSQL.

**Why cache-aside:** Simple invalidation model. Redis can be rebuilt from
PostgreSQL. Cache failures do not corrupt source-of-truth data.

---

### 7.3 Write-Through Click Counters

Click increments are written to Redis first to avoid synchronous PostgreSQL writes
on every redirect.

Counter key:
```text
link:{short_code}:clicks
```
On successful redirect:
- `INCR link:{short_code}:clicks` in Redis
- Return redirect quickly.
- If Redis increment fails -> fall back to PostgreSQL click increment.
- Redis counters are atomic and efficient for high-volume redirect traffic.

Celery Beat flushes Redis counters to PostgreSQL every ~30 seconds
(see section 8.3).

A later background job can periodically flush Redis counters into PostgreSQL if
stronger persistence is required.

**Why Redis counters were chosen:** Atomic, fast, and lightweight. Better suited for
high-volume increments than row-by-row database updates.

**Trade-off accepted:** Redis counters are less durable than immediate PostgreSQL writes. Acceptable because redirect latency and write-pressure
reduction are the priority. PostgreSQL fallback exists when Redis is
unavailable.

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
Identifiers are hashed before being stored in Redis keys. Raw API keys and
raw IP addresses are never stored in rate-limit keys.

**Why sliding-window over fixed-window:** Fixed-window allows boundary
bursts:
```text
59 requests at 12:00:59
59 requests at 12:01:00
```

Sliding-window enforcement is smoother and more accurate.

**Trade-off accepted:** Sorted sets are more complex than a fixed-window
counter. The smoother enforcement is worth the added complexity for an API
that protects both authenticated routes and public redirect routes.

If Redis is unavailable, rate limiting fails open to preserve API
availability.

---

### 7.5 Celery Analytics Pipeline (Phase 2 foundation)

Redirects must remain fast. Analytics processing is pushed to Celery so the
redirect path never blocks on enrichment work.

Flow:
```text
GET /{short_code}
  → resolve link (Redis cache → PostgreSQL fallback)
  → INCR Redis click counter
  → enqueue analytics.process_click_event
  → return 301/302 immediately   ← never blocks on analytics

[Celery worker]
  → process click event asynchronously
```
Celery uses Redis as broker and result backend:
```apache
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2
```

Registered tasks (Phase 2 foundation):
```text
health.ping
analytics.process_click_event
```
The worker healthcheck uses Celery inspection, not HTTP:
```bash
celery -A app.tasks.celery_app:celery_app inspect ping --timeout=5
```
An HTTP healthcheck such as curl localhost:8000 is not valid for the worker
because the Celery worker does not run an HTTP server.

**Why Celery:** Redirect latency must not depend on GeoIP lookup,
User-Agent parsing, analytics enrichment, or future webhook processing.

**Trade-off accepted:** Analytics becomes eventually consistent. Redirect
correctness is more important than immediate analytics availability.

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

---

## 8. Phase 3: Full Analytics Pipeline

Phase 3 extends the Celery foundation from Phase 2 into a complete
click-enrichment and stats system.

---

### 8.1 GeoIP Lookup on Raw IP, Anonymized IP for Storage

**Decision:** Perform GeoIP lookup using the raw client IP, then store
only the anonymized IP (`last octet zeroed`).
```python
geoip_info    = lookup_geoip(ip_address)   # raw IP → accurate country/city
ip_anonymized = anonymize_ip(ip_address)   # 8.8.8.8 → 8.8.8.0 (stored)
```

**Why:** GeoIP accuracy degrades significantly at the subnet level. Zeroing
the last octet before lookup would reduce city-level precision. Performing
lookup first then anonymizing gives the best accuracy while still honoring
privacy-by-design storage.

**Trade-off** accepted: The raw IP transiently exists in worker memory during
enrichment. It is never written to PostgreSQL, Redis, or any log. The
anonymized form is the only persisted value.

---

### 8.2 GeoIP Fails Open

**Decision:** All GeoIP failure modes (missing database file, missing
`geoip2` package, invalid IP, IP not in database) return empty
`country/city` values rather than raising exceptions.
```python
def lookup_geoip(ip: str) -> GeoIPLocation:
    try:
        ...
    except Exception:
        return GeoIPLocation(country=None, city=None)
```

**Why:** GeoIP enrichment is optional context. A missing MaxMind database
should never prevent a click from being recorded. The redirect and analytics
pipeline must remain operational regardless of GeoIP availability.

**Trade-off accepted:** Some clicks will have NULL country/city. This is
expected and documented. Infrastructure/CDN IPs (e.g. `8.8.8.8`, `1.1.1.1`)
often return country only with no city even when the database is present —
that is a MaxMind data coverage limit, not a bug.

---

### 8.3 Counter Flush with `GETDEL` for Safety

**Decision:** The `analytics.flush_click_counters` Celery Beat task uses
Redis `GETDEL` (atomic get-and-delete) rather than `GET` + `DEL`.
```python
count = redis.getdel(f"link:{short_code}:clicks")
# → UPDATE links SET click_count = click_count + count
```

**Why:** `GET` + `DEL` is two operations. Between them another request could
`INCR` the counter, and `DEL` would erase that increment, losing a click
permanently. `GETDEL` is a single atomic operation that eliminates this race.

**On database failure:** If the `UPDATE` fails after `GETDEL` has already
removed the Redis key, the count value is restored to Redis before the task
retries (max 3 retries, exponential backoff). No clicks are lost.

**Trade-off accepted:** `GETDEL` requires Redis ≥ 6.2. This is within our
stated Redis 7 requirement. Older Redis versions would need `GET` + `DEL`
inside a Lua script as an alternative.

---

### 8.4 Stats API Design: Four Focused Endpoints over One Combined Endpoint

**Rejected:** Single `GET /api/v1/analytics/links/{short_code}?include=timeseries,country,browser`

- One large response regardless of what the client actually needs
- Complex query parameter combination logic
- Harder to cache individual dimensions independently

**Chosen:** Four focused endpoints:
```text
GET /api/v1/analytics/overview
GET /api/v1/analytics/links/{short_code}/overview
GET /api/v1/analytics/links/{short_code}/timeseries
GET /api/v1/analytics/links/{short_code}/breakdown?dimension=country|city|browser|os|device_type|referrer
```

**Why:**

- Each endpoint maps to one query — simpler to reason about, test, and cache
- `breakdown` covers all six dimensions through one route using a `dimension` enum parameter, avoiding endpoint proliferation
- Clients fetch only what they need (a dashboard rendering a chart fetches `timeseries` without also receiving a full country breakdown)
- `meta` block on every response includes the exact date range used, making responses self-describing

**Trade-off accepted:** Multiple round trips if a client needs all
dimensions. Acceptable for a stats/dashboard use case where individual
charts are loaded independently.

---

### 8.5 Analytics Query Uses PostgreSQL, Not Redis Counters

**Decision:** All stats API queries (`/overview`, `/timeseries`,
`/breakdown`) query the `clicks` table in PostgreSQL directly rather than
reading Redis analytics counters.

**Why:**

- PostgreSQL clicks rows contain full enriched data (country, city, browser, os, device_type, referrer) that Redis counters do not have
- SQL GROUP BY + COUNT is expressive and correct for arbitrary date ranges
- Redis counters are a denormalized optimization for the redirect hot path, not a query layer
- Avoids dual-write consistency concerns between Redis and PostgreSQL

**Trade-off accepted:** Stats API queries hit PostgreSQL. For the evaluation
scale this is fine. At production scale, read replicas or a dedicated OLAP
store (e.g. ClickHouse) would offload analytics queries from the primary.

---

### 8.6 `clicks` Table Indexed, Not Partitioned

**Decision:** The `clicks` table uses composite indexes for time-series
queries rather than table partitioning.
```sql
CREATE INDEX ix_clicks_link_clicked_at ON clicks (link_id, clicked_at);
CREATE INDEX ix_clicks_clicked_at      ON clicks (clicked_at);
```

**Why:** Partitioning adds operational complexity (partition management,
migration complexity, partition pruning configuration). For evaluation scale
with hundreds to thousands of click rows, indexes are sufficient and
simpler to reason about.

**Future fix:** Monthly `RANGE` partitions on `clicked_at` when the table
grows to millions of rows:
```sql
CREATE TABLE clicks_2026_07 PARTITION OF clicks
  FOR VALUES FROM ('2026-07-01') TO ('2026-08-01');
```
Monthly partitions allow old data to be archived or dropped without
affecting query performance on recent data.

---

## 9. Phase 3 Trade-offs Summary

| Decision | Chosen approach | Key reason |
|---|---|---|
| GeoIP lookup timing | Raw IP for lookup, anonymized for storage | Accuracy + privacy |
| GeoIP failure mode | Fail open, return NULL | Click recording must never fail due to GeoIP |
| Counter flush atomicity | GETDEL + restore-on-failure | No double-count, no lost clicks |
| Stats API shape | Four focused endpoints + dimension enum | One query per endpoint, client fetches only what it needs |
| Stats data source | PostgreSQL clicks table | Full enriched data; Redis counters are hot-path only |
| clicks table scaling | Indexes only for now | Partitioning is future work when rows reach millions |

---

## 10. Phase 4: Public API, Webhooks, and Dashboard

Phase 4 turns the internal service into a documented public product: a
versioned API with a stable contract, click-threshold webhooks, and an
analytics dashboard.

### 10.1 Explicit URL Versioning under `/api/v1/`

**Decision:** All public API routes live under `/api/v1/`.

**Why:**

- Gives clients a stable, explicit contract
- A future breaking change can ship under `/api/v2/` without disrupting existing integrations
- Keeps public API routes clearly separated from UI routes (`/dashboard`) and the redirect hot path (`/{short_code}`)

**Trade-off accepted:** Slightly longer URLs. URL-based versioning is simple,
visible, and easy for clients to reason about compared to header-based
versioning.

### 10.2 OpenAPI / Swagger as the Living API Contract

**Decision:** Lean on FastAPI's generated OpenAPI schema as the source of API
documentation, enriched with router tags, summaries, descriptions, response
models, and the API-key security scheme.

```text
/docs        Swagger UI
/redoc       ReDoc
/openapi.json Raw schema
```

**Why:**

- Documentation stays in sync with the code because it is generated from the same Pydantic models and route signatures
- No separate, manually-maintained API spec to drift out of date
- Response model examples make the envelope shape discoverable in Swagger

**Trade-off accepted**: Requires disciplined use of tags, summaries, and
response models on every route to keep the generated docs high quality.

### 10.3 Envelope Audit and Unified Exception Handling

**Decision**: Finalize the `{ data, meta, errors }` envelope across every
endpoint and route all errors through unified exception handlers.

```json
{
  "data": null,
  "meta": {},
  "errors": [
    { "code": "not_found", "message": "Link not found", "field": null }
  ]
}
```
Handled consistently: `400`, `401`, `404`, `410`, `422`, `429`, `500`.

**Why:**

- Clients and the dashboard use one parser for success and error responses
- Machine-readable code fields make error handling programmatic
- Validation errors can carry a field for form feedback

**Trade-off accepted**: Small wrapping overhead on simple responses. The
consistency benefit outweighs the extra bytes.

### 10.4 Webhook Delivery via Celery, Fired from the Counter Flush

**Decision**: Fire click-threshold webhooks from the
`analytics.flush_click_counters` Beat task (where `click_count` is authoritatively
updated), delivered by a separate Celery task — not from the redirect path.

```text
flush_click_counters (Beat)
  → click_count updated from Redis
  → threshold crossed and webhook_fired == false?
        set webhook_fired = true      # single-flight guard
        enqueue webhook delivery task
  → webhook task POSTs signed payload with retry/backoff
```

**Why:**

- The redirect hot path only does `INCR`; it must never make outbound HTTP calls
- The flush task is the natural place to observe threshold crossings because it owns the durable `click_count` update
- Delivery in its own task isolates slow/failing receivers from analytics processing

**Trade-off accepted**: Webhooks are eventually consistent — they fire shortly
after the threshold is crossed (on the next flush), not during the exact
redirect that crossed it. Acceptable because thresholds are a notification
feature, not a real-time guarantee.

### 10.5 Webhook Idempotency via `webhook_fired`

**Decision**: Persist a `webhook_fired` boolean on the link and set it to
`true` before enqueueing delivery, inside the same flush transaction that
detects the crossing.

**Why:**

- Guarantees the threshold event is scheduled at most once even if flushes overlap or the task is retried
- Simple, durable, and easy to reason about compared to an external dedup store

**Trade-off accepted**: This design supports a single threshold event per link.
Multiple thresholds, repeatable events, or an event log would require a richer
schema — deferred as future work.

### 10.6 HMAC-Signed Webhook Payloads

**Decision**: Sign each webhook body with HMAC SHA-256 using a configured
secret, sent as `X-Webhook-Signature: sha256=<hex>`.

**Why:**

- Lets receivers verify authenticity and integrity of the payload
- Follows a widely-understood webhook security convention (GitHub-style)
- Cheap to compute and easy for receivers to validate

**Trade-off accepted**: Receivers must implement signature verification and the
service must manage a webhook secret. Standard cost for secure webhooks.

### 10.7 Multi-Link Comparison Aggregated in the Backend

**Decision**: Provide a dedicated comparison endpoint that returns aligned,
zero-filled series for multiple short codes over one shared window, rather than
having the dashboard fetch each link separately and align in the browser.

```json
{
  "data": {
    "labels": ["2026-06-28", "2026-06-29"],
    "series": [
      { "short_code": "demo",  "values": [5, 12] },
      { "short_code": "promo", "values": [0, 3] }
    ]
  }
}
```

**Why:**

- Date alignment and zero-filling of missing days are done once, correctly, on the server
- The chart consumes a single, ready-to-render payload
- Avoids N separate client requests and client-side merge logic

**Trade-off accepted**: More backend aggregation logic. Worth it for correct,
consistent chart data.

### 10.8 Dashboard with Jinja2 + Chart.js (Country Table, No Map)

**Decision**: Build `/dashboard` as server-rendered Jinja2 HTML with Chart.js
for visualizations, and present the geographic breakdown as a table.

**Why:**

- No separate frontend build pipeline; FastAPI serves both API and dashboard
- Chart.js is sufficient for line and comparison charts
- A country table satisfies the requirement without a map library, external map API keys, or handling of incomplete GeoIP data
- The dashboard reuses the Phase 3 analytics endpoints, keeping the UI thin

**Trade-off accepted**: Less interactive than a full SPA and less visual than a
map. Appropriate for this project’s scope; a richer frontend is future work.
