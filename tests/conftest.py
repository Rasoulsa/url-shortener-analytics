# tests/conftest.py
from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

# ---------------------------------------------------------------------------
# Pytest is running from your Mac host.
# Docker service names like "db" and "redis" do NOT work from host pytest.
# Force host-mapped ports.
# ---------------------------------------------------------------------------

TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/urlshort"

os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["POSTGRES_HOST"] = "127.0.0.1"
os.environ["POSTGRES_PORT"] = "5433"
os.environ["POSTGRES_USER"] = "postgres"
os.environ["POSTGRES_PASSWORD"] = "postgres"
os.environ["POSTGRES_DB"] = "urlshort"

os.environ["REDIS_URL"] = "redis://127.0.0.1:6380/0"
os.environ["CELERY_BROKER_URL"] = "redis://127.0.0.1:6380/1"
os.environ["CELERY_RESULT_BACKEND"] = "redis://127.0.0.1:6380/2"
os.environ["CELERY_TASK_ALWAYS_EAGER"] = "true"

# Disable rate limiting during tests.
os.environ["RATE_LIMIT_ENABLED"] = "false"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool  # noqa: E402

import app.core.database as _db_module  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.main import app  # noqa: E402

# Extra safety.
settings.rate_limit_enabled = False


@pytest.fixture(autouse=True, scope="session")
def _disable_rate_limit_for_tests() -> Iterator[None]:
    old_value = settings.rate_limit_enabled
    settings.rate_limit_enabled = False

    yield

    settings.rate_limit_enabled = old_value


@pytest.fixture(autouse=True, scope="session")
def _force_test_database_engine() -> Iterator[None]:
    """
    Force pytest to use host Postgres at 127.0.0.1:5433.

    Do NOT reuse _db_module.engine.url because it may already contain db:5432
    from .env/docker settings.
    """
    engine = create_async_engine(
        TEST_DATABASE_URL,
        poolclass=NullPool,
        echo=False,
    )

    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    _db_module.engine = engine

    if hasattr(_db_module, "SessionLocal"):
        _db_module.SessionLocal = session_factory

    if hasattr(_db_module, "AsyncSessionLocal"):
        _db_module.AsyncSessionLocal = session_factory

    if hasattr(_db_module, "async_session_maker"):
        _db_module.async_session_maker = session_factory

    yield


@pytest.fixture()
def client() -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def auth_client(client: TestClient) -> Iterator[TestClient]:
    email = f"u_{uuid.uuid4().hex[:8]}@example.com"

    res = client.post(
        "/session/register",
        json={
            "email": email,
            "password": "supersecret123",
        },
    )

    assert res.status_code == 200, f"Register failed ({res.status_code}): {res.text}"
    assert res.json().get("redirect") == "/dashboard/"

    yield client

    client.cookies.clear()
