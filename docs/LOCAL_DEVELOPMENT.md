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

View logs:

```bash
docker compose logs -f api
```

View worker logs:

```bash
docker compose logs -f worker
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

## Phase 2 Redis/Celery Validation

Phase 2 adds Redis caching, Redis counters, Redis-backed rate limiting, and Celery
workers. Use the commands below to validate the local Docker setup.

---

### Check containers
```bashe
docker compose ps
```
Expected:
```text
api      healthy
db       healthy
redis    healthy
worker   healthy
```

If one service is unhealthy, inspect logs:
```bash
docker compose logs -f api
docker compose logs -f worker
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

The Celery worker does not run an HTTP server.

This is valid for the API:
```bash
curl http://localhost:8001/health
```
This is not valid for the worker:
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
docker compose exec db psql -U postgres -d url_shortener
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
