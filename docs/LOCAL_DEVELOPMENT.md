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
