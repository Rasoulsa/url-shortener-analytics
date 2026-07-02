# Local Handoff Guide

This guide explains how another developer or evaluator can run the URL
Shortener & Analytics project locally from source code.

Production deployment is intentionally out of scope for v1.0. The project is
designed to run locally using Docker Compose.

---

## 1. Requirements

Install:

- Git
- Docker
- Docker Compose
- Make

Optional, only if running tools directly on the host machine:

- Python 3.13+
- uv

---

## 2. Makefile Quick Start

This project includes a `Makefile` so local setup can be done with short
commands.

```bash
make setup
make up
make migrate
make smoke
make open-urls
```

Useful commands:

| Command | Purpose |
|---|---|
| `make setup` | Copy `.env.example` to `.env.dev` if missing |
| `make up` | Build and start Docker Compose services |
| `make migrate` | Run Alembic migrations |
| `make health` | Check API health |
| `make smoke` | Check health, docs, OpenAPI, and dashboard |
| `make open-urls` | Print local URLs |
| `make logs-api` | Follow API logs |
| `make logs-worker` | Follow Celery worker logs |
| `make worker-ping` | Check Celery worker |
| `make test-docker` | Run tests inside Docker |
| `make webhook-receiver` | Start local webhook receiver on port `9999` |

Expected local URLs:

```text
Health:    http://localhost:8001/health
Swagger:   http://localhost:8001/docs
ReDoc:     http://localhost:8001/redoc
OpenAPI:   http://localhost:8001/openapi.json
Dashboard: http://localhost:8001/dashboard
```

---

## 3. Get the source code

### Option A — Clone from GitHub

```bash
git clone git@github.com:Rasoulsa/url-shortener-analytics.git
cd url-shortener-analytics
git checkout v1.0.0
```

### Option B — Extract ZIP archive

```bash
unzip url-shortener-analytics-v1.0.0.zip -d url-shortener-analytics
cd url-shortener-analytics
```

### Option C — Clone from Git bundle

```bash
git clone url-shortener-analytics-v1.0.0.bundle url-shortener-analytics
cd url-shortener-analytics
git checkout v1.0.0
```

---

## 4. Create environment file

```bash
make setup
```

This copies:

```text
.env.example -> .env.dev
```

You can also do it manually:

```bash
cp .env.example .env.dev
```

Do not commit real secrets.

For Docker Compose, service hostnames should point to Docker service names:

```ini
POSTGRES_HOST=db
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2
```

If running the API directly on the host machine instead of Docker, use
localhost values:

```ini
POSTGRES_HOST=localhost
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2
```

---

## 5. Start local services

```bash
make up
```

Equivalent command:

```bash
docker compose up --build -d
```

Check containers:

```bash
make ps
```

Expected services:

```text
api
db
redis
worker
beat
```

---

## 6. Run migrations

```bash
make migrate
```

Equivalent command if there is no dedicated `migrate` service:

```bash
docker compose exec api alembic upgrade head
```

If `uv run alembic` fails inside Docker with a permission error, use plain
`alembic` inside the container:

```bash
docker compose exec api alembic upgrade head
```

---

## 7. Run smoke checks

```bash
make smoke
make open-urls
```

Expected output should show HTTP `200` for:

```text
Health
Swagger
ReDoc
OpenAPI
Dashboard
```

---

## 8. Register a user and get an API key

```bash
make register EMAIL=local@example.com PASSWORD=password123
```

Or manually:

```bash
curl -s -X POST http://localhost:8001/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "local@example.com",
    "password": "password123"
  }' | python3 -m json.tool
```

Copy the returned API key:

```bash
export API_KEY="paste-api-key-here"
```

---

## 9. Create a short link

Using Make:

```bash
make create-link API_KEY="$API_KEY" ALIAS=handoffdemo URL=https://example.com/local-handoff
```

Or manually:

```bash
ALIAS="handoff$(date +%s)"

curl -s -X POST http://localhost:8001/api/v1/links \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"long_url\": \"https://example.com/local-handoff\",
    \"custom_alias\": \"${ALIAS}\"
  }" | python3 -m json.tool
```

Test redirect:

```bash
make click ALIAS=handoffdemo
```

Or manually:

```bash
curl -i "http://localhost:8001/${ALIAS}"
```

Expected:

```text
HTTP/1.1 302 Found
location: https://example.com/local-handoff
```

---

## 10. Verify OpenAPI / Swagger

Open:

```text
http://localhost:8001/docs
http://localhost:8001/redoc
http://localhost:8001/openapi.json
```

Expected:

- Public API routes are under `/api/v1/`.
- Protected routes document API-key authentication.
- Responses use `{ data, meta, errors }`.

You can also run:

```bash
make openapi
make docs-check
```

---

## 11. Verify response envelope

Success example:

```bash
make links API_KEY="$API_KEY"
```

Or manually:

```bash
curl -s "http://localhost:8001/api/v1/links?limit=5" \
  -H "X-API-Key: $API_KEY" | python3 -m json.tool
```

Expected shape:

```json
{
  "data": [],
  "meta": {},
  "errors": []
}
```

Error example:

```bash
curl -s "http://localhost:8001/api/v1/links/doesnotexist" \
  -H "X-API-Key: $API_KEY" | python3 -m json.tool
```

Expected shape:

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

---

## 12. Verify cursor pagination

```bash
curl -s "http://localhost:8001/api/v1/links?limit=2" \
  -H "X-API-Key: $API_KEY" | python3 -m json.tool
```

Expected:

```text
meta.next_cursor
meta.limit
```

If `meta.next_cursor` is not null, use it for the next page:

```bash
CURSOR="paste-next-cursor-here"

curl -s "http://localhost:8001/api/v1/links?cursor=${CURSOR}&limit=2" \
  -H "X-API-Key: $API_KEY" | python3 -m json.tool
```

---

## 13. Verify analytics pipeline

Fire a click with test headers:

```bash
curl -i \
  -H "X-Forwarded-For: 81.2.69.142" \
  -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36" \
  -H "Referer: https://google.com" \
  "http://localhost:8001/handoffdemo"
```

Wait for Celery processing:

```bash
sleep 3
```

Query analytics:

```bash
make stats API_KEY="$API_KEY" ALIAS=handoffdemo
make breakdown-browser API_KEY="$API_KEY" ALIAS=handoffdemo
make breakdown-referrer API_KEY="$API_KEY" ALIAS=handoffdemo
```

Or manually:

```bash
curl -s "http://localhost:8001/api/v1/analytics/links/handoffdemo/timeseries?days=7" \
  -H "X-API-Key: $API_KEY" | python3 -m json.tool

curl -s "http://localhost:8001/api/v1/analytics/links/handoffdemo/breakdown?dimension=browser" \
  -H "X-API-Key: $API_KEY" | python3 -m json.tool

curl -s "http://localhost:8001/api/v1/analytics/links/handoffdemo/breakdown?dimension=referrer" \
  -H "X-API-Key: $API_KEY" | python3 -m json.tool
```

Expected:

- Standard `{ data, meta, errors }` envelope.
- Time-series rows for recent clicks.
- Browser/referrer breakdown data.

---

## 14. Verify dashboard

Open:

```text
http://localhost:8001/dashboard
```

Expected dashboard features:

- Visits line chart for 7 / 30 / 90 days.
- Geographic breakdown by country as a table.
- Top referrers.
- Top browsers.
- Multi-link comparison chart.

If charts are empty, generate clicks first and wait a few seconds for Celery.

---

## 15. Verify multi-link comparison

Create two links:

```bash
make create-link API_KEY="$API_KEY" ALIAS=comparea URL=https://example.com/a
make create-link API_KEY="$API_KEY" ALIAS=compareb URL=https://example.com/b
```

Fire clicks:

```bash
for i in 1 2 3; do make click ALIAS=comparea; done
for i in 1 2; do make click ALIAS=compareb; done
```

Wait for processing:

```bash
sleep 5
```

Query compare endpoint:

```bash
make compare API_KEY="$API_KEY" CODES=comparea,compareb
```

Expected:

```text
data.labels
data.series
```

Each series should have a `values` array with the same length.

---

## 16. Verify webhook support

### Start a local receiver on the host

Open a second terminal:

```bash
make webhook-receiver
```

This starts a receiver on:

```text
http://0.0.0.0:9999/webhook
```

### Create webhook-enabled link

From the project terminal:

```bash
make create-webhook-link \
  API_KEY="$API_KEY" \
  ALIAS=webhookdemo \
  URL=https://example.com/webhook-test \
  WEBHOOK_URL=http://host.docker.internal:9999/webhook \
  WEBHOOK_THRESHOLD=3
```

On macOS/Windows, `host.docker.internal` works from inside Docker.

On Linux, replace it with your host machine LAN IP, for example:

```text
http://192.168.1.20:9999/webhook
```

### Drive clicks past the threshold

```bash
make webhook-clicks ALIAS=webhookdemo
```

Wait for counter flush:

```bash
sleep 35
```

Expected in the receiver terminal:

```text
--- Webhook received ---
SIGNATURE: sha256=<hmac>
EVENT: link.click_threshold_reached
BODY: {"event": "link.click_threshold_reached", ...}
```

It should fire exactly once.

Confirm in database:

```bash
docker compose exec db psql -U postgres -d urlshort -c \
"SELECT short_code, click_count, webhook_threshold, webhook_fired
 FROM links WHERE short_code = 'webhookdemo';"
```

Expected:

```text
webhook_fired = t
```

---

## 17. Optional GeoIP setup

GeoIP is optional.

Without the MaxMind database:

- clicks still record
- browser / OS / device / referrer still work
- country and city are NULL

To enable country/city:

1. Create a free MaxMind account.
2. Download GeoLite2-City `.mmdb`.
3. Place it at:

```text
geoip/GeoLite2-City.mmdb
```

4. Restart API and worker:

```bash
docker compose up -d --build worker api
```

Check GeoIP:

```bash
make geoip-check
```

See:

```text
docs/GEOIP_SETUP.md
```

Do not redistribute the `.mmdb` file.

---

## 18. Run tests

Inside Docker:

```bash
make test-docker
```

Locally:

```bash
uv sync --all-extras
make test
```

Run quality checks:

```bash
make format-check
make lint
make type
```

Or all together:

```bash
make quality
```

---

## 19. Stop local stack

```bash
make down
```

Remove volumes and reset the local database:

```bash
make reset
```

---

## 20. Troubleshooting

### API is not reachable

```bash
make ps
make logs-api
```

### Migrations fail

```bash
make alembic-current
make alembic-history
make migrate
```

### Worker is unhealthy

The Celery worker is not an HTTP server. Do not use curl.

Use Celery inspection:

```bash
make worker-ping
```

### Dashboard is empty

Generate clicks first, then wait for Celery processing:

```bash
sleep 5
```

### Webhook receiver does not receive payload

Check:

- Receiver terminal is running.
- URL uses `host.docker.internal` on macOS/Windows.
- URL uses host LAN IP on Linux.
- `worker` logs show webhook delivery.
- `webhook_threshold` was crossed.
- `sleep 35` allowed the flush task to run.

```bash
make logs-worker
make logs-beat
```

---

## 21. v1.0 Feature Checklist

Public API:

- [x] Full OpenAPI / Swagger documentation
- [x] URL versioning under `/api/v1/`
- [x] Consistent response envelope `{ data, meta, errors }`
- [x] Cursor-based pagination for link listings
- [x] Webhook support when click threshold is reached

Analytics Dashboard:

- [x] Line chart for visits over 7 / 30 / 90 days
- [x] Geographic breakdown by country as a table
- [x] Top referrers
- [x] Top browsers
- [x] Multi-link comparison on a single chart
