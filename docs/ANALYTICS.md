# Phase 3 — Analytics Collection & Processing

This document describes the analytics pipeline: how click-level data is
collected without slowing redirects, enriched asynchronously, stored in a
time-series-friendly schema, and exposed through the stats API.

---

## 1. Requirements Mapping

| Requirement | Implementation |
|---|---|
| Precise visit timestamp | `clicks.clicked_at` (timestamptz) |
| IP anonymization | Last IPv4 octet zeroed before storage (`ip_anonymized`) |
| User-Agent parsing | Browser + OS extracted via `user-agents` |
| Referrer capture | `Referer` header stored in `clicks.referrer` |
| Country / City | GeoIP lookup via MaxMind GeoLite2 (`geoip2`) |
| Device type | desktop / mobile / tablet / unknown classification |
| Non-blocking collection | Redirect enqueues a Celery task; never blocks |
| Celery processing | `analytics.process_click_event` enriches + persists |
| Aggregation | Stats grouped by day, country, browser, device, referrer |
| Time-series schema | `clicks` indexed on `(link_id, clicked_at)` |

---

## 2. Pipeline Flow

```text
Client
  │ GET /{short_code}
  ▼
FastAPI redirect handler
  ├─ Resolve link (Redis cache → PostgreSQL fallback)
  ├─ Return 301/302 immediately          ← hot path, non-blocking
  ├─ INCR Redis click counter            ← write-through
  └─ enqueue analytics.process_click_event(short_code, ip, ua, referrer)
                                           │
                                           ▼
                                Celery Beat (every ~30s)
                                  └─ analytics.flush_click_counters
                                       ├─ GETDEL Redis counter → links.click_count
                                       └─ if click_count >= webhook_threshold
                                            and webhook_fired == false:
                                              set webhook_fired = true
                                              enqueue webhooks.deliver task

                                Celery worker (queue: default)
                                  └─ webhooks.deliver
                                       ├─ build payload (event, short_code,
                                       │  click_count, threshold, occurred_at)
                                       ├─ sign: X-Webhook-Signature sha256=<hmac>
                                       └─ POST to webhook_url (retry/backoff)
```

**Key privacy rule:** GeoIP lookup uses the **raw IP** for accuracy, but only
the **anonymized IP** is persisted.

```python
geoip_info   = lookup_geoip(ip_address)   # raw IP → best accuracy
ip_anonymized = anonymize_ip(ip_address)  # 8.8.8.8 → 8.8.8.0 (stored)
```

---

## 3. `clicks` Table Schema

| Column | Type | Notes |
|---|---|---|
| id | integer | PK |
| link_id | integer | FK → links.id |
| clicked_at | timestamptz | precise visit time |
| ip_anonymized | varchar | last octet zeroed |
| country | varchar | GeoIP, nullable |
| city | varchar | GeoIP, nullable |
| browser | varchar | parsed UA, nullable |
| os | varchar | parsed UA, nullable |
| device_type | varchar | desktop/mobile/tablet/unknown |
| referrer | text | Referer header, nullable |
| user_agent | text | raw UA |

Indexes for time-series queries:

```sql
CREATE INDEX ix_clicks_link_clicked_at ON clicks (link_id, clicked_at);
CREATE INDEX ix_clicks_clicked_at      ON clicks (clicked_at);
```

Future scaling: monthly `PARTITION BY RANGE (clicked_at)`.

---

## 4. Redis Analytics Keys

| Key pattern | Purpose |
|---|---|
| `link:{short_code}:clicks` | write-through click counter (flushed to PG) |
| `analytics:clicks:processed` | global processed-event counter |
| `analytics:link:{short_code}:processed` | per-link processed count |
| `analytics:link:{short_code}:daily:{YYYY-MM-DD}` | daily counter |
| `analytics:link:{short_code}:country:{country}` | country counter |
| `analytics:link:{short_code}:browser:{browser}` | browser counter |
| `analytics:link:{short_code}:device:{device}` | device counter |
| `analytics:link:{short_code}:last_event` | hash of last event (hashed PII) |

All PII (IP, UA, referrer) is SHA-256 hashed before being stored in Redis
summary keys.

---

## 5. Celery Tasks

| Task | Queue | Trigger | Responsibility |
|---|---|---|---|
| `analytics.process_click_event` | analytics | per redirect | enrich + persist one click |
| `analytics.flush_click_counters` | default | Beat, ~30s | Redis→PostgreSQL counter flush |
| `health.ping` | default | manual | worker liveness check |

The flush task uses Redis `GETDEL` so successful flushes never double-count.
On database failure the removed counter value is restored and the task retries
with exponential backoff (max 3 retries).

---

## 6. Stats API

All endpoints require `X-API-Key` authentication and are scoped to links
owned by the authenticated user.

Base prefix: `/api/v1/analytics`

Interactive contract: `http://localhost:8000/docs`

### 6.1 User-level overview

```awk
GET /api/v1/analytics/overview
```

Returns aggregate totals across all links owned by the user.

**Query parameters:**
```text
| Parameter | Type | Default | Description |
|---|---|---|---|
| days | int (1–365) | 30 | Rolling window in days |
| from | ISO-8601 datetime | — | Explicit start (overrides days) |
| to | ISO-8601 datetime | — | Explicit end (overrides days) |
```

**Example:**
```bash
curl "http://localhost:8000/api/v1/analytics/overview?days=7" \
  -H "X-API-Key: YOUR_KEY"
```

**Response envelope:**
```json
{
  "data": { ... },
  "meta": {
    "from": "2026-06-24T00:00:00+00:00",
    "to":   "2026-07-01T00:00:00+00:00",
    "days": 7
  },
  "errors": []
}
```

### 6.2 Per-link overview

```awk
GET /api/v1/analytics/links/{short_code}/overview
```

Returns aggregate totals for a single link.

**Query parameters:** same as overview (`days`, `from`, `to`)

**Example:**
```bash
curl "http://localhost:8000/api/v1/analytics/links/demo/overview?days=30" \
  -H "X-API-Key: YOUR_KEY"
```

**Response envelope:**
```json
{
  "data": { ... },
  "meta": {
    "short_code": "demo",
    "from": "2026-06-01T00:00:00+00:00",
    "to":   "2026-07-01T00:00:00+00:00",
    "days": 30
  },
  "errors": []
}
```

### 6.3 Time-series (clicks by day)

```awk
GET /api/v1/analytics/links/{short_code}/timeseries
```
Returns clicks grouped by day for the specified window.

**Query parameters:** same as overview (`days`, `from`, `to`)

**Example:**

```bash
curl "http://localhost:8000/api/v1/analytics/links/demo/timeseries?days=14" \
  -H "X-API-Key: YOUR_KEY"
```

**Response envelope:**
```json
{
  "data": [
    { "date": "2026-06-28", "clicks": 5 },
    { "date": "2026-06-29", "clicks": 12 },
    { "date": "2026-06-30", "clicks": 8 },
    { "date": "2026-07-01", "clicks": 17 }
  ],
  "meta": {
    "short_code": "demo",
    "from": "2026-06-17T00:00:00+00:00",
    "to":   "2026-07-01T00:00:00+00:00",
    "days": 14,
    "granularity": "day"
  },
  "errors": []
}
```

### 6.4 Dimension breakdown

```awk
GET /api/v1/analytics/links/{short_code}/breakdown
```

Returns top-N values for a single aggregation dimension.

**Query parameters:**

```tex
| Parameter | Type | Default | Description |
|---|---|---|---|
| dimension | enum | country | One of: country, city, browser, os, device_type, referrer |
| days | int (1–365) | 30 | Rolling window in days |
| from | ISO-8601 datetime | — | Explicit start (overrides days) |
| to | ISO-8601 datetime | — | Explicit end (overrides days) |
| limit | int (1–100) | 10 | Max rows returned |
```

**Examples:**
```bash
# Top countries
curl "http://localhost:8000/api/v1/analytics/links/demo/breakdown?dimension=country&days=30" \
  -H "X-API-Key: YOUR_KEY"

# Top browsers
curl "http://localhost:8000/api/v1/analytics/links/demo/breakdown?dimension=browser&days=30" \
  -H "X-API-Key: YOUR_KEY"

# Top referrers, top 5
curl "http://localhost:8000/api/v1/analytics/links/demo/breakdown?dimension=referrer&limit=5" \
  -H "X-API-Key: YOUR_KEY"

# Device breakdown
curl "http://localhost:8000/api/v1/analytics/links/demo/breakdown?dimension=device_type" \
  -H "X-API-Key: YOUR_KEY"
```

**Response envelope:**
```json
{
  "data": [
    { "country": "United States", "clicks": 18 },
    { "country": "United Kingdom", "clicks": 7 },
    { "country": "Germany", "clicks": 4 }
  ],
  "meta": {
    "short_code": "demo",
    "dimension": "country",
    "from": "2026-06-01T00:00:00+00:00",
    "to":   "2026-07-01T00:00:00+00:00",
    "days": 30,
    "limit": 10
  },
  "errors": []
}
```

---

## 7. Manual Validation

```bash
# 1. Fire a test click with a resolvable public IP
curl -i \
  -H "X-Forwarded-For: 81.2.69.142" \
  -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126 Safari/537.36" \
  -H "Referer: https://google.com" \
  http://localhost:8000/{short_code}

# 2. Inspect the recorded click
docker compose exec db psql -U postgres -d urlshort -c \
"SELECT id, clicked_at, ip_anonymized, country, city, browser, os, device_type, referrer
 FROM clicks ORDER BY clicked_at DESC LIMIT 5;"

# 3. Inspect Redis analytics keys
docker compose exec redis redis-cli -n 0 KEYS '*analytics*'

# 4. Wait for a counter flush, then confirm links.click_count
sleep 35
docker compose logs --tail=30 worker
docker compose exec db psql -U postgres -d urlshort -c \
"SELECT short_code, click_count FROM links WHERE short_code = '{short_code}';"
```

Notes:
- `curl -I` sends HEAD and may not count as a click — use `GET`.
- Private/local IPs (`127.0.0.1`, `192.168.x.x`, Docker `172.x.x.x`) never
  resolve via GeoIP; `country`/`city` stay NULL. This is expected.
- `81.2.69.142` is a MaxMind test IP resolving to London, UK.
- Infrastructure/CDN IPs (e.g. `8.8.8.8`, `1.1.1.1`) often return country only with no city. That is a GeoLite2 data coverage limit, not a bug.

---

## 8. Failure Behavior

| Failure | Behavior |
|---|---|
| Redis cache down | Redirect falls back to PostgreSQL |
| Redis counter down | Click increment falls back to PostgreSQL |
| Celery broker/worker down | Redirect still succeeds; task queued/skipped |
| GeoIP DB missing | Click stored with `country`/`city` = NULL |
| PostgreSQL down | Management API + cache misses fail normally |

Redirect UX is always prioritized; analytics is eventually consistent.

---

## 9. Completion Checklist

### Phase 3
- [x] Click-event schema (`feat/d3-click-schema`)
- [x] Enrichment helpers: GeoIP, UA, privacy (`feat/d3-analytics-enrichment`)
- [x] Non-blocking click recording (`feat/d3-click-recording`)
- [x] Redis→PostgreSQL counter flush (`feat/d3-counter-flush`)
- [x] Stats API (`feat/d3-stats-api`)
- [x] Documentation (`docs/d3-analytics`)

### Phase 4
- [x] Webhooks on click thresholds (`feat/d4-webhooks`)
- [x] Dashboard — line chart, country table, referrers, browsers (`feat/d4-dashboard-ui`)
- [x] Multi-link comparison chart (`feat/d4-dashboard-api` + `feat/d4-dashboard-ui`)
- [x] Final analytics documentation (`docs/d4-documentation`)


## 10. Phase 4 — Dashboard & Webhooks

### Dashboard

Phase 4 adds a browser-based analytics dashboard at `/dashboard` that
consumes the Phase 3 stats API directly.

Production website: `www.matinrayaneharyan.ir`

**Dashboard views:**

| View | Endpoint used | Notes |
|---|---|---|
| Visits line chart (7/30/90 days) | `timeseries` | Switchable day window |
| Geographic breakdown | `breakdown?dimension=country` | Table, no map required |
| Top referrers | `breakdown?dimension=referrer` | Top 10 by default |
| Top browsers | `breakdown?dimension=browser` | Top 10 by default |
| Multi-link comparison | `compare?codes=...&days=...` | Zero-filled aligned series |

The dashboard is built with Jinja2 server-rendered HTML and Chart.js
visualizations. All aggregation stays in the backend — the UI stays thin.

**Validate the dashboard locally:**

```bash
open http://localhost:8000/dashboard
```

---

### Webhooks

Phase 4 adds click-threshold webhook support on top of the analytics flush
pipeline.

**New link fields:**

| Field | Type | Description |
|---|---|---|
| `webhook_url` | string (URL) | Destination for the threshold event |
| `webhook_threshold` | integer | Click count required before firing |
| `webhook_fired` | boolean | Idempotency guard; `true` after the event fires |

**Delivery behavior:**

- Threshold detection runs inside `analytics.flush_click_counters` — the
  task that owns the authoritative `click_count` update.
- `webhook_fired` is set to `true` before enqueueing delivery so the event
  is scheduled at most once per link even if flushes overlap.
- Delivery runs in a separate Celery task with retry/backoff for transient
  failures (timeouts, connection errors, receiver `5xx`).
- Payloads are signed with HMAC SHA-256.
- Webhook delivery never touches the redirect hot path.

**Example payload delivered to `webhook_url`:**

```json
{
  "event": "link.click_threshold_reached",
  "short_code": "demo",
  "click_count": 100,
  "threshold": 100,
  "occurred_at": "2026-07-02T00:00:00Z"
}
```

**Example signature header:**

```http
X-Webhook-Signature: sha256=<hmac_hex_digest>
```

**Validate webhooks locally:**

```bash
# 1. Start a local receiver
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

# 2. Create a link with webhook config
curl -X POST http://localhost:8000/api/v1/links \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "long_url": "https://example.com",
    "custom_alias": "webhooktest",
    "webhook_url": "http://0.0.0.0:9999/webhook",
    "webhook_threshold": 3
  }'

# 3. Drive clicks past the threshold
for i in 1 2 3 4; do
  curl -s -o /dev/null http://localhost:8000/webhooktest
done

# 4. Wait for the counter flush and check the receiver output
sleep 35
# Receiver terminal should print the payload exactly once

# 5. Confirm webhook_fired is true in the database
docker compose exec db psql -U postgres -d urlshort -c \
"SELECT short_code, click_count, webhook_fired FROM links WHERE short_code = 'webhooktest';"
```

**Updated failure behavior table:**

| Failure | Behavior |
|---|---|
| Redis cache down | Redirect falls back to PostgreSQL |
| Redis counter down | Click increment falls back to PostgreSQL |
| Celery broker/worker down | Redirect still succeeds; task queued/skipped |
| GeoIP DB missing | Click stored with `country`/`city` = NULL |
| Webhook receiver slow/down | Celery retries with backoff; redirect unaffected |
| Webhook permanently failing | Logged; `webhook_fired` stays `true` (no spam) |
| PostgreSQL down | Management API + cache misses fail normally |
