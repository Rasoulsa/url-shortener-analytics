# Release Checklist

## v1.1.0 — Password Gate & Branded Frontend

**Date:** July 5, 2026
**Final tag:** `v1.1.0`
**Previous release:** `v1.0.0`

---

## 1. Scope

This release completes **all 5 frontend phases** with the addition of **F5: Password Gate**.

**Scope:**
- ✅ F5: Branded password gate extending base.html
- ✅ Template refactoring in `redirect.py` (Jinja2 instead of inline HTML)
- ✅ 7 new tests for password gate
- ✅ Version bump across all source files

**Out of scope (same as v1.0):**
- Production deployment (local Docker Compose only)
- Cloud infrastructure

**Backward compatibility:** ✅ Fully backward compatible with v1.0.0. No breaking changes, no database migrations.

---

## 2. Branches Completed

### v1.1.0 (This Release)

- [x] `feat/frontend-f5-passwordgate` — Password gate template + tests + version bump

### v1.0.0 (Previous Phases, Still Valid)

- [x] `feat/frontend-f1-foundation` — Base layout, responsive grid, Tailwind, auth.js
- [x] `feat/frontend-f2-auth` — Login/Signup forms, session mgmt, protected routes
- [x] `feat/frontend-f3-dashboard` — Link CRUD, custom alias, expiration, password toggle
- [x] `feat/frontend-f4-analytics` — Charts, geo table, referrers, browsers, compare
- [x] `feat/d4-api-envelope` — Response envelope, pagination
- [x] `feat/d4-openapi-docs` — Swagger/ReDoc documentation
- [x] `feat/d4-webhooks` — Click-threshold webhooks with HMAC signing
- [x] `feat/d4-dashboard-api` — Analytics aggregation endpoints
- [x] `test/d4-tests` — Cross-cutting tests
- [x] `ci/d4-pipeline` — CI validation (Ruff, mypy, pytest)
- [x] `docs/d4-final` — Final documentation

---

## 3. Password Gate (F5) Checklist

- [x] `app/templates/public/password_gate.html` — Jinja2 template extending base.html
  - [x] Inherits navbar (Login/Sign up buttons for guests)
  - [x] Inherits footer (API Docs, version stamp)
  - [x] Lock icon + password input + error messaging
  - [x] Form action to `/{short_code}/unlock`
  - [x] No auth guard — fully public

- [x] `app/api/v1/redirect.py` — Template refactoring
  - [x] Added `Jinja2Templates` import
  - [x] Removed old `_password_gate_html()` function (inline string builder)
  - [x] Added `_password_gate_response()` using `TemplateResponse`
  - [x] Updated 3 call sites: cache-hit GET, cache-miss GET, wrong-password POST
  - [x] Status codes preserved: 200 for gate, 403 for wrong password, 301/302 for success

- [x] `tests/test_f5_passwordgate.py` — 7 new tests
  - [x] `test_protected_link_shows_password_gate` — Gate renders (HTTP 200)
  - [x] `test_protected_gate_shows_no_error_by_default` — No error on first visit
  - [x] `test_protected_gate_inherits_base_nav` — Nav + footer inherited
  - [x] `test_wrong_password_reshows_gate_with_error` — 403, error message, form re-rendered
  - [x] `test_wrong_password_still_has_nav` — Error gate includes nav/footer
  - [x] `test_correct_password_redirects` — 301/302 to target URL
  - [x] `test_plain_link_redirects_without_gate` — Unprotected links unaffected

---

## 4. Frontend Completion Checklist

All 5 phases complete and integrated:

| Phase | Feature | Status | Tests |
|-------|---------|--------|-------|
| F1 | Foundation (base layout, Tailwind) | ✅ | ✅ |
| F2 | Authentication (login/signup, session) | ✅ | ✅ |
| F3 | Dashboard (link CRUD, password toggle) | ✅ | ✅ |
| F4 | Analytics (charts, geo, compare) | ✅ | ✅ |
| F5 | Password Gate (branded public gate) | ✅ | ✅ |

---

## 5. Backend Features (Unchanged, Still Valid)

All v1.0.0 features remain fully operational:

### Public API
- [x] Full OpenAPI / Swagger documentation
- [x] ReDoc documentation
- [x] URL versioning under `/api/v1/`
- [x] API-key security scheme
- [x] Consistent response envelope `{ data, meta, errors }`
- [x] Unified exception handling
- [x] Cursor-based pagination
- [x] Webhook support on click threshold

### Dashboard
- [x] `/dashboard` route (session-protected)
- [x] Jinja2 templates
- [x] Chart.js visualizations
- [x] Visits line chart (7/30/90 days)
- [x] Geographic breakdown (country table)
- [x] Top referrers
- [x] Top browsers
- [x] Multi-link comparison

### Core Features
- [x] URL shortening with custom alias
- [x] Expiration dates
- [x] Password protection
- [x] 301/302 redirect control
- [x] Base62 short code generation (collision-safe with SETNX)
- [x] Redis cache-aside (metadata, click counters, rate limiting)
- [x] PostgreSQL async with SQLAlchemy 2.0
- [x] Alembic migrations
- [x] Celery async task queue (GeoIP, analytics, webhooks)
- [x] Rate limiting (anonymous: 10/min, authenticated: 100/min)
- [x] GeoIP analytics (MaxMind GeoLite2, optional)

---

## 6. Local Handoff Checklist

- [x] Docker Compose stack works locally
- [x] `.env.example` provided
- [x] Migrations documented
- [x] API key registration documented
- [x] Swagger/ReDoc documented
- [x] Dashboard documented
- [x] Password gate documented
- [x] Webhook local receiver documented
- [x] GeoIP optional setup documented
- [x] Test commands documented

---

## 7. Final Quality Checks

Run from repository root:

```bash
# Code quality
uv run ruff check . --fix
uv run ruff format . --check
uv run mypy app/

# Tests
uv run pytest -v --tb=short
```

**Expected result:**
```basic
171 passed in ~17s (no warnings)
```

### Docker test (optional)
```bash
docker compose up --build -d
docker compose exec api uv run pytest -v
docker compose down
```

## 8. Version Bump Verification

Verify all version strings are updated to `1.1.0`:
```bash
grep -rn "1\.1\.0" app/ pyproject.toml README.md CHANGELOG.md | head -20
```

Expected files:

✅ pyproject.toml — version = "1.1.0"
✅ app/core/config.py — app_version: str = "1.1.0"
✅ app/core/openapi.py — version="1.1.0"
✅ app/main.py — version="1.1.0"
✅ README.md — all references to v1.1.0
✅ CHANGELOG.md — v1.1.0 entry at top
✅ docs/RELEASE_CHECKLIST.md — this file

## 9. Local Smoke Test

**Setup and start**
```bash
cp .env.example .env.dev
docker compose up --build -d
docker compose exec api alembic upgrade head
```

**Health checks**
```bash
# Health endpoint
curl -i http://localhost:8001/health

# Swagger UI
curl -s http://localhost:8001/docs | grep -q "title" && echo "✓ Swagger OK"

# ReDoc
curl -s http://localhost:8001/redoc | grep -q "ReDoc" && echo "✓ ReDoc OK"
```

**Test password gate**
```bash
# Register user
curl -X POST http://localhost:8001/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"testpass123"}' \
  | jq .

# Get API key (manually from response or check DB)
# For testing, use a known test key from conftest

# Create protected link
RESPONSE=$(curl -s -X POST http://localhost:8001/api/v1/links \
  -H "X-API-Key: test-api-key" \
  -H "Content-Type: application/json" \
  -d '{"long_url":"https://example.com/target","password":"secret123"}')

SHORT_CODE=$(echo $RESPONSE | jq -r '.data.short_code')
echo "Short code: $SHORT_CODE"

# Visit gate (should render HTML with password input)
curl -i http://localhost:8001/$SHORT_CODE | head -20

# Wrong password (should return 403 with error)
curl -i -X POST http://localhost:8001/$SHORT_CODE/unlock \
  -d "password=wrongpassword" | head -20

# Correct password (should return 301/302 redirect)
curl -i -X POST http://localhost:8001/$SHORT_CODE/unlock \
  -d "password=secret123"
```

**Cleanup**
```bash
docker compose down
```

## 10. Tagging

**From main branch**
```bash
git checkout main
git pull origin main

# Verify version files
grep -r "1\.1\.0" app/ pyproject.toml README.md | wc -l
# Expected: ~8+ matches

# Create annotated tag
git tag -a v1.1.0 -m "Release v1.1.0: Password Gate & Branded Frontend

All 5 frontend phases complete:
✅ F1: Foundation
✅ F2: Authentication
✅ F3: Dashboard
✅ F4: Analytics
✅ F5: Password Gate

Key changes:
- Password gate template (F5) extending base.html
- Template refactoring in redirect.py (Jinja2 instead of inline HTML)
- 7 new tests for password gate
- Version bump to 1.1.0 across all source files
- Celery eager mode warning fix

Backward compatible with v1.0.0
No breaking changes, no database migrations required
171 tests passing, 0 warnings

See docs/RELEASE_1_1_0.md for full release notes"

# Push tag
git push origin v1.1.0

# Verify
git tag
git show v1.1.0 --stat
```

## 11. GitHub Release (Optional)

If using GitHub CLI:
```bash
gh release create v1.1.0 \
  --title "v1.1.0 — Password Gate & Branded Frontend" \
  --notes-file docs/RELEASE_1_1_0.md \
  --latest

# Verify
gh release view v1.1.0
```

Or manually at: https://github.com/Rasoulsa/url-shortener-analytics/releases

## 12. Source Artifact Options

**GitHub (Automatic)**
ZIP and TAR archives are automatically generated by GitHub for each tag:
```awk
https://github.com/Rasoulsa/url-shortener-analytics/releases/tag/v1.1.0
```

**Manual ZIP**
```bash
git archive \
  --format=zip \
  --output ../url-shortener-analytics-v1.1.0.zip \
  v1.1.0
```

**Manual TAR.GZ**
```bash
git archive \
  --format=tar.gz \
  --prefix=url-shortener-analytics-v1.1.0/ \
  --output ../url-shortener-analytics-v1.1.0.tar.gz \
  v1.1.0
```

**Git bundle (with full history)**
```bash
git bundle create ../url-shortener-analytics-v1.1.0.bundle --all
```

## 13. Do Not Include in Artifacts

Excluded from release archives:
```text
.env
.env.dev
.venv/
__pycache__/
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage
htmlcov/
geoip/*.mmdb
node_modules/
.git/
.DS_Store
```

**Note:** GeoIP databases must be downloaded separately by each developer because MaxMind does not allow redistribution. See `docs/GEOIP_SETUP.md`.

## 14. Handoff Instructions for Recipients

**Via GitHub**
```bash
git clone https://github.com/Rasoulsa/url-shortener-analytics.git
cd url-shortener-analytics
git checkout v1.1.0

cp .env.example .env.dev
docker compose up --build -d
docker compose exec api alembic upgrade head

# Verify
curl http://localhost:8001/health
```

**Via ZIP Archive**
```bash
unzip url-shortener-analytics-v1.1.0.zip
cd url-shortener-analytics

cp .env.example .env.dev
docker compose up --build -d
docker compose exec api alembic upgrade head

# Verify
curl http://localhost:8001/health
```

**Via Git Bundle**
```bash
git bundle unbundle ../url-shortener-analytics-v1.1.0.bundle
cd url-shortener-analytics
git checkout v1.1.0

cp .env.example .env.dev
docker compose up --build -d
docker compose exec api alembic upgrade head
```

**Expected URLs After Setup**
```bash
Health:    http://localhost:8001/health
Swagger:   http://localhost:8001/docs
ReDoc:     http://localhost:8001/redoc
Dashboard: http://localhost:8001/dashboard
```

## 15. Final Release Checklist

Before tagging:
[ ] All tests pass: uv run pytest -v (171 tests)
[ ] No warnings: uv run pytest -v 2>&1 | grep -i warning returns nothing
[ ] Code quality: uv run ruff check . passes
[ ] Type checking: uv run mypy app/ passes
[ ] Formatting: uv run ruff format --check . passes
[ ] Version bumped everywhere (grep for 1.1.0)
[ ] CHANGELOG.md updated with v1.1.0 entry
[ ] RELEASE_1_1_0.md created
[ ] README.md mentions F5
[ ] All 5 frontend phases documented
[ ] Docker Compose smoke test passes
[ ] Password gate tested locally

After tagging:
[ ] Tag pushed to remote: git push origin v1.1.0
[ ] Tag visible on GitHub: https://github.com/Rasoulsa/url-shortener-analytics/releases
[ ] Release notes visible: https://github.com/Rasoulsa/url-shortener-analytics/releases/tag/v1.1.0
[ ] Archive downloads work (ZIP, TAR.GZ)

## 16. Summary

✅ v1.1.0 is complete and ready for release.

**What’s included:**
  - All 5 frontend phases (F1–F5)
  - Full backend (API, analytics, webhooks)
  - 171 tests, 0 failures, 0 warnings
  - Comprehensive documentation
  - Backward compatible with v1.0.0

**Next steps:**
  - Run final quality checks (section 7)
  - Run smoke test (section 9)
  - Tag release (section 10)
  - Push to GitHub (section 10)
  - Create GitHub release (section 11)
  - Archive and distribute (section 12)

**Release date:** July 5, 2026

**Tag:** `v1.1.0`

Enjoy! 🚀
