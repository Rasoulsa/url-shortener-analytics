# Development Journal

Daily log of decisions, progress, blockers, and trade-offs.
Kept to demonstrate engineering process and reasoning.

---

## Day 1 — Core Shortening Service

**Goal:** Working end-to-end shorten → redirect with auth,
custom alias, expiry, and password protection.

### What I built

**Project foundation**
- Full folder structure, `pyproject.toml` with `uv`, Ruff lint+format,
  mypy, pre-commit hooks
- Docker Compose: Postgres 16 + Redis 7 + FastAPI, one-command boot
- GitHub: branch protection on `main`, CI workflow, PR/issue templates,
  conventional commits, feature-branch → PR → main workflow

**Database layer**
- `User`, `Link`, `Click` models with SQLAlchemy 2.0 async `mapped_column`
- `Click` designed as a time-series fact table with composite indexes:
  `(link_id, clicked_at)`, `(link_id, country)`, `(link_id, browser)`
  — anticipating Day 3 aggregation queries from the very start
- Alembic configured with autogenerate; initial migration created

**Authentication**
- API-key model: `secrets.token_urlsafe(32)` at registration
- `get_current_user` and `get_optional_user` FastAPI dependencies
- `POST /api/v1/auth/register` → returns `{data: {id, email, api_key}}`

**Short-code generation**
- Chose **Random Base62 + Redis SETNX** over counter-based approach
- `secrets.choice()` for cryptographic randomness (not `random`)
- SETNX atomically reserves the code before DB insert
  → eliminates the check-then-insert race condition entirely
- DB UNIQUE constraint as the final safety net
- Keyspace: 62^7 ≈ 3.5 trillion — collisions negligible in practice
- Transparent fallback: grow code length after max_tries exhausted

**Link CRUD**
- `POST /api/v1/links` — alias, expiry, password, webhook, 301/302
- `GET /api/v1/links` — cursor/keyset pagination (not offset)
- `GET /api/v1/links/{code}` — single retrieve
- `PATCH /api/v1/links/{code}` — partial update
- `DELETE /api/v1/links/{code}` — hard delete

**Redirect endpoint**
- `GET /{short_code}` — DB lookup → expiry → password gate → 301/302
- `POST /{short_code}/unlock` — password form submission
- Lazy deletion: expiry checked on access (410 Gone), no cleanup cron
- Synchronous click count today; TODO markers for Day 2/3 upgrades
- Clean HTML password gate with bcrypt verification

**Response design**
- `{data, meta, errors}` envelope on every endpoint from Day 1
- `meta.next_cursor` for cursor pagination

### Key decisions

**Random + SETNX over counter codes**
Counter codes are sequential → enumerable → an attacker can iterate
`abc0001`, `abc0002` and harvest all destination URLs. Random codes
from 62^7 keyspace are not enumerable. SETNX makes reservation atomic.

**Cursor pagination over offset**
`OFFSET 10000 LIMIT 20` forces Postgres to scan and discard 10k rows.
Keyset pagination (`WHERE id < cursor ORDER BY id DESC`) uses the index
directly — constant time at any depth.

**Design the Click table on Day 1**
Schema changes are cheap before data exists. The composite indexes I
need for Day 3 aggregations are already in place — no migration
required when analytics land.

**Response envelope from Day 1**
Retrofitting an envelope on a live API breaks all clients. Consistent
shape from the start means one response handler on the frontend.

**`main`-only branching**
Solo project. `develop` exists to protect `main` from broken
multi-developer integration — that problem doesn't apply here.
Feature branches → PR → main keeps the history clean and professional
without unnecessary complexity.

### Blockers / notes
- Router order critical: `/{short_code}` catch-all must be registered
  **last** in `main.py` or it shadows `/api/*` and `/docs`.
- `python-multipart` required for `Form(...)` in FastAPI. Added to deps.
- `uv sync` generates `uv.lock` automatically — committed to repo for
  reproducible installs in CI and Docker.

### Tomorrow — Day 2
- Redis cache-aside layer in front of redirect (hot path)
- Write-through click counter (Redis INCR, flushed to DB by Celery)
- Hot-link detection: auto-extend TTL for high-traffic links
- Lazy deletion upgrade: invalidate Redis cache on expired link
- Sliding-window rate limiting (anon by IP, auth by API key)
- Celery worker + beat scaffold (so Day 3 analytics slot straight in)

---

## Day 2 — *(to be completed)*
## Day 3 — *(to be completed)*
## Day 4 — *(to be completed)*
