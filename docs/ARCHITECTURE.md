# Architecture & Design

## 1. System Overview

\`\`\`
              ┌──────────────────────────────────────────────┐
  Client ───▶ │  FastAPI Application                          │
              │                                               │
              │  /api/v1/auth      Registration + API key    │
              │  /api/v1/links     CRUD + pagination          │
              │  /api/v1/analytics Time-series stats (Day 3) │
              │  /{short_code}     Redirect (hot path)        │
              │  /dashboard        Chart.js UI (Day 4)        │
              │  /health           System status              │
              └──────────────┬──────────────────┬────────────┘
                             │                  │
                 ┌───────────▼───────┐  ┌───────▼────────────┐
                 │  Redis            │  │  PostgreSQL         │
                 │  · cache-aside    │  │  · users            │
                 │  · write-through  │  │  · links            │
                 │  · rate limiting  │  │  · clicks (TS)      │
                 │  · SETNX reserve  │  └───────▲────────────┘
                 └───────────┬───────┘          │
                             │ enqueue    flush  │
                 ┌───────────▼──────────────────┴──────────┐
                 │  Celery Worker + Beat          (Day 3)   │
                 │  · GeoIP lookup (MaxMind offline)        │
                 │  · User-agent parsing                    │
                 │  · Counter flush to Postgres             │
                 │  · Webhook firing on threshold           │
                 └─────────────────────────────────────────┘
\`\`\`

## 2. Layered Architecture

\`\`\`
┌──────────────────────────────────────────────────┐
│  API Layer         app/api/v1/*                  │  HTTP, auth, validation
├──────────────────────────────────────────────────┤
│  Service Layer     app/services/*                │  Business logic
│  shortener · cache · ratelimit · analytics       │
├──────────────────────────────────────────────────┤
│  Data Layer        app/models/*                  │  SQLAlchemy ORM
├──────────────────────────────────────────────────┤
│  Infrastructure    Postgres · Redis · Celery     │
└──────────────────────────────────────────────────┘
\`\`\`

Routers stay thin (parse + validate + delegate).
Services hold all business logic.
Models own persistence.

## 3. Data Model (ERD)

\`\`\`
users                    links                        clicks
─────                    ─────                        ──────
id          PK     ┌───< id           PK        ┌───< id
email       UQ     │    short_code    UQ INDEX   │    link_id       FK
hashed_pw          │    long_url                 │    clicked_at
api_key     UQ     │    user_id       FK         │    ip_anonymized
created_at         │    password_hash             │    country
                   │    expires_at    INDEX       │    city
                   │    is_permanent              │    browser
                   │    click_count               │    os
                   │    webhook_url               │    device_type
                   │    webhook_threshold          │    referrer
                   │    webhook_fired              │
                   │    created_at                 │  Indexes:
                   │    updated_at                 │  (link_id, clicked_at)
                   └────                           │  (link_id, country)
                                                   │  (link_id, browser)
                                                   └────
\`\`\`

## 4. Request Flows

### Create short link
\`\`\`
POST /api/v1/links
  → auth (API key lookup)
  → validate payload (Pydantic)
  → if custom_alias: DB check + SETNX reserve
  → else: generate_unique_code (random + SETNX)
  → INSERT links row
  → 201 {data: LinkOut}
\`\`\`

### Redirect — Day 1 (DB only)
\`\`\`
GET /{short_code}
  → DB lookup
  → if not found: 404
  → if expired: 410 (lazy deletion)
  → if password_hash: return HTML form
  → click_count += 1 (sync)
  → 301 or 302
\`\`\`

### Redirect — Day 2 (with Redis cache)
\`\`\`
GET /{short_code}
  → Redis GET
  → HIT:  INCR counter → 301/302     ← fast path, no DB
  → MISS: DB lookup → SET cache → 301/302
\`\`\`

### Redirect — Day 3 (full async)
\`\`\`
GET /{short_code}
  → Redis GET
  → HIT:  record_click.delay(...) → return immediately
  → MISS: DB lookup → cache → record_click.delay(...) → return
  [worker]: GeoIP + UA parse + INSERT click + flush counter to DB
\`\`\`

## 5. Design Decisions
→ [DESIGN_DECISIONS.md](DESIGN_DECISIONS.md)
