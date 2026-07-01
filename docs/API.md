# API Reference

**Base URL:** `http://localhost:8000`
**Auth:** `X-API-Key: <key>` header on all `/api/v1/*` (except register)
**Envelope:** All responses → `{ "data": ..., "meta": ..., "errors": [] }`

> **Interactive docs:**
> Swagger UI → http://localhost:8000/docs
> ReDoc      → http://localhost:8000/redoc

---

## Table of Contents

1. [Authentication](#authentication)
2. [Links](#links)
3. [Redirect](#redirect)
4. [Analytics](#analytics)
5. [Rate Limiting](#rate-limiting)
6. [System](#system)

---

## Authentication

### POST `/api/v1/auth/register`

Registers a new user and returns an API key.

**Request:**
```json
{ "email": "user@example.com", "password": "minimum8chars" }
```

**Response 201:**
```json
{
  "data": {
    "id": 1,
    "email": "user@example.com",
    "api_key": "abc123xyz...",
    "created_at": "2026-06-28T10:00:00Z"
  },
  "meta": null,
  "errors": []
}
```

---

## Links

All /api/v1/links endpoints require:
```http
X-API-Key: YOUR_KEY
```

Creates a shortened URL.

### POST `/api/v1/links` — Create

Creates a shortened URL.
```bash
curl -X POST http://localhost:8000/api/v1/links \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "long_url": "https://example.com/very/long/path",
    "custom_alias": "mylink",
    "expires_at": "2026-12-31T23:59:59Z",
    "password": "secret",
    "is_permanent": false,
    "webhook_url": "https://hooks.example.com/notify",
    "webhook_threshold": 100
  }'
```

#### Response 201 example:
```json
{
  "data": {
    "id": 1,
    "short_code": "mylink",
    "long_url": "https://example.com/very/long/path",
    "short_url": "http://localhost:8000/mylink",
    "expires_at": "2026-12-31T23:59:59Z",
    "is_permanent": false,
    "click_count": 0,
    "created_at": "2026-06-28T10:00:00Z"
  },
  "meta": null,
  "errors": []
}
```

---

### GET `/api/v1/links` — List

Lists links owned by the authenticated user using cursor pagination.
```bash
# First page
curl "http://localhost:8000/api/v1/links?limit=20" \
  -H "X-API-Key: YOUR_KEY"

# Next page
curl "http://localhost:8000/api/v1/links?cursor=42&limit=20" \
  -H "X-API-Key: YOUR_KEY"
```

Response 200 example:
```json
{
  "data": [
    {
      "id": 42,
      "short_code": "abc123",
      "long_url": "https://example.com",
      "short_url": "http://localhost:8000/abc123",
      "expires_at": null,
      "is_permanent": false,
      "click_count": 10,
      "created_at": "2026-06-28T10:00:00Z"
    }
  ],
  "meta": {
    "next_cursor": 41,
    "limit": 20
  },
  "errors": []
}
```

---

### GET `/api/v1/links/{short_code}` — Get one

Returns a single link owned by the authenticated user.
```bash
curl "http://localhost:8000/api/v1/links/abc123" \
  -H "X-API-Key: YOUR_KEY"
```

---

### PATCH `/api/v1/links/{short_code}` — Update

Updates an existing link owned by the authenticated user.
```bash
curl -X PATCH "http://localhost:8000/api/v1/links/abc123" \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "long_url": "https://example.com/new-target",
    "expires_at": "2026-12-31T23:59:59Z",
    "is_permanent": false
  }'
```

---

### DELETE `/api/v1/links/{short_code}` — Delete (204 No Content)

Deletes an existing link owned by the authenticated user.
```bash
curl -X DELETE "http://localhost:8000/api/v1/links/abc123" \
  -H "X-API-Key: YOUR_KEY"
```
Response:
```text
204 No Content
```

---

## Redirect

Redirect routes are public and do not require an API key.

### GET `/{short_code}`
- `302` temporary or `301` permanent redirect
- `404` if not found
- `410` if expired
- `200` HTML password form if protected
- `429` Rate limit exceeded (Too Many Requests)

Example:
```bash
curl -i http://localhost:8000/abc123
```

Temporary redirect example:
```http
HTTP/1.1 302 Found
Location: https://example.com
x-ratelimit-limit: 60
x-ratelimit-remaining: 59
```

Permanent redirect example:
```http
HTTP/1.1 301 Moved Permanently
Location: https://example.com
```

> **Analytics** note: Every successful redirect enqueues a Celery task that
> records the click asynchronously. The redirect itself is never blocked by
> analytics processing.

---

### POST `/{short_code}/unlock`

Unlocks a password-protected link.

Form field: `password`

Example:
```bash
curl -i -X POST http://localhost:8000/abc123/unlock \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "password=secret"
```

---

## Rate Limiting

API and redirect requests may be rate limited.

Rate limiting is implemented with Redis using a sliding-window algorithm.

#### Rate-limit classes

```text
┌────────────────────────────┬─────────────────────────────-─┬──────────────────────────────────────┐
│ ROUTE                      │ IDENTIFIER                    │ PURPOSE                              │
├────────────────────────────┼──────────────────────────────-┼──────────────────────────────────────┤
│ POST /api/v1/auth/register │ Client IP                     │ Registration abuse protection        │
├────────────────────────────┼──────────────────────────────-┼──────────────────────────────────────┤
│ /api/v1/*                  │ API key, fallback to client IP│ API abuse protection                 │
├────────────────────────────┼──────────────────────────────-┼──────────────────────────────────────┤
│ GET /{short_code}          │ Client IP                     │ Redirect abuse protection            │
└────────────────────────────┴─────────────────────────────-─┴──────────────────────────────────────┘
```

Identifiers are hashed before being stored in Redis keys. Raw API keys and raw IP
addresses are not stored directly in Redis rate-limit keys.

---

### Successful request headers


When a request is allowed, responses may include:
```http
X-RateLimit-Limit: <limit>
X-RateLimit-Remaining: <remaining>
```

Example:
```http
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 58
```

---

### Rate limit exceeded

When the limit is exceeded, the API returns:
```http
HTTP/1.1 429 Too Many Requests
Retry-After: <seconds>
X-RateLimit-Limit: <limit>
X-RateLimit-Remaining: 0
```

Example response body:
```json
{
  "data": null,
  "meta": {
    "limit": 5,
    "remaining": 0,
    "retry_after_seconds": 57
  },
  "errors": [
    {
      "code": "rate_limit_exceeded",
      "message": "Too many requests. Please try again later."
    }
  ]
}
```

---

#### Example rate-limit test

With local low test values:
```ini
RATE_LIMIT_REDIRECT_REQUESTS=3
RATE_LIMIT_WINDOW_SECONDS=60
```

Run:
```bash
for i in 1 2 3 4 5; do
  curl -s -o /dev/null -w "%{http_code}\n" "http://localhost:8000/abc123"
done
```

Expected:
```text
302
302
302
429
429
```
> If the link is configured as permanent, the successful responses may be `301`
> instead of `302`.

---

## Analytics

All analytics endpoints require X-API-Key authentication and are scoped to
links owned by the authenticated user.

**Common query parameters:**
```text
| Parameter | Type | Default | Description |
|---|---|---|---|
| days | int (1–365) | 30 | Rolling window in days |
| from | ISO-8601 datetime | — | Explicit start datetime (overrides days) |
| to | ISO-8601 datetime | — | Explicit end datetime (overrides days) |
```

> **Eventually consistent:** Click events are recorded asynchronously via
> Celery. Counter flushes to PostgreSQL happen every ~30 seconds via Celery
> Beat. Analytics data may lag up to ~30 seconds behind real-time.

### GET `/api/v1/analytics/overview`

Returns aggregate totals across all links owned by the authenticated user.
```bash
curl "http://localhost:8000/api/v1/analytics/overview?days=7" \
  -H "X-API-Key: YOUR_KEY"
```

**Response 200:**
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

### `GET /api/v1/analytics/links/{short_code}/overview`

Returns aggregate totals for a single link.
```bash
curl "http://localhost:8000/api/v1/analytics/links/demo/overview?days=30" \
  -H "X-API-Key: YOUR_KEY"
```

**Response 200:**
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

### GET `/api/v1/analytics/links/{short_code}/timeseries`

Returns clicks grouped by day for the specified time window.
```bash
curl "http://localhost:8000/api/v1/analytics/links/demo/timeseries?days=14" \
  -H "X-API-Key: YOUR_KEY"
```

**Response 200:**
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

### GET `/api/v1/analytics/links/{short_code}/breakdown`

Returns the top-N values for a single aggregation dimension.

**Additional query parameters:**
```text
| Parameter | Type | Default | Description |
|---|---|---|---|
| dimension | enum | country | Aggregation field — see supported values below |
| limit | int (1–100) | 10 | Maximum rows returned |
```

**Supported dimensions:**
```text
| Value | Description |
|---|---|
| country | Country resolved via GeoIP |
| city | City resolved via GeoIP |
| browser | Browser parsed from User-Agent |
| os | Operating system parsed from User-Agent |
| device_type | desktop, mobile, tablet, or unknown |
| referrer | Referring URL from Referer header |
```

```bash
# Top countries
curl "http://localhost:8000/api/v1/analytics/links/demo/breakdown?dimension=country&days=30" \
  -H "X-API-Key: YOUR_KEY"

# Top browsers
curl "http://localhost:8000/api/v1/analytics/links/demo/breakdown?dimension=browser" \
  -H "X-API-Key: YOUR_KEY"

# Top referrers, top 5
curl "http://localhost:8000/api/v1/analytics/links/demo/breakdown?dimension=referrer&limit=5" \
  -H "X-API-Key: YOUR_KEY"

# Device type split
curl "http://localhost:8000/api/v1/analytics/links/demo/breakdown?dimension=device_type" \
  -H "X-API-Key: YOUR_KEY"

# OS breakdown for a custom date range
curl "http://localhost:8000/api/v1/analytics/links/demo/breakdown?dimension=os&from=2026-06-01T00:00:00Z&to=2026-07-01T00:00:00Z" \
  -H "X-API-Key: YOUR_KEY"
```

**Response 200 (country example):**
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

Full analytics pipeline details → [docs/ANALYTICS.md](docs/ANALYTICS.md)

---

#### Rate limiter failure behavior

If Redis is unavailable, rate limiting fails open.

That means the request is allowed instead of blocking all traffic. This preserves
availability during a Redis outage.

---

## System

### GET /`health`

Returns API and dependency health status. Does not require authentication.
```bash
curl http://localhost:8000/health
```

Response 200:
```json
{
  "status": "ok",
  "version": "1.0.0",
  "dependencies": {
    "redis": "up"
  }
}
```

### Notes for Docker local development

If Docker Compose maps the API to port 8001, replace 8000 with 8001 in all
examples above.
```bash
curl -i http://localhost:8001/health
curl "http://localhost:8001/api/v1/analytics/links/demo/timeseries?days=7" \
  -H "X-API-Key: YOUR_KEY"
```
