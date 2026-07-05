from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.main import app


def _unique_email() -> str:
    return f"user_{uuid.uuid4().hex[:8]}@example.com"


# ── Session register sets cookie + returns redirect ──────────────────────────


def test_session_register_sets_cookie_and_redirect(client: TestClient) -> None:
    res = client.post(
        "/session/register",
        json={"email": _unique_email(), "password": "supersecret123"},
    )
    assert res.status_code == 200
    assert res.json()["redirect"] == "/dashboard/"
    assert "session_token" in res.cookies


def test_session_login_with_password_sets_cookie(client: TestClient) -> None:
    email = _unique_email()
    client.post("/session/register", json={"email": email, "password": "supersecret123"})

    res = client.post(
        "/session/login",
        json={"email": email, "password": "supersecret123"},
    )
    assert res.status_code == 200
    assert res.json()["redirect"] == "/dashboard/"
    assert "session_token" in res.cookies


def test_session_login_bad_password_fails(client: TestClient) -> None:
    email = _unique_email()
    client.post("/session/register", json={"email": email, "password": "supersecret123"})

    res = client.post(
        "/session/login",
        json={"email": email, "password": "wrongpassword"},
    )
    assert res.status_code == 401


def test_session_logout_clears_cookie(client: TestClient) -> None:
    res = client.post("/session/logout")
    assert res.status_code == 200
    assert res.json()["redirect"] == "/"


# ── Dashboard guard: cookie required ─────────────────────────────────────────
# These tests need to be unauthenticated. We use a fresh TestClient (created
# in the test) instead of the session-scoped `client` fixture, so we sidestep
# cookie pollution from earlier tests that registered users.


def test_dashboard_redirects_when_no_cookie() -> None:
    """Fresh client, no cookies at all."""
    with TestClient(app) as fresh_client:
        res = fresh_client.get("/dashboard/", follow_redirects=False)
        assert res.status_code == 303
        assert res.headers["location"] == "/?auth=required"


def test_dashboard_loads_with_cookie(client: TestClient) -> None:
    email = _unique_email()
    client.post("/session/register", json={"email": email, "password": "supersecret123"})

    res = client.get("/dashboard/")
    assert res.status_code == 200
    assert email in res.text
    assert "apiKeyDisplay" in res.text
    assert "apiKeyInput" in res.text


def test_compare_redirects_when_no_cookie() -> None:
    """Fresh client, no cookies at all."""
    with TestClient(app) as fresh_client:
        res = fresh_client.get("/dashboard/compare", follow_redirects=False)
        assert res.status_code == 303
        assert res.headers["location"] == "/?auth=required"
