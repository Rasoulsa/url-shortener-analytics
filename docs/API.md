# API Reference

**Base URL:** `http://localhost:8000`
**Auth:** `X-API-Key: <key>` header on all `/api/v1/*` (except register)
**Envelope:** All responses → `{ "data": ..., "meta": ..., "errors": [] }`

> **Interactive docs:**
> Swagger UI → http://localhost:8000/docs
> ReDoc      → http://localhost:8000/redoc

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

Gets one link owned by the authenticated user.
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
- `429` Rate limit exceeded

Example:
```bash
curl -i http://localhost:8000/abc123
```

Temporary redirect example:
```http
HTTP/1.1 302 Found
Location: https://example.com
```

Permanent redirect example:
```http
HTTP/1.1 301 Moved Permanently
Location: https://example.com
```

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
If the link is configured as permanent, the successful responses may be `301`
instead of `302`.

---

#### Rate limiter failure behavior
If Redis is unavailable, rate limiting fails open.

That means the request is allowed instead of blocking all traffic. This preserves
availability during a Redis outage.


---

## Analytics *(Phase 3)*

### GET `/api/v1/analytics/{short_code}?days=7`
Time-series breakdown by day, country, browser, device. *(Coming Day 3)*

---

## System

### GET `/health`

Returns API health status.
```json
{
  "status": "ok",
  "version": "1.0.0",
  "dependencies": { "redis": "up" }
}
```

Response 200 example:
```json
{
  "status": "ok",
  "version": "1.0.0",
  "dependencies": {
    "redis": "up"
  }
}
```

---

### Notes for Docker local development

If Docker Compose maps the API to port 8001, use:

```text
http://localhost:8001
```
instead of:
```text
http://localhost:8000
```

Example:
```bash
curl -i http://localhost:8001/health
```
