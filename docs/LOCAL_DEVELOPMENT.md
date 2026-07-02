# Local Development

## Requirements

- Python 3.13+
- uv
- Docker
- Docker Compose

---

## Setup

Clone the repository:

```bash
git clone git@github.com:Rasoulsa/url-shortener-analytics.git
cd url-shortener-analytics
```

Install dependencies:

```bash
uv sync --all-extras
```

Create local environment file:

```bash
cp .env.example .env.dev
```

If you plan to test GeoIP enrichment locally, see [GEOIP_SETUP.md](GEOIP_SETUP.md)
— it's optional and everything else works without it.

---

## Run with Docker

Build and start all services:

```bash
docker compose up --build
```

Run in detached mode:

```bash
docker compose up --build -d
```

Run migrations:

```bash
docker compose run --rm migrate
```

> If `migrate` isn't defined as its own service, run migrations directly
> against the `api` container instead — see
> [Migration troubleshooting](#migration-troubleshooting) below.

View logs:

```bash
docker compose logs -f api
```

View worker logs:

```bash
docker compose logs -f worker
```

View beat (scheduler) logs:

```bash
docker compose logs -f beat
```

Stop:

```bash
docker compose down
```

Stop and remove volumes:

```bash
docker compose down -v
```

---

## Run Without Docker

If running the API directly on your machine, change local env values from Docker service names to localhost:

```ini
POSTGRES_HOST=localhost
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2
```

Then run:

```bash
uv run uvicorn app.main:app --reload
```

---

## Tests

Run all tests:

```bash
uv run pytest
```

Run shortener tests:

```bash
uv run pytest tests/test_shortener.py -v
```

Run analytics tests:

```bash
uv run pytest tests/test_analytics.py -v
```

Run inside Docker instead of locally:

```bash
docker compose exec api uv run pytest
```

---

## Code Quality

Ruff check:

```bash
uv run ruff check .
```

Ruff format:

```bash
uv run ruff format .
```

Mypy:

```bash
uv run mypy app/
```

---

## Environment Files

| File | Committed? | Purpose |
|---|---|---|
| .env.example | Yes | Safe template |
| .env.dev | No | Local Docker development config |
| .env | No | Personal local overrides |

Do not commit real secrets.

---

## Migration Troubleshooting

Alembic has two invocation styles depending on where you're running it. Both
have caused real issues locally — use these workarounds.

**`uv run alembic` inside the container fails with a permission error:**
```text
PermissionError: [Errno 13] Permission denied: '/home/appuser/.cache/uv'
```
The container's non-root user can't write `uv`'s cache directory. Skip `uv run`
and call `alembic` directly instead:
```bash
docker compose exec api alembic upgrade head
```

**`DuplicateTable` error on `clicks` (or any table):**
```text
sqlalchemy.exc.ProgrammingError: relation "clicks" already exists
```
This means a table was created outside of, or ahead of, Alembic's tracked
revision history (e.g. an earlier partial migration run). Check current state
and revision history before retrying:
```bash
docker compose exec api alembic current
docker compose exec api alembic history
```
If the table genuinely already matches the target schema, stamp the revision
without re-running the DDL:
```bash
docker compose exec api alembic stamp <revision_id>
```
Then continue with `alembic upgrade head` for any remaining revisions.

**Missing table during upgrade (e.g. `relation "clicks" does not exist`):**
Usually means migrations are being applied out of order — a later migration
(e.g. adding enrichment columns) ran before the migration that creates the
base table. Check `docker compose exec api alembic history` for the correct
order and re-run from the earliest missing revision.

---

## Phase 2 Redis/Celery Validation

Phase 2 adds Redis caching, Redis counters, Redis-backed rate limiting, and Celery
workers. Use the commands below to validate the local Docker setup.

---

### Check containers
```bash
docker compose ps
```
Expected:
```text
api      healthy
beat     running
db       healthy
redis    healthy
worker   healthy
```

> `beat` (the Celery scheduler, added in Phase 3) typically shows as `running`
> rather than `healthy` — it has no meaningful healthcheck of its own since it
> only dispatches scheduled tasks to the worker.

If one service is unhealthy, inspect logs:
```bash
docker compose logs -f api
docker compose logs -f worker
docker compose logs -f beat
docker compose logs -f redis
docker compose logs -f db
```

---

### Check API health

```bash
curl -i http://localhost:8001/health
```
Expected:
```text
HTTP/1.1 200 OK
```

---

### Check Redis DB separation

Redis logical databases are separated by purpose:
```text
DB 0 -> API cache, click counters, rate-limit keys, analytics counters
DB 1 -> Celery broker
DB 2 -> Celery result backend
```

#### Inspect Redis DB 0:
```bash
docker compose exec redis redis-cli -n 0 keys '*'
```

#### Inspect Redis DB 1:
```bash
docker compose exec redis redis-cli -n 1 keys '*'
```

#### Inspect Redis DB 2:
```bash
docker compose exec redis redis-cli -n 2 keys '*'
```

#### Inspect Redis keyspace summary:
```bash
docker compose exec redis redis-cli info keyspace
```
Expected:
```text
db0 -> app cache, counters, rate-limit, analytics keys
db1 -> Celery broker keys
db2 -> Celery result keys
```

---

### Test metadata cache

Set your API key:
```bash
export API_KEY="your-api-key-here"
```

Create a test alias:
```bash
ALIAS="cachetest$(date +%s)"
```

Create a short link:
```bash
curl -i -X POST \
  'http://localhost:8001/api/v1/links' \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $API_KEY" \
  -d "{
    \"long_url\": \"https://example.com/cache-test\",
    \"custom_alias\": \"${ALIAS}\"
  }"
```

Trigger redirect once:
```bash
curl -i "http://localhost:8001/${ALIAS}"
```

Check Redis metadata cache:
```bash
docker compose exec redis redis-cli -n 0 get "link:${ALIAS}:meta"
```

Check metadata TTL:
```bash
docker compose exec redis redis-cli -n 0 ttl "link:${ALIAS}:meta"
```
Expected:
```text
Redis should contain metadata at key:
link:{short_code}:meta

TTL should be positive.
```
Example key:
```text
link:cachetest1782814996:meta
```

---

### Test click counter

Run several redirects:
```bash
for i in 1 2 3; do
  curl -s -o /dev/null -w "%{http_code}\n" "http://localhost:8001/${ALIAS}"
done
```

Check Redis click counter:
```bash
docker compose exec redis redis-cli -n 0 get "link:${ALIAS}:clicks"
```
Expected:
```text
"3"
```
The value may be higher if the alias was clicked before this test.

When using zsh, always use braces:
```bash
"link:${ALIAS}:clicks"
```
Do not use:
```bash
"link:$ALIAS:clicks"
```
The second form can be parsed incorrectly by the shell.

---

### Test rate limiting

For local testing, temporarily use low values in .env.dev:
```ini
RATE_LIMIT_REDIRECT_REQUESTS=3
RATE_LIMIT_WINDOW_SECONDS=60
```

Restart the API after changing env values:
```bash
docker compose up --build -d
```

Run repeated redirect requests:
```bash
for i in 1 2 3 4 5; do
  curl -s -o /dev/null -w "%{http_code}\n" "http://localhost:8001/${ALIAS}"
done
```
Expected:
```text
302
302
302
429
429
```
A 429 Too Many Requests response should include headers similar to:
```text
Retry-After: <seconds>
X-RateLimit-Limit: <limit>
X-RateLimit-Remaining: 0
```
Check rate-limit keys in Redis DB 0:
```bash
docker compose exec redis redis-cli -n 0 keys 'rate_limit:*'
```
Expected:
```text
rate_limit:redirect:{identifier_hash}
rate_limit:api:{identifier_hash}
rate_limit:auth:{identifier_hash}
```
Identifiers are hashed before being stored in Redis keys.

---

### Test Celery registered tasks

Check registered Celery tasks:
```bash
docker compose exec worker celery -A app.tasks.celery_app:celery_app inspect registered
```
Expected tasks:
```text
analytics.process_click_event
analytics.flush_click_counters
webhooks.send_webhook_event
health.ping
```

---

### Test Celery worker ping

Run Celery inspection ping:
```bash
docker compose exec worker celery -A app.tasks.celery_app:celery_app inspect ping --timeout=5
```
Expected:
```text
pong
```

The exact output may include the worker name, for example:
```text
celery@<container-id>: OK
    pong
```

---

### Test Celery health task

Run a Celery task from the API container:
```bash
docker compose exec -T api python - <<'PY'
from app.tasks.health import ping

result = ping.delay()
print(result.get(timeout=10))
PY
```
Expected:
```text
pong
```

---

### Validate Celery Redis databases

Celery broker keys should appear in Redis DB 1:
```bash
docker compose exec redis redis-cli -n 1 keys '*'
```
Celery result keys may appear in Redis DB 2 after running a task:
```bash
docker compose exec redis redis-cli -n 2 keys '*'
```
Expected:
```text
DB 1 contains broker/queue keys.
DB 2 contains result backend keys after task execution.
```

---

### Important worker healthcheck note

The Celery worker (and beat) does not run an HTTP server.

This is valid for the API:
```bash
curl http://localhost:8001/health
```
This is **not** valid for the worker or beat, and will hang / fail to connect:
```bash
curl http://worker:8000
```

Worker health should be checked with Celery inspection:
```bash
docker compose exec worker celery -A app.tasks.celery_app:celery_app inspect ping --timeout=5
```

---

### Useful Redis debug commands

List all app keys:
```bash
docker compose exec redis redis-cli -n 0 keys '*'
```

Get cached metadata:
```bash
docker compose exec redis redis-cli -n 0 get "link:${ALIAS}:meta"
```

Get metadata TTL:
```bash
docker compose exec redis redis-cli -n 0 ttl "link:${ALIAS}:meta"
```

Get click counter:
```bash
docker compose exec redis redis-cli -n 0 get "link:${ALIAS}:clicks"
```

List rate-limit keys:
```bash
docker compose exec redis redis-cli -n 0 keys 'rate_limit:*'
```

Check Redis keyspace:
```bash
docker compose exec redis redis-cli info keyspace
```

---

### Useful PostgreSQL debug commands

Open Postgres shell:
```bash
docker compose exec db psql -U postgres -d urlshort
```

Check link row:
```sql
SELECT id, short_code, long_url, click_count, created_at
FROM links
ORDER BY id DESC
LIMIT 5;
```

Check specific alias:
```sql
SELECT id, short_code, long_url, click_count
FROM links
WHERE short_code = 'your_alias_here';
```

Exit Postgres:
```sql
\q
```

---

### Phase 2 expected failure behavior

| Component failure | Expected behavior |
|---|---|
| Redis metadata cache unavailable | Fall back to PostgreSQL lookup |
| Redis click counter unavailable | Fall back to PostgreSQL click increment |
| Redis rate limiter unavailable | Fail open and allow request |
| Celery broker unavailable | Log warning; redirect still succeeds |
| Celery worker unavailable | Tasks may queue; redirect still succeeds |
| PostgreSQL unavailable | API management and cache misses fail normally |

---

## Phase 3 Analytics Validation

Phase 3 adds click enrichment (GeoIP + User-Agent), durable counter flushing via
Celery Beat, and a stats API. Use the commands below to validate the pipeline
end to end.

---

### Check the clicks table exists

```bash
docker compose exec db psql -U postgres -d urlshort -c "\d clicks"
```
Expected columns:
```text
id, link_id, clicked_at, ip_anonymized, country, city,
browser, os, device_type, referrer, user_agent
```

If the table is missing or migrations are out of order, see
[Migration troubleshooting](#migration-troubleshooting) above.

---

### Verify GeoIP database is mounted (optional)

```bash
docker compose exec worker ls -la /data/
```
Expected:
```text
GeoLite2-City.mmdb
```

If the file is absent, GeoIP lookups fail open — clicks still record, but
`country`/`city` are NULL. This is expected and documented in
[GEOIP_SETUP.md](GEOIP_SETUP.md).

Test GeoIP lookup directly against known IPs:
```bash
docker compose exec -T worker python - <<'PY'
from app.services.geoip import lookup_geoip
for ip in ["8.8.8.8", "1.1.1.1", "81.2.69.142", "127.0.0.1"]:
    print(ip, lookup_geoip(ip))
PY
```
Expected:
```text
8.8.8.8     country only (Google infra IP, no city in GeoLite2)
1.1.1.1     country only (Cloudflare infra IP, no city in GeoLite2)
81.2.69.142 country=United Kingdom, city=London (known MaxMind test IP)
127.0.0.1   empty (private/local IP, never resolves)
```

---

### Test full click enrichment

Create a fresh alias and trigger a redirect with a spoofed public IP,
realistic User-Agent, and referrer:
```bash
ALIAS="analytics$(date +%s)"

curl -i -X POST \
  'http://localhost:8001/api/v1/links' \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $API_KEY" \
  -d "{
    \"long_url\": \"https://example.com/analytics-test\",
    \"custom_alias\": \"${ALIAS}\"
  }"

curl -i \
  -H "X-Forwarded-For: 81.2.69.142" \
  -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36" \
  -H "Referer: https://google.com" \
  "http://localhost:8001/${ALIAS}"
```

Give the worker a second to process, then check the enriched row:
```bash
docker compose exec db psql -U postgres -d urlshort -c \
"SELECT ip_anonymized, country, city, browser, os, device_type, referrer
 FROM clicks c
 JOIN links l ON l.id = c.link_id
 WHERE l.short_code = '${ALIAS}'
 ORDER BY clicked_at DESC LIMIT 1;"
```
Expected:
```text
ip_anonymized | country        | city   | browser | os      | device_type | referrer
81.2.69.0     | United Kingdom | London | Chrome  | Windows | desktop     | https://google.com
```

> **Note:** the stored IP is anonymized (`81.2.69.0`) even though GeoIP looked
> up the raw `81.2.69.142` — see the Privacy section of
> [GEOIP_SETUP.md](GEOIP_SETUP.md) for why.

If `country`, `city`, `browser`, `os`, or `referrer` are empty for **all**
recent rows, check:
- Is the GeoIP database mounted? (see above)
- Was the request made with `curl -I` (HEAD)? HEAD requests may not trigger
  full click recording — use `GET`.
- Is `analytics.process_click_event` actually registered and being consumed?
  (see Celery registered tasks check in the Phase 2 section)

---

### Test counter flush (Celery Beat)

Confirm the flush task is registered:
```bash
docker compose exec worker celery -A app.tasks.celery_app:celery_app inspect registered
```
Expected to include:
```text
analytics.flush_click_counters
```

Confirm beat is scheduling it:
```bash
docker compose logs -f beat | grep flush_click_counters
```
Expected roughly every 30 seconds:
```text
Scheduler: Sending due task flush-click-counters (analytics.flush_click_counters)
```

Manually verify the counter drains from Redis to Postgres:
```bash
# Note the Redis counter value
docker compose exec redis redis-cli -n 0 get "link:${ALIAS}:clicks"

# Wait ~30s for the beat schedule to fire, then check Postgres
docker compose exec db psql -U postgres -d urlshort -c \
"SELECT short_code, click_count FROM links WHERE short_code = '${ALIAS}';"
```
Expected: `links.click_count` matches (or exceeds, if more clicks happened) the
Redis counter value, and the Redis key is cleared or reset after the flush.

---

### Test the stats API

```bash
curl -s "http://localhost:8001/api/v1/analytics/links/${ALIAS}/overview" \
  -H "X-API-Key: $API_KEY" | python3 -m json.tool

curl -s "http://localhost:8001/api/v1/analytics/links/${ALIAS}/timeseries?days=7" \
  -H "X-API-Key: $API_KEY" | python3 -m json.tool

curl -s "http://localhost:8001/api/v1/analytics/links/${ALIAS}/breakdown?dimension=country" \
  -H "X-API-Key: $API_KEY" | python3 -m json.tool

curl -s "http://localhost:8001/api/v1/analytics/overview" \
  -H "X-API-Key: $API_KEY" | python3 -m json.tool
```
Expected: `{data, meta, errors}` envelopes with `meta.from`/`meta.to` reflecting
the requested date range, and `breakdown` accepting
`dimension=country|city|browser|os|device_type|referrer`.

---

### Run the full test suite

```bash
docker compose exec api uv run pytest -v
```
Expected: all tests passing (54 at last count, growing as Phase 3 test
coverage is added).

---

### Phase 3 expected failure behavior

| Component failure | Expected behavior |
|---|---|
| GeoIP database file missing | Click still recorded; `country`/`city` are NULL; worker logs a warning once |
| `geoip2` package missing | Same as above — fails open, no crash |
| Redis counter flush fails (DB down) | Counter value restored to Redis; task retries with backoff; no clicks lost |
| Celery Beat unavailable | Redis counters keep accumulating but stop flushing to Postgres; `links.click_count` becomes stale until beat recovers |
| Stats API queries fail | Returns standard `{errors}` envelope; redirect and click recording are unaffected (stats reads are decoupled from the write path) |

---

## Phase 4 Validation

Phase 4 adds OpenAPI docs, the response envelope audit, click-threshold
webhooks, and the analytics dashboard. Use the commands below to validate
the full Phase 4 feature set against your local Docker stack.

---

### Verify OpenAPI docs

```bash
curl -s http://localhost:8001/openapi.json | python3 -m json.tool | head -30
```

Expected: a valid JSON document with `openapi`, `info`, and `paths` keys.

Open the interactive docs in a browser:

```text
Swagger UI → http://localhost:8001/docs
ReDoc      → http://localhost:8001/redoc
```

Expected: all `/api/v1/*` routes visible with tags, summaries, and request/response examples. The API-key security scheme should appear on protected endpoints.

### Verify the response envelope

Confirm every endpoint returns `{ data, meta, errors }` on success and on error.

**Success — create a link:**

```bash
curl -s -X POST http://localhost:8001/api/v1/links \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"long_url": "https://example.com/envelope-test", "custom_alias": "envelopetest"}' \
  | python3 -m json.tool
```

Expected keys: `data`, `meta`, `errors`.

**Error — unknown short code:**

```bash
curl -s http://localhost:8001/api/v1/links/doesnotexist \
  -H "X-API-Key: $API_KEY" \
  | python3 -m json.tool
```

Expected:

```json
{
  "data": null,
  "meta": {},
  "errors": [
    { "code": "not_found", "message": "Link not found", "field": null }
  ]
}
```

**Error — missing API key:**

```bash
curl -s http://localhost:8001/api/v1/links | python3 -m json.tool
```

Expected `401` with `"code": "unauthorized"` in `errors`.

**Error — validation failure:**

```bash
curl -s -X POST http://localhost:8001/api/v1/links \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"long_url": "not-a-url"}' \
  | python3 -m json.tool
```

Expected `422` with `"code": "validation_error"` in `errors`.

### Verify cursor pagination

```bash
# First page
curl -s "http://localhost:8001/api/v1/links?limit=2" \
  -H "X-API-Key: $API_KEY" | python3 -m json.tool
```

Expected: `meta.next_cursor` present if more results exist, `meta.limit` set to 2.

```bash
# Next page using cursor from previous response
CURSOR=<next_cursor value>
curl -s "http://localhost:8001/api/v1/links?cursor=${CURSOR}&limit=2" \
  -H "X-API-Key: $API_KEY" | python3 -m json.tool
```

Expected: different set of links, `meta.next_cursor` null if last page.

### Validate the analytics dashboard

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8001/dashboard
```
Expected: 200.

Open in a browser:

```bash
open http://localhost:8001/dashboard
```

Expected views:

```text
✓ Visits line chart (7 / 30 / 90 day toggle)
✓ Geographic breakdown — country table
✓ Top referrers table
✓ Top browsers table
✓ Multi-link comparison chart
```
If the charts are empty, fire some test clicks first (see Phase 3
enrichment section above) and wait ~30 seconds for the counter flush.

### Validate the multi-link comparison endpoint
```bash
ALIAS1="comptest1$(date +%s)"
ALIAS2="comptest2$(date +%s)"

# Create two links
curl -s -X POST http://localhost:8001/api/v1/links \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"long_url\": \"https://example.com/a\", \"custom_alias\": \"${ALIAS1}\"}" \
  | python3 -m json.tool

curl -s -X POST http://localhost:8001/api/v1/links \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"long_url\": \"https://example.com/b\", \"custom_alias\": \"${ALIAS2}\"}" \
  | python3 -m json.tool

# Fire some clicks on both
for i in 1 2 3; do curl -s -o /dev/null "http://localhost:8001/${ALIAS1}"; done
for i in 1 2;   do curl -s -o /dev/null "http://localhost:8001/${ALIAS2}"; done

# Wait for enrichment
sleep 5

# Fetch comparison data
curl -s "http://localhost:8001/api/v1/analytics/compare?codes=${ALIAS1},${ALIAS2}&days=7" \
  -H "X-API-Key: $API_KEY" | python3 -m json.tool
```

Expected: `data.labels` with date strings and `data.series` with two entries,
one per short code, with `values` arrays of equal length (missing days
zero-filled).

**Error — unknown code in compare:**

```bash
curl -s "http://localhost:8001/api/v1/analytics/compare?codes=${ALIAS1},doesnotexist&days=7" \
  -H "X-API-Key: $API_KEY" | python3 -m json.tool
```
Expected `404` with `"code": "not_found"` in `errors`.

### Validate webhooks end-to-end

**Step 1 — Start a local receiver**

Open a second terminal and run:

```bash
python - <<'PY'
from http.server import BaseHTTPRequestHandler, HTTPServer

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(n)
        print("\n--- Webhook received ---")
        print("PATH   :", self.path)
        print("SIG    :", self.headers.get("X-Webhook-Signature"))
        print("EVENT  :", self.headers.get("X-Webhook-Event"))
        print("BODY   :", body.decode())
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")
    def log_message(self, *_): pass

HTTPServer(("0.0.0.0", 9999), Handler).serve_forever()
PY
```

**Step 2 — Create a link with webhook config**

```bash
WHTEST="whtest$(date +%s)"

curl -s -X POST http://localhost:8001/api/v1/links \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"long_url\": \"https://example.com/webhook-test\",
    \"custom_alias\": \"${WHTEST}\",
    \"webhook_url\": \"http://host.docker.internal:9999/webhook\",
    \"webhook_threshold\": 3
  }" | python3 -m json.tool
```
> On Linux, replace `host.docker.internal` with your host machine’s LAN IP
> `(e.g. 192.168.x.x)`. On macOS/Windows, `host.docker.internal` resolves
> correctly from inside Docker containers.

**Step 3 — Drive clicks past the threshold**

```bash
for i in 1 2 3 4; do
  curl -s -o /dev/null -w "%{http_code}\n" "http://localhost:8001/${WHTEST}"
done
```
Expected: four `302` responses.

**Step 4 — Wait for the flush and check the receiver**

```bash
sleep 35
```

Expected in the receiver terminal:

```text
--- Webhook received ---
PATH   : /webhook
SIG    : sha256=<hmac_hex_digest>
EVENT  : link.click_threshold_reached
BODY   : {"event": "link.click_threshold_reached", "short_code": "...",
          "click_count": 3, "threshold": 3, "occurred_at": "..."}
```

**Step 5 — Confirm idempotency**

Drive more clicks past the threshold:

```bash
for i in 1 2 3; do
  curl -s -o /dev/null "http://localhost:8001/${WHTEST}"
done
sleep 35
```

Expected: receiver does not print a second payload. The webhook fires
exactly once per link.

**Step 6 — Confirm webhook_fired in the database**

```bash
docker compose exec db psql -U postgres -d urlshort -c \
"SELECT short_code, click_count, webhook_threshold, webhook_fired
 FROM links WHERE short_code = '${WHTEST}';"
```

Expected:

```text
short_code | click_count | webhook_threshold | webhook_fired
-----------+-------------+-------------------+--------------
whtest...  |           7 |                 3 | t
```

### Run the Phase 4 test suite

```bash
uv run pytest tests/test_d4_envelope_contracts.py -v
uv run pytest tests/test_d4_webhook_contracts.py -v
uv run pytest tests/test_d4_dashboard_ui.py -v
```

Or run everything together:

```bash
uv run pytest -v
```
Expected: all tests passing (136 at last count).
