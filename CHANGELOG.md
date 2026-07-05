# Changelog

## v1.1.0 — Password Gate & Branded Frontend (July 5, 2026)

### New Features
- **F5: Password Gate** — Branded, fully-public password-protected link gate extending base.html
  - No VisionSAN account required to enter password
  - Tailwind-styled card with lock icon, password input, error handling
  - `POST /{short_code}/unlock` validates password → redirects (301/302) or re-renders error (403)
  - Inherits navbar and footer from base.html for visual consistency

### Frontend Completion
All 5 frontend phases now complete:
- ✅ F1: Foundation (base layout, responsive grid, Tailwind)
- ✅ F2: Authentication (login/signup, session management, protected routes)
- ✅ F3: Dashboard (link creation, custom alias, expiration, password protection)
- ✅ F4: Analytics (charts, geographic breakdown, referrers, multi-link comparison)
- ✅ F5: Password Gate (public password-protected link interface)

### Testing
- 171 test cases across all 5 frontend phases
- Fixed Celery eager mode warning in analytics queue service
- All tests passing with no warnings

### Backward Compatibility
✅ Fully backward compatible with v1.0.0. No breaking changes, no DB migrations required.

---

# Changelog

All notable changes to this project are documented here.

---

## v1.0.0 — Public API, Webhooks & Analytics Dashboard

Release date: 2026-07-02

### Added

#### Public API

- Full OpenAPI / Swagger documentation.
- ReDoc documentation.
- URL versioning under `/api/v1/`.
- API-key authentication documented in Swagger.
- Consistent response envelope:

```json
{
  "data": {},
  "meta": {},
  "errors": []
}
```

- Unified exception handlers for:

    - validation errors
    - unauthorized errors
    - not found errors
    - expired link errors
    - rate-limit errors
    - internal server errors
- Cursor-based pagination for link listings.

- Public API documentation through:

    - `/docs`
    - `/redoc`
    - `/openapi.json`

**Webhooks**

- Click-threshold webhook support.
- Webhook fires when `click_count` crosses `webhook_threshold`.
- Threshold detection integrated into `analytics.flush_click_counters`.
- Webhook delivery handled asynchronously by Celery.
- HMAC SHA-256 webhook signature.
- Retry/backoff for transient receiver failures.
- `webhook_fired` idempotency guard to prevent duplicate threshold events.

**Analytics Dashboard**

- Dashboard route at /dashboard.
- Jinja2 server-rendered templates.
- Chart.js visualizations.
- Visits line chart for:
  - last 7 days
  - last 30 days
  - last 90 days
- Geographic breakdown by country as a table.
- Top referrers.
- Top browsers.
- Multi-link comparison on a single chart.

**Analytics Pipeline**

- Non-blocking click collection.
- Celery task for click enrichment.
- GeoIP country/city lookup.
- User-Agent parsing.
- IP anonymization before storage.
- PostgreSQL clicks event table.
- Redis click counters.
- Celery Beat counter flushing to PostgreSQL.

**Infrastructure**

- FastAPI application.
- PostgreSQL source of truth.
- Redis cache/counters/rate-limits.
- Celery worker.
- Celery Beat scheduler.
- Docker Compose local development stack.

**Documentation**

- API documentation.
- Architecture documentation.
- Analytics documentation.
- Design decisions.
- Assumptions and limitations.
- Local development guide.
- Local handoff guide.
- GeoIP setup guide.
- Final documentation.

### Completed Scope**

**Public API**
[x] Full OpenAPI / Swagger documentation
[x] URL versioning: `/api/v1/`
[x] Consistent response envelope: `{ data, meta, errors }`
[x] Cursor-based pagination for link listings
[x] Webhook support: fire an event to a configured URL when a click threshold is reached

**Analytics Dashboard**
[x] Line chart: visits over the last 7 / 30 / 90 days
[x] Geographic breakdown: visit distribution by country
[x] Top referrers
[x] Top browsers
[x] Multi-link comparison on a single chart

### Known Limitations

- Local Docker execution only for v1.0.
- Production deployment branch intentionally deferred.
- GeoIP database is optional and must be downloaded separately from MaxMind.
- Dashboard uses a country table, not a map.
- One webhook threshold event per link.
- API-key authentication only; no JWT/OAuth yet.
- No email verification.
- No soft delete.
- Single-region architecture.
- `clicks` table is indexed but not partitioned yet.
