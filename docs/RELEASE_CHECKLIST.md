# v1.0 Release Checklist

Release branch:

```text
release/v1.0
```

Final tag:

```text
v1.0.0
```

---

## 1. Scope

This release completes Phase 4 of the URL Shortener & Analytics project.

Production deployment is intentionally out of scope for this release. The
project is released as a local Docker Compose application that can be run from
source code by another developer or evaluator.

---

## 2. Branches Completed

- [x] `feat/d4-api-envelope`
- [x] `feat/d4-openapi-docs`
- [x] `feat/d4-webhooks`
- [x] `feat/d4-dashboard-api`
- [x] `feat/d4-dashboard-ui`
- [x] `test/d4-tests`
- [x] `ci/d4-pipeline`
- [x] `docs/d4-final`

Deferred:

- [ ] `chore/d4-deploy`

Reason: production deployment is not required for the local v1.0 handoff.

---

## 3. Public API Checklist

- [x] Full OpenAPI / Swagger documentation
- [x] ReDoc documentation
- [x] URL versioning under `/api/v1/`
- [x] API-key security scheme in Swagger
- [x] Consistent response envelope `{ data, meta, errors }`
- [x] Unified exception handling
- [x] Cursor-based pagination for link listings
- [x] Webhook support on click threshold crossing

---

## 4. Dashboard Checklist

- [x] `/dashboard` route
- [x] Jinja2 templates
- [x] Chart.js integration
- [x] Visits line chart for 7 / 30 / 90 days
- [x] Geographic breakdown by country table
- [x] Top referrers
- [x] Top browsers
- [x] Multi-link comparison chart

---

## 5. Local Handoff Checklist

- [x] Docker Compose stack works locally
- [x] `.env.example` provided
- [x] Makefile provided for local setup and validation
- [x] Migrations documented
- [x] API key registration documented
- [x] Swagger/ReDoc documented
- [x] Dashboard documented
- [x] Webhook local receiver documented
- [x] GeoIP optional setup documented
- [x] Test commands documented
- [x] Source archive options documented

---

## 6. Final Quality Checks

Run from the repository root:

```bash
make format-check
make lint
make type
make test
```

Equivalent manual commands:

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy app/
uv run pytest -v
```

Optional Docker test:

```bash
make up
make test-docker
```

Equivalent manual command:

```bash
docker compose up --build -d
docker compose exec api uv run pytest -v
```

---

## 7. Local Smoke Test

Start stack:

```bash
make setup
make up
make migrate
make smoke
make open-urls
```

Equivalent manual commands:

```bash
cp .env.example .env.dev
docker compose up --build -d
docker compose exec api alembic upgrade head
curl -i http://localhost:8001/health
```

Check docs:

```text
http://localhost:8001/docs
http://localhost:8001/redoc
```

Check dashboard:

```text
http://localhost:8001/dashboard
```

---

## 8. Tagging

After `release/v1.0` is merged into `main`:

```bash
git checkout main
git pull origin main
git tag -a v1.0.0 -m "v1.0.0 - Public API, webhooks, and analytics dashboard"
git push origin v1.0.0
```

Verify:

```bash
git tag
git show v1.0.0 --stat
```

---

## 9. Source Artifact Options

GitHub automatically provides source ZIP/TAR archives for tags.

Manual ZIP:

```bash
make archive-zip REF=v1.0.0
```

Equivalent manual command:

```bash
git archive \
  --format=zip \
  --output ../url-shortener-analytics-v1.0.0.zip \
  v1.0.0
```

Manual TAR:

```bash
make archive-tar REF=v1.0.0
```

Equivalent manual command:

```bash
git archive \
  --format=tar.gz \
  --prefix=url-shortener-analytics-v1.0.0/ \
  --output ../url-shortener-analytics-v1.0.0.tar.gz \
  v1.0.0
```

Git bundle with history:

```bash
make bundle
```

Equivalent manual command:

```bash
git bundle create ../url-shortener-analytics-v1.0.0.bundle --all
```

---

## 10. Do Not Include

Do not include local secrets or generated files in release artifacts:

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
```

GeoIP databases must be downloaded separately by each developer because
MaxMind does not allow redistribution.

---

## 11. Handoff Instructions for Recipient

If using GitHub:

```bash
git clone git@github.com:Rasoulsa/url-shortener-analytics.git
cd url-shortener-analytics
git checkout v1.0.0
make setup
make up
make migrate
make smoke
make open-urls
```

If using ZIP:

```bash
unzip url-shortener-analytics-v1.0.0.zip -d url-shortener-analytics
cd url-shortener-analytics
make setup
make up
make migrate
make smoke
make open-urls
```

Expected URLs:

```text
Health:    http://localhost:8001/health
Swagger:   http://localhost:8001/docs
ReDoc:     http://localhost:8001/redoc
Dashboard: http://localhost:8001/dashboard
```

---

## 12. Final Release Branch Commands

From `release/v1.0`:

```bash
make format
make lint
make type
make test

make setup
make up
make migrate
make smoke
make worker-ping

git status
git add VERSION CHANGELOG.md Makefile docs/LOCAL_HANDOFF.md docs/RELEASE_CHECKLIST.md
git commit -m "chore(release): prepare v1.0 local handoff"
git push -u origin release/v1.0
```

After PR merge:

```bash
git checkout main
git pull origin main
git tag -a v1.0.0 -m "v1.0.0 - Public API, webhooks, and analytics dashboard"
git push origin v1.0.0
```

Create ZIP:

```bash
make archive-zip REF=v1.0.0
```
