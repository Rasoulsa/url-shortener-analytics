# 🔗 URL Shortener & Analytics

![CI](https://github.com/Rasoulsa/url-shortener-analytics/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.13-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688)
![License](https://img.shields.io/badge/license-MIT-green)

A production-minded URL shortening service with intelligent Redis
caching, non-blocking analytics collection, and a live dashboard.

> **Build log:** [docs/JOURNAL.md](docs/JOURNAL.md) — daily decisions and trade-offs.

---

## Table of Contents
1. [Problem & Solution](#1-problem--solution)
2. [Short Code Generation Algorithm](#2-short-code-generation-algorithm)
3. [Architecture](#3-architecture)
4. [Installation & Execution](#4-installation--execution)
5. [API Usage](#5-api-usage)
6. [Technologies](#6-technologies)
7. [Assumptions & Limitations](#7-assumptions--limitations)
8. [Project Structure](#8-project-structure)

---

## 1. Problem & Solution

### Problem
Long URLs are hard to share, track, and manage. Teams need:
- Short, branded links with optional custom aliases
- High-speed redirects that never block on analytics
- Rich insight: who clicks, when, from where, on what device
- Protection against abuse and full lifecycle control

### Solution
A service that shortens, redirects, and analyzes:

| Principle | Implementation |
|-----------|---------------|
| Performance first | Redis cache-aside — redirects never hit the DB |
| Non-blocking analytics | Celery tasks process GeoIP + UA asynchronously |
| Privacy by design | IPs anonymized (last octet zeroed) before storage |
| Developer-friendly | Versioned REST API with Swagger + ReDoc |

### Features
- [x] API-key authenticated REST API (`/api/v1`)
- [x] Base62 short codes — unpredictable, collision-safe (SETNX)
- [x] Custom aliases, expiry dates, password-protected links
- [x] 301 (permanent) / 302 (temporary) redirect control
- [x] Consistent response envelope `{data, meta, errors}`
- [x] Cursor/keyset pagination
- [ ] Redis cache-aside + write-through counters *(Day 2)*
- [ ] Sliding-window rate limiting *(Day 2)*
- [ ] Async GeoIP + UA analytics pipeline *(Day 3)*
- [ ] Time-series stats API *(Day 3)*
- [ ] Webhooks on click thresholds *(Day 3)*
- [ ] Analytics dashboard *(Day 4)*

---

## 2. Short Code Generation Algorithm

This project uses **Random Base62 generation with Redis SETNX collision retry**.
Generated short codes use a configurable length, defaulting to `7` characters via:
```env
SHORT_CODE_LENGTH=7
```
The code alphabet is Base62:
```text
0-9, a-z, A-Z
```
This keeps generated URLs compact, URL-safe, and free from special characters.

### Considered approaches

| Approach | Throughput | Predictability | Storage / Operational Cost | Decision |
|---|---:|---:|---:|---|
| Counter-based encoding | Very high | Poor — sequential IDs are guessable | Low | Rejected |
| Random Base62 with collision retry | High | Good — codes are difficult to guess | Low | Chosen |
| Pre-generated pool | Very high at request time | Good if generated randomly | Higher — requires pool storage and refill workers | Rejected for Phase 1 |

### Why Random Base62 + SETNX was chosen

The project chooses **Random Base62 with collision retry** because it provides a strong balance for the Phase 1 requirements:

1. **Unpredictability**

   Random codes avoid exposing sequential database IDs. This makes it harder to guess valid short links.

2. **Good throughput**

   Generating a random Base62 string is fast and does not require a central database counter.

3. **Low operational complexity**

   Unlike a pre-generated pool, there is no need to maintain a background code-generation buffer.

4. **Race-condition-safe uniqueness**

   Redis is used to atomically reserve codes before database insertion:

   ```python
   redis_client.set(key, "1", nx=True, ex=ttl)
   ```

   The `nx=True` option gives Redis `SETNX` behavior: only one concurrent request can reserve a generated short code.

5. **Database safety net**

   PostgreSQL also enforces a unique index on `links.short_code`, so even if Redis is bypassed or unavailable, duplicate short codes are still rejected at the database layer.

### Collision handling

If a generated code is already reserved or already exists, the service retries generation. This gives the system collision safety while keeping codes short and random.

For this project scope, a default 7-character Base62 code gives a large key space:

```text
62^7 = 3,521,614,606,208 possible codes
```

That is sufficient for Phase 1 while keeping URLs compact.

## 3. Architecture

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

Full details → [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

---

## 4. Installation & Execution

### Prerequisites
- Docker + Docker Compose
- Git
- [uv](https://docs.astral.sh/uv/) (for local dev outside Docker)
- *(Optional)* MaxMind `GeoLite2-City.mmdb` → see [docs/GEOIP_SETUP.md](docs/GEOIP_SETUP.md)

### Quickstart

\`\`\`bash
# 1. Clone
git clone https://github.com/<your-username>/url-shortener-analytics.git
cd url-shortener-analytics

# 2. Configure environment
cp .env.example .env.dev

# 3. Build and start (migrations run automatically)
docker compose up --build

# 4. Open interactive docs
#    Swagger UI → http://localhost:8000/docs
#    ReDoc      → http://localhost:8000/redoc
\`\`\`

### Local dev (outside Docker)

\`\`\`bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install all deps
uv sync

# Activate virtual environment
source .venv/bin/activate

# Install git hooks
uv run pre-commit install
\`\`\`

### Useful commands

\`\`\`bash
# Stop stack
docker compose down

# Stop + remove volumes (clean slate)
docker compose down -v

# View API logs
docker compose logs -f api

# Run migrations manually
docker compose exec api alembic upgrade head

# Open Postgres shell
docker compose exec db psql -U postgres -d urlshort

# Code quality
uv run ruff check . --fix    # lint
uv run ruff format .          # format
uv run mypy app               # type check
uv run pytest -v              # tests
\`\`\`

---

## 5. API Usage

**Auth header:** `X-API-Key: your_key` (all `/api/v1/*` except register)

**Response envelope:**
\`\`\`json
{
  "data":   { ... },
  "meta":   { "next_cursor": null, "count": 1 },
  "errors": []
}
\`\`\`

### Register → get API key
\`\`\`bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@example.com","password":"secret123"}'
\`\`\`

### Create a short link
\`\`\`bash
curl -X POST http://localhost:8000/api/v1/links \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "long_url": "https://example.com/very/long/path",
    "custom_alias": "demo",
    "expires_at": "2026-12-31T23:59:59Z",
    "is_permanent": false
  }'
\`\`\`

### Use the short link
\`\`\`bash
curl -iL http://localhost:8000/demo
\`\`\`

### List links (paginated)
\`\`\`bash
# First page
curl "http://localhost:8000/api/v1/links?limit=20" \
  -H "X-API-Key: YOUR_KEY"

# Next page (use next_cursor from meta)
curl "http://localhost:8000/api/v1/links?cursor=42&limit=20" \
  -H "X-API-Key: YOUR_KEY"
\`\`\`

### Delete a link
\`\`\`bash
curl -X DELETE http://localhost:8000/api/v1/links/demo \
  -H "X-API-Key: YOUR_KEY"
\`\`\`

Full reference → [docs/API.md](docs/API.md)

---

## 6. Technologies

| Tool | Purpose |
|------|---------|
| FastAPI | Async web framework, auto OpenAPI docs |
| PostgreSQL 16 | Primary data store |
| Redis 7 | Cache, counters, rate limiting, SETNX |
| Celery | Async task queue for analytics |
| SQLAlchemy 2.0 | Async ORM with typed mapped columns |
| Alembic | Database migrations with autogenerate |
| Pydantic v2 | Validation, serialization, settings |
| geoip2 | Offline IP → country/city (MaxMind) |
| user-agents | Browser/OS/device type parsing |
| passlib[bcrypt] | Password hashing |
| uv | Fast Python package manager + lock file |
| Docker Compose | One-command dev environment |
| GitHub Actions | CI: lint + type-check + tests |
| Ruff | Linting + formatting (replaces flake8/black/isort) |
| mypy | Static type checking |
| pytest | Unit + integration tests |

Full justification → [docs/TECH_STACK.md](docs/TECH_STACK.md)

---

## 7. Assumptions & Limitations

See [docs/ASSUMPTIONS.md](docs/ASSUMPTIONS.md) for the full list.

**Key points:**
- API-key auth is sufficient for this evaluation scope
- GeoIP requires optional MaxMind file — gracefully degrades without it
- Click analytics have ≤30s lag by design (Redis buffer → Postgres flush)
- `clicks` table not partitioned in this build (documented as future work)

---

## 8. Project Structure

\`\`\`
url-shortener-analytics/
├── app/
│   ├── core/           config, database, redis, security
│   ├── models/         SQLAlchemy ORM models
│   ├── schemas/        Pydantic request/response schemas
│   ├── services/       business logic (shortener, cache, ratelimit)
│   ├── tasks/          Celery async tasks (Day 3)
│   ├── api/v1/         versioned route handlers
│   └── web/            dashboard templates (Day 4)
├── alembic/            database migrations
├── tests/              unit + integration tests
├── docs/               project documentation
├── .github/            CI workflows + PR/issue templates
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
├── uv.lock
└── README.md
\`\`\`

## License
MIT — see [LICENSE](LICENSE)
