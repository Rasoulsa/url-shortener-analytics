# Architecture

## Overview

The URL Shortener & Analytics project is designed as a modular FastAPI application backed by PostgreSQL and Redis.

The architecture separates:

- API routing
- business logic
- persistence models
- configuration
- background jobs
- documentation and tests

---

## High-Level Components

```text
Client
  |
  v
FastAPI API
  |
  |-- PostgreSQL
  |     └── users, links, clicks
  |
  |-- Redis
  |     ├── short-code reservation
  |     ├── cache
  |     └── Celery broker/result backend
  |
  └-- Celery Worker
        └── background analytics / future async tasks
```

---

## Application Layers

### app/api

Contains FastAPI route handlers and dependency wiring.

Responsibilities:

- receive HTTP requests
- validate request/response schemas
- call service-layer functions
- return API responses

### app/services

Contains business logic.

Current important service:

```text
app/services/shortener.py
```

Responsibilities:

- generate random Base62 short codes
- reserve codes atomically in Redis
- retry on collisions
- provide Base62 encode/decode helpers

### app/models

Contains SQLAlchemy ORM models.

Main entities:

| Model | Purpose |
|---|---|
| User | Account / owner entity |
| Link | Shortened URL metadata |
| Click | Redirect analytics event |

### app/core

Contains shared infrastructure and configuration.

Examples:

| File | Purpose |
|---|---|
| config.py | Pydantic settings |
| redis_client.py | Async Redis client |
| database-related files | DB session / engine setup |

### app/tasks

Celery-related background task setup.

Expected future responsibilities:

- async analytics enrichment
- click aggregation
- webhook delivery
- periodic cleanup

---

## Data Storage

### PostgreSQL

PostgreSQL is the source of truth.

Used for:

- users
- links
- click events
- unique short-code constraint

### Redis

Redis is used for:

- atomic short-code reservation
- caching hot links
- Celery broker
- Celery result backend

Redis DB usage:

```text
redis://redis:6379/0  application cache / code reservation
redis://redis:6379/1  Celery broker
redis://redis:6379/2  Celery result backend
```

---

## Docker Services

| Service | Description |
|---|---|
| api | FastAPI app |
| db | PostgreSQL |
| redis | Redis |
| worker | Celery worker |
| migrate | Alembic migration runner |

---

## Request Flow: Short Link Creation

```text
POST /links
  |
  v
Validate request
  |
  v
Generate random Base62 code
  |
  v
Reserve code in Redis using SETNX
  |
  v
Insert link into PostgreSQL
  |
  v
Return short URL
```

---

## Request Flow: Redirect

```text
GET /{short_code}
  |
  v
Look up short code
  |
  |-- Redis cache hit -> redirect
  |
  |-- Redis cache miss
        |
        v
      PostgreSQL lookup
        |
        v
      cache result
        |
        v
      redirect
```

---

## Scalability Considerations

- Random short-code generation avoids global counters.
- Redis SETNX avoids race conditions during reservation.
- PostgreSQL unique constraints provide final consistency.
- Redis caching reduces DB load for popular links.
- Celery allows analytics processing to move out of request path.
