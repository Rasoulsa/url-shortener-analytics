# URL Shortener & Analytics

A high-performance URL shortener built with **FastAPI**, **PostgreSQL**, **Redis**, **Celery**, and **Docker**.

The project focuses on reliable short-code generation, scalable redirects, Redis-backed caching, and analytics-ready architecture.

---

## Features

- Create short links from long URLs
- Generate unpredictable Base62 short codes
- Reserve codes atomically using Redis `SETNX`
- Prevent collisions with retry logic and database uniqueness constraints
- PostgreSQL persistence with SQLAlchemy async support
- Redis support for caching and reservation flows
- Celery-ready background worker setup
- Docker Compose development environment
- Alembic migration support
- Test coverage for short-code generation logic

---

## Tech Stack

| Area | Technology |
|---|---|
| API | FastAPI |
| ASGI Server | Uvicorn |
| Database | PostgreSQL |
| ORM | SQLAlchemy Async |
| Migrations | Alembic |
| Cache / Queue | Redis |
| Background Jobs | Celery |
| Package Manager | uv |
| Testing | pytest, pytest-asyncio |
| Linting / Formatting | Ruff |
| Type Checking | mypy |
| Containerization | Docker, Docker Compose |

---

## Project Structure

```text
.
├── app/
│   ├── api/
│   ├── core/
│   ├── models/
│   ├── schemas/
│   ├── services/
│   ├── tasks/
│   └── main.py
├── alembic/
├── docs/
├── geoip/
├── tests/
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── README.md
└── CHANGELOG.md
```

## Environment Variables

The committed template is:

```text
.env.example
```

For local Docker development, create:

```bash
cp .env.example .env.dev
```

Local/private environment files are intentionally ignored:

```text
.env
.env.dev
```

Important default values:

```ini
POSTGRES_HOST=db
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2
```

These values are correct for Docker Compose because services communicate using Compose service names such as db and redis.

## Local Development with uv

Install dependencies:

```bash
uv sync --all-extras
```

Run tests:

```bash
uv run pytest
```

Run linting:

```bash
uv run ruff check .
```

Run formatter:

```bash
uv run ruff format .
```

Run type checks:

```bash
uv run mypy app/
```

Run the API locally:

```bash
uv run uvicorn app.main:app --reload
```

Note: if running outside Docker, update database and Redis host values from db/redis to localhost.

## Docker Development

Create local dev environment file:

```bash
cp .env.example .env.dev
```

Build and start services:

```bash
docker compose up --build
```

Run in background:

```bash
docker compose up --build -d
```

Run migrations:

```bash
docker compose run --rm migrate
```

Stop services:

```bash
docker compose down
```

Stop services and remove volumes:

```bash
docker compose down -v
```

## Services

The Docker Compose stack includes:

| Service | Description |
|---|---|
| api | FastAPI application |
| db | PostgreSQL database |
| redis | Redis cache / queue backend |
| worker | Celery background worker |
| migrate | One-shot Alembic migration runner |

## Testing

Short-code generation tests cover:

- Base62 alphabet contract
- Random code length and character set
- Redis SETNX reservation behavior
- Collision retry behavior
- Length growth after retry exhaustion
- Base62 encode/decode roundtrips

Run:

```bash
uv run pytest tests/test_shortener.py -v
```

Current status:

```text
42 tests passing
```

## Design Highlights

Short-code generation

The chosen algorithm is:

```text
Random Base62 + Redis SETNX reservation + DB UNIQUE constraint
```

Reasons:

- Codes are unpredictable and not sequential.
- Redis SETNX provides atomic reservation.
- No global counter means better horizontal scalability.
- A 7-character Base62 code has approximately 3.5 trillion combinations.
- Database uniqueness remains the final safety net.

See:

```text
docs/DESIGN_DECISIONS.md
```

## Documentation

Additional docs:

```text
docs/ARCHITECTURE.md
docs/DESIGN_DECISIONS.md
docs/LOCAL_DEVELOPMENT.md
```

## License

MIT License.

---
