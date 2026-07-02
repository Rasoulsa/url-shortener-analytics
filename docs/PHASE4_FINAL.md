# Phase 4 Final Documentation

Project: URL Shortener with Analytics Dashboard
Production domain: https://www.matinrayaneharyan.ir
API base path: `/api/v1/`

## Summary

Phase 4 completes the public API, webhook workflow, analytics dashboard, cross-cutting tests, and project documentation for the URL Shortener with Analytics Dashboard.

The main deliverables are:

- Public API documentation through OpenAPI / Swagger.
- URL versioning under `/api/v1/`.
- Consistent API response envelope using `{ data, meta, errors }`.
- Cursor-based pagination for link listings.
- Webhook support when a click threshold is reached.
- Analytics dashboard with charts and summary tables.
- Dashboard data APIs for time-series, country breakdown, referrers, browsers, and multi-link comparison.
- Cross-cutting tests for API contracts, envelope behavior, webhooks, and dashboard endpoints.
- Final project documentation updates.

---

## Public API

### OpenAPI and Swagger

The API exposes interactive documentation through FastAPI's built-in documentation pages:

- Swagger UI: `/docs`
- ReDoc: `/redoc`
- OpenAPI JSON: `/openapi.json`

The OpenAPI schema documents:

- Router tags.
- Endpoint summaries.
- Endpoint descriptions.
- Request and response models.
- API-key authentication.
- Error response envelopes.
- Versioned API routes.

---

## URL Versioning

All public API endpoints are formalized under:

```text
/api/v1/
```

This keeps the public API stable and allows future versions such as /api/v2/ without breaking existing clients.

Example:
```text
GET /api/v1/links
POST /api/v1/links
GET /api/v1/analytics/{short_code}/timeseries
GET /api/v1/dashboard/compare
```

## Response Envelope

API responses use a consistent envelope:
```json
{
  "data": {},
  "meta": {},
  "errors": []
}
```

### Success Response

```json
{
  "data": {
    "short_code": "abc1234",
    "original_url": "https://example.com"
  },
  "meta": {
    "request_id": "optional-request-id"
  },
  "errors": []
}
```

### List Response

```json
{
  "data": [
    {
      "short_code": "abc1234",
      "original_url": "https://example.com"
    }
  ],
  "meta": {
    "limit": 20,
    "next_cursor": "eyJpZCI6MTIzfQ",
    "has_more": true
  },
  "errors": []
}
```

### Error Response

```json
{
  "data": null,
  "meta": {},
  "errors": [
    {
      "code": "not_found",
      "message": "Link not found",
      "field": null
    }
  ]
}
```

Unified exception handlers are used for common API errors including:

- Validation errors.
- Authentication errors.
- Authorization errors.
- Not found errors.
- Gone / expired link errors.
- Rate limit errors.
- Internal server errors.


## Cursor-Based Pagination

Link listing endpoints use cursor pagination instead of offset pagination.

Cursor pagination avoids slow large-offset scans and is more stable when records are inserted or deleted while clients are paging.

Example request:

```http
GET /api/v1/links?limit=20&cursor=eyJpZCI6MTIzfQ
```

Example response:

```json
{
  "data": [
    {
      "id": 124,
      "short_code": "nxt4567",
      "original_url": "https://example.org"
    }
  ],
  "meta": {
    "limit": 20,
    "next_cursor": "eyJpZCI6MTI0fQ",
    "has_more": true
  },
  "errors": []
}
```

When there are no more records:

```json
{
  "data": [],
  "meta": {
    "limit": 20,
    "next_cursor": null,
    "has_more": false
  },
  "errors": []
}
```

### Webhook Support

Links may define webhook settings so an external service can be notified when the link reaches a configured click threshold.

Supported behavior:

- A link stores a webhook target URL.
- A link stores a click threshold.
- Click counters are flushed through the analytics pipeline.
- When click_count reaches or crosses the configured threshold, a webhook task is triggered.
- Webhook delivery runs asynchronously through Celery.
- Delivery uses retry/backoff behavior.
- The event is protected with an idempotency guard so it only fires once per threshold configuration.
- The payload is signed with HMAC SHA-256.

Example webhook payload:

```json
{
  "event": "link.click_threshold_reached",
  "short_code": "abc1234",
  "click_count": 100,
  "threshold": 100,
  "timestamp": "2026-07-02T00:00:00Z"
}
```

Example webhook headers:

```http
Content-Type: application/json
X-Webhook-Event: link.click_threshold_reached
X-Webhook-Signature-256: sha256=<hmac-signature>
```

Webhook receivers should verify the HMAC signature before trusting the event.

### Analytics Dashboard

The dashboard is available at:

```text
/dashboard
```

The dashboard provides:

- Line chart for visits over the last 7, 30, and 90 days.
- Geographic breakdown by country.
- Top referrers.
- Top browsers.
- Multi-link comparison chart.


## Dashboard Data

The dashboard uses existing analytics data and additional aggregation endpoints where needed.

Main dashboard data types:

### Time-Series Visits

Used for the line chart.

```text
GET /api/v1/analytics/{short_code}/timeseries?days=7
GET /api/v1/analytics/{short_code}/timeseries?days=30
GET /api/v1/analytics/{short_code}/timeseries?days=90
```

### Country Breakdown

Used for the geographic breakdown table.

```text
GET /api/v1/analytics/{short_code}/countries
```

Example:

```json
{
  "data": [
    {
      "country": "Germany",
      "visits": 42
    },
    {
      "country": "United States",
      "visits": 31
    }
  ],
  "meta": {
    "short_code": "abc1234"
  },
  "errors": []
}
```

### Top Referrers

```text
GET /api/v1/analytics/{short_code}/referrers
```

Example:

```json
{
  "data": [
    {
      "referrer": "google.com",
      "visits": 80
    },
    {
      "referrer": "direct",
      "visits": 50
    }
  ],
  "meta": {
    "short_code": "abc1234"
  },
  "errors": []
}
```

### Top Browsers

```text
GET /api/v1/analytics/{short_code}/browsers
```

Example:

```json
{
  "data": [
    {
      "browser": "Chrome",
      "visits": 90
    },
    {
      "browser": "Safari",
      "visits": 30
    }
  ],
  "meta": {
    "short_code": "abc1234"
  },
  "errors": []
}
```

### Multi-Link Comparison

Used to compare multiple short links on one chart.

```text
GET /api/v1/dashboard/compare?codes=abc1234,def5678&days=30
```

Example:

```json
{
  "data": {
    "labels": [
      "2026-06-28",
      "2026-06-29",
      "2026-06-30"
    ],
    "series": [
      {
        "short_code": "abc1234",
        "values": [10, 12, 8]
      },
      {
        "short_code": "def5678",
        "values": [4, 6, 9]
      }
    ]
  },
  "meta": {
    "days": 30
  },
  "errors": []
}
```

## Testing

Phase 4 includes cross-cutting tests for:

- Response envelope contracts.
- Cursor pagination metadata.
- OpenAPI documentation availability.
- Webhook triggering.
- Webhook idempotency.
- Dashboard route availability.
- Dashboard aggregation endpoints.
- Multi-link comparison behavior.

The standard local verification commands are:

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy app
uv run pytest -q
```

Coverage improvements can be continued later if needed.
