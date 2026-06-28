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

**Request:**
\`\`\`json
{ "email": "user@example.com", "password": "minimum8chars" }
\`\`\`

**Response 201:**
\`\`\`json
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
\`\`\`

---

## Links

### POST `/api/v1/links` — Create
\`\`\`bash
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
\`\`\`

### GET `/api/v1/links` — List
\`\`\`bash
# First page
curl "http://localhost:8000/api/v1/links?limit=20" \
  -H "X-API-Key: YOUR_KEY"

# Next page
curl "http://localhost:8000/api/v1/links?cursor=42&limit=20" \
  -H "X-API-Key: YOUR_KEY"
\`\`\`

### GET `/api/v1/links/{short_code}` — Get one
### PATCH `/api/v1/links/{short_code}` — Update
### DELETE `/api/v1/links/{short_code}` — Delete (204 No Content)

---

## Redirect

### GET `/{short_code}`
- `302` temporary or `301` permanent redirect
- `404` if not found
- `410` if expired
- `200` HTML password form if protected

### POST `/{short_code}/unlock`
Form field: `password`

---

## Analytics *(Day 3)*

### GET `/api/v1/analytics/{short_code}?days=7`
Time-series breakdown by day, country, browser, device. *(Coming Day 3)*

---

## System

### GET `/health`
\`\`\`json
{
  "status": "ok",
  "version": "1.0.0",
  "dependencies": { "redis": "up" }
}
\`\`\`
