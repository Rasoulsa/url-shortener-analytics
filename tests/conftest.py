# tests/conftest.py
from __future__ import annotations

import os
import uuid


def pytest_configure(config):
    os.environ["POSTGRES_HOST"] = "localhost"
    os.environ["POSTGRES_PORT"] = "5433"
    os.environ["POSTGRES_USER"] = "postgres"
    os.environ["POSTGRES_PASSWORD"] = "postgres"
    os.environ["POSTGRES_DB"] = "urlshort"
    os.environ["REDIS_URL"] = "redis://localhost:6380/0"
    os.environ["CELERY_BROKER_URL"] = "redis://localhost:6380/1"
    os.environ["CELERY_RESULT_BACKEND"] = "redis://localhost:6380/2"
    os.environ["CELERY_TASK_ALWAYS_EAGER"] = "true"


import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def auth_client(client: TestClient):
    client.cookies.clear()
    email = f"u_{uuid.uuid4().hex[:8]}@example.com"
    client.post(
        "/session/register",
        json={"email": email, "password": "supersecret123"},
    )
    yield client
    client.cookies.clear()
