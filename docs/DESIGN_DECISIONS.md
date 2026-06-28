# Design Decisions

## 1. Short-Code Generation

### Decision

Use:

```text
Random Base62 + Redis SETNX reservation + PostgreSQL UNIQUE constraint
```

---

### Options Considered

| Approach | Speed | Privacy | Complexity | Decision |
|---|---|---|---|---|
| Counter + Base62 | Very fast | Poor, sequential/guessable | Low | Rejected |
| Pre-generated pool | Very fast | Good | High | Rejected |
| Random Base62 + SETNX | Very fast | Good | Medium | Chosen |

---

### Why Not Counter + Base62?

A counter-based approach is simple:

```text
1 -> 1
2 -> 2
62 -> 10
```

But it creates predictable URLs.

Problems:

- users can guess nearby links
- total link count is exposed
- privacy is weaker
- abuse scraping becomes easier

Counter-based Base62 is still useful as a demonstration and is implemented as helper functions:

```python
encode_base62(number)
decode_base62(code)
```

But it is not the primary production strategy.

---

### Why Random Base62?

A random Base62 code is harder to enumerate.

Current alphabet:

```text
0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ
```

For 7 characters:

```text
62^7 = 3,521,614,606,208
```

That is approximately 3.5 trillion possible codes.

Benefits:

- non-sequential
- privacy-friendly
- horizontally scalable
- no global counter bottleneck

---

### Why Redis SETNX?

Redis `SET NX` atomically sets a key only if it does not already exist.

Reservation key format:

```text
code_reserved:{code}
```

Example:

```text
code_reserved:abc1234
```

This prevents two concurrent workers from thinking they both own the same code.

Reservation TTL:

```text
60 seconds
```

This means if the app reserves a code but fails before writing to PostgreSQL, the reservation automatically expires.

---

### Collision Handling

Flow:

```text
generate random code
  |
  v
try Redis SETNX reservation
  |
  |-- success -> use code
  |
  |-- collision -> retry
```

If all attempts fail:

```text
increase length by 1 and retry
```

This allows the keyspace to grow automatically under extreme pressure.

---

### Final Safety Net

PostgreSQL should still enforce a unique constraint on the short code.

Reason:

Redis reservation protects the normal concurrent path, but the database remains the source of truth.

The final consistency chain is:

```text
Random generation
  +
Redis SETNX reservation
  +
PostgreSQL UNIQUE constraint
```

---

## 2. Environment File Strategy

### Decision

Commit only:

```text
.env.example
```

Do not commit:

```text
.env
.env.dev
```

Reason:

- `.env.example` documents required variables
- `.env` and `.env.dev` may contain secrets
- local values can differ from deployment values

For local Docker development:

```bash
cp .env.example .env.dev
docker compose up --build
```

---

## 3. Docker Service Names

Inside Docker Compose, services communicate using service names:

```text
db
redis
```

Therefore:

```ini
POSTGRES_HOST=db
REDIS_URL=redis://redis:6379/0
```

This is correct inside Docker.

If running locally outside Docker, use:

```ini
POSTGRES_HOST=localhost
REDIS_URL=redis://localhost:6379/0
```

---

## 4. Redis DB Separation

Redis logical databases are separated by responsibility:

```text
0 -> app cache / short-code reservation
1 -> Celery broker
2 -> Celery result backend
```

This makes debugging and clearing data easier during development.
