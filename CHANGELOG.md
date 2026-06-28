# Changelog

All notable changes documented here.
Format: [Keep a Changelog](https://keepachangelog.com/)
Versioning: [SemVer](https://semver.org/)

---

## [Unreleased]

### Added — Day 1 (Core Shortening Service)

**Infrastructure**
- Docker Compose: Postgres 16 + Redis 7 + FastAPI with healthchecks
- Dockerfile with non-root user and uv-based layer-cached install
- Alembic configured with autogenerate, sync URL for migrations
- GitHub Actions CI: ruff lint + ruff format + mypy + pytest on every PR
- Branch protection on `main` (CI must pass before merge)
- PR template, issue templates, CONTRIBUTING guide
- uv for dependency management, `uv.lock` committed for reproducibility
- pre-commit hooks: ruff, mypy, trailing-whitespace, detect-private-key

**Models**
- `User`: email, bcrypt password, auto-generated API key
- `Link`: short_code (unique), long_url, expiry, password hash,
  is_permanent, click_count, webhook fields
- `Click`: time-series fact table with composite indexes on
  `(link_id, clicked_at)`, `(link_id, country)`, `(link_id, browser)`
- Initial Alembic migration for all three tables

**API**
- `POST /api/v1/auth/register` — registration, returns API key
- `POST /api/v1/links` — create (alias, expiry, password, webhook, 301/302)
- `GET /api/v1/links` — list with cursor/keyset pagination
- `GET /api/v1/links/{code}` — retrieve single link
- `PATCH /api/v1/links/{code}` — partial update
- `DELETE /api/v1/links/{code}` — delete
- `GET /{short_code}` — 301/302 redirect with expiry + password support
- `POST /{short_code}/unlock` — password gate form submission
- `GET /health` — service + Redis status

**Services**
- Base62 random code generation using `secrets.choice()`
- Redis SETNX atomic reservation before DB insert
- `encode_base62()` / `decode_base62()` utility functions
- Consistent `{data, meta, errors}` response envelope
- `get_current_user` + `get_optional_user` auth dependencies

**Documentation**
- `README.md` — problem, solution, architecture, quickstart, API, tech
- `docs/JOURNAL.md` — Day 1 build log with decisions and rationale
- `docs/DESIGN_DECISIONS.md` — algorithm, pagination, envelope, lazy deletion
- `docs/ARCHITECTURE.md` — system diagram, ERD, request flows
- `docs/TECH_STACK.md` — every tool with justification
- `docs/ASSUMPTIONS.md` — assumptions, limitations, future work
- `docs/API.md` — endpoint reference with curl examples
- `docs/GEOIP_SETUP.md` — MaxMind setup instructions

### Planned
- **Day 2:** Redis cache-aside, write-through counters, rate limiting
- **Day 3:** Async analytics, GeoIP, UA parsing, webhooks, stats API
- **Day 4:** Dashboard, production deploy, v1.0.0 release tag
