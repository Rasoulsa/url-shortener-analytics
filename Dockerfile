# ── Stage 1: dependencies ─────────────────────────────────────────────────────
FROM python:3.13-slim AS deps

# System deps needed to build asyncpg / psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency manifests first — layer cache stays valid if code changes
COPY pyproject.toml uv.lock* ./

# Install production deps only into the system Python
RUN uv pip install --system --no-cache -e ".[dev]"


# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM python:3.13-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Non-root user for security
RUN groupadd --gid 1001 appgroup \
 && useradd  --uid 1001 --gid appgroup --no-create-home appuser

WORKDIR /app

# Copy installed packages from deps stage
COPY --from=deps /usr/local/lib/python3.13 /usr/local/lib/python3.13
COPY --from=deps /usr/local/bin /usr/local/bin

# Copy application source
COPY --chown=appuser:appgroup . .

# GeoIP data directory
RUN mkdir -p /data && chown appuser:appgroup /data

USER appuser

EXPOSE 8000

# Healthcheck — hits the /health endpoint every 30 s
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
