# Release 1.1.0 — Password Gate & Branded Frontend

**Date:** July 5, 2026
**Tag:** `v1.1.0`
**Previous:** `v1.0.0`

## Summary

v1.1.0 completes all **5 frontend phases** with the addition of the **F5: Password Gate** — a branded, fully-public password-protected link gate that extends the base layout and inherits the navbar/footer for visual consistency.

**Backward compatible** with v1.0.0. No breaking changes or database migrations required.

---

## What's New

### F5: Password Gate Feature

A public-facing page for visitors who received a password-protected short link.

**Key aspects:**
- ✅ Fully **unauthenticated** — no VisionSAN account required to enter a password
- ✅ Extends `base.html` — inherits the public navbar (Logo + Home + Login + Sign up) and footer automatically
- ✅ Tailwind-styled card with lock icon, password input field, error messaging
- ✅ `GET /{short_code}` → renders gate (HTTP 200)
- ✅ `POST /{short_code}/unlock` with password form data:
  - **Correct password** → 301/302 redirect to target URL
  - **Wrong password** → 403, re-render gate with error message: _"Incorrect password. Try again."_
- ✅ Simple, focused UX — no distractions, no unnecessary fields

**Files:**
- `app/templates/public/password_gate.html` — Jinja2 template extending base.html
- `app/api/v1/redirect.py` — refactored `_password_gate_html()` → `_password_gate_response()`
- `tests/test_f5_passwordgate.py` — 7 new tests covering gate rendering, error handling, redirects

### Frontend Completion

All 5 phases are now complete and tested:

| Phase | Branch | Status | Focus |
|-------|--------|--------|-------|
| F1 | `feat/frontend-f1-foundation` | ✅ Complete | Base layout, responsive grid, Tailwind, auth.js navbar |
| F2 | `feat/frontend-f2-auth` | ✅ Complete | Login/Signup forms, session/cookie management, protected routes |
| F3 | `feat/frontend-f3-dashboard` | ✅ Complete | Link creation UI, custom alias, expiration, password toggle, API key display |
| F4 | `feat/frontend-f4-analytics` | ✅ Complete | Chart.js visualizations, geo table, top referrers/browsers, multi-link compare |
| F5 | `feat/frontend-f5-passwordgate` | ✅ Complete | Public password gate, Jinja2 template, branded UX |

### Testing

**New tests in this release:**
- `test_protected_link_shows_password_gate` — gate renders on protected link visit
- `test_protected_gate_shows_no_error_by_default` — no error message on first visit
- `test_protected_gate_inherits_base_nav` — nav and footer are inherited from base.html
- `test_wrong_password_reshows_gate_with_error` — 403, error message, form still visible
- `test_wrong_password_still_has_nav` — error gate includes base nav/footer
- `test_correct_password_redirects` — 301/302 to target URL
- `test_plain_link_redirects_without_gate` — non-protected links unaffected

**Total test suite:** 171 tests (164 from v1.0.0 + 7 new F5 tests)

**All passing, no warnings.**

---

## Backend Features (Unchanged from v1.0.0)

Still fully operational:
- ✅ URL shortening with custom alias, expiration, password protection
- ✅ Redis cache-aside (metadata, click counters, rate limiting)
- ✅ PostgreSQL async with SQLAlchemy 2.0 + Alembic migrations
- ✅ Celery async task queue (GeoIP lookup, analytics persistence, webhooks)
- ✅ API Key authentication for registered users
- ✅ REST API v1 with OpenAPI/Swagger docs
- ✅ Webhook support (click threshold, HMAC signing, retry logic)
- ✅ Session-based dashboard login
- ✅ Rate limiting (anonymous: 10/min, authenticated: 100/min)
- ✅ GeoIP analytics (MaxMind GeoLite2, optional)

---

## Migration Guide

**No database migrations required.** Schema is unchanged from v1.0.0.

### For Existing Installations

1. **Pull latest code:**
```bash
   git fetch origin
   git checkout v1.1.0
```

2. **Refresh dependencies (if using uv):**
```bash
  uv sync
```

3. **Restart the FastAPI app (no code changes affect hot reload):**
```bash
  docker compose restart api
  # or locally:
  # Ctrl+C and re-run uvicorn
```

4. **Run tests to verify:**
```bash
  uv run pytest -v
```

5. **Check password gate works:**
```bash
# Create a password-protected link
curl -X POST http://localhost:8000/api/v1/links \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"long_url":"https://example.com","password":"secret"}'

# Visit the short code
curl -i http://localhost:8000/abc123
# Should return 200 with the gate HTML

# Submit wrong password
curl -i -X POST http://localhost:8000/abc123/unlock \
  -d "password=wrong"
# Should return 403 with error message

# Submit correct password
curl -i -X POST http://localhost:8000/abc123/unlock \
  -d "password=secret"
# Should return 301/302 redirect
```

### Breaking Changes
None. v1.1.0 is fully backward compatible with v1.0.0 clients and deployments.

### Known Limitations
Same as v1.0.0:

- GeoIP database must be pre-downloaded (optional; see docs/GEOIP_SETUP.md)
- Password gate does not support 2FA (out of scope)
- Webhook retry uses naive exponential backoff (no jitter)
- Analytics retention is hard-coded (no user-configurable TTL)
- Single-region deployment only
- No JWT/OAuth (API-key auth only)

### Documentation Updates
All documentation has been reviewed and bumped to v1.1.0:

✅ README.md — version bump, F5 summary added to feature list
✅ docs/RELEASE_CHECKLIST.md — reference updated to v1.1.0
✅ docs/ARCHITECTURE.md — unchanged, applies to both v1.0 and v1.1
✅ docs/API.md — version updated in OpenAPI spec
✅ docs/ANALYTICS.md — unchanged
✅ docs/DESIGN_DECISIONS.md — unchanged
✅ docs/TECH_STACK.md — unchanged
✅ docs/LOCAL_DEVELOPMENT.md — unchanged
✅ docs/GEOIP_SETUP.md — unchanged
✅ docs/ASSUMPTIONS.md — unchanged
✅ docs/JOURNAL.md — unchanged

### Contributors
RasoulSa (F1–F5 frontend implementation, full-stack integration)

### Deployment
**Docker Compose (Recommended)**
```bash
git clone https://github.com/Rasoulsa/url-shortener-analytics.git
cd url-shortener-analytics
git checkout v1.1.0

cp .env.example .env.dev
docker compose up --build

# Migrations run automatically
# Visit: http://localhost:8001/docs
```

**Local Development**
```bash
git checkout v1.1.0
uv sync
source .venv/bin/activate

# Start FastAPI
uv run uvicorn app.main:app --reload

# In another terminal, start worker + beat
uv run celery -A app.tasks.celery_app worker --loglevel=info
uv run celery -A app.tasks.celery_app beat --loglevel=info
```

### Validation Checklist**
```bash
# Code quality
uv run ruff check . --fix
uv run ruff format . --check
uv run mypy app

# Tests
uv run pytest -v --tb=short

# Docker
docker compose up --build -d
docker compose exec api uv run pytest -v
docker compose down
```

All checks should pass with 171 tests, 0 failures, 0 warnings.

### Commits in This Release
```bash
git log v1.0.0..v1.1.0 --oneline
```

Key commits:

  - `feat(frontend): branded password gate page extending base.html (F5)`
  - `fix(services): skip analytics queue enqueue in eager mode to suppress AlwaysEagerIgnored warning`

### Next Steps
- **v1.2.0 candidates:** JWT auth, 2FA, soft delete, table partitioning, multi-region support
- **Deployment:** Cloud deployment (AWS/GCP/Heroku) with HTTPS, CDN, managed PostgreSQL, managed Redis
- **Dashboard enhancements:** Map visualization, real-time updates, export to CSV

### License
MIT — see [LICENSE](LICENSE)

**Enjoy your URL shortener with password-protected analytics!** 🚀
