"""F3 — Link management UI (create + my links pages).

Covers:
  • Auth guarding: unauthenticated → redirect to /?auth=required
  • Authenticated users can load /create and /links
  • Templates contain the expected controls & call the right endpoints
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def client() -> TestClient:
    """Fresh TestClient with its own event loop for every test."""
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def auth_client(client: TestClient) -> TestClient:
    """
    Register a brand-new user and return the same client.
    /session/register → 200 JSON {"redirect": "/dashboard/"} + sets session cookie.
    """
    email = f"f3_{uuid.uuid4().hex[:8]}@example.com"
    password = "secret-password-123"

    resp = client.post(
        "/session/register",
        json={"email": email, "password": password},
        follow_redirects=False,
    )

    assert resp.status_code == 200, f"Register failed ({resp.status_code}): {resp.text}"
    body = resp.json()
    assert body.get("redirect") == "/dashboard/", f"Unexpected body: {body}"

    # Cookie is automatically stored in the TestClient's cookie jar.
    # All subsequent requests on this client are authenticated.
    return client


# ── Auth guarding ─────────────────────────────────────────────────────────────


def test_create_redirects_when_no_cookie(client: TestClient) -> None:
    resp = client.get("/create", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/?auth=required"


def test_links_redirects_when_no_cookie(client: TestClient) -> None:
    resp = client.get("/links", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/?auth=required"


# ── Authenticated page loads ──────────────────────────────────────────────────


def test_create_page_loads_with_cookie(auth_client: TestClient) -> None:
    resp = auth_client.get("/create")
    assert resp.status_code == 200, resp.text
    assert "text/html" in resp.headers["content-type"]


def test_links_page_loads_with_cookie(auth_client: TestClient) -> None:
    resp = auth_client.get("/links")
    assert resp.status_code == 200, resp.text
    assert "text/html" in resp.headers["content-type"]


# ── Create page: controls + endpoint wiring ───────────────────────────────────


def test_create_has_form_controls(auth_client: TestClient) -> None:
    html = auth_client.get("/create").text

    assert 'id="createForm"' in html, "Missing createForm"
    assert 'id="longUrl"' in html, "Missing longUrl"
    assert 'id="customAlias"' in html, "Missing customAlias"
    assert 'id="expiresAt"' in html, "Missing expiresAt"
    assert 'id="password"' in html, "Missing password"
    assert 'id="webhookUrl"' in html, "Missing webhookUrl"
    assert 'id="webhookThreshold"' in html, "Missing webhookThreshold"


def test_create_calls_links_endpoint(auth_client: TestClient) -> None:
    html = auth_client.get("/create").text

    assert '"/api/v1/links"' in html, "Missing POST target"
    assert 'method: "POST"' in html, "Missing POST method"
    assert '"X-API-Key"' in html, "Missing X-API-Key header"


# ── Links page: table + endpoint wiring ──────────────────────────────────────


def test_links_has_table_and_controls(auth_client: TestClient) -> None:
    html = auth_client.get("/links").text

    assert 'id="linksTable"' in html, "Missing linksTable"
    assert 'id="loadMoreBtn"' in html, "Missing loadMoreBtn"
    assert 'id="emptyState"' in html, "Missing emptyState"
    assert 'href="/create"' in html, "Missing link to /create"


def test_links_calls_list_and_delete_endpoints(auth_client: TestClient) -> None:
    html = auth_client.get("/links").text

    assert "/api/v1/links?limit=20" in html, "Missing list endpoint"
    assert "cursor=" in html, "Missing cursor param"
    assert "/api/v1/links/" in html, "Missing delete endpoint path"
    assert 'method: "DELETE"' in html, "Missing DELETE method"


# ── End-to-end: create a link then see it in the list ────────────────────────


def test_created_link_appears_in_api_list(auth_client: TestClient) -> None:
    # POST /api/v1/links — cookie authenticates (same client, same cookie jar)
    create = auth_client.post(
        "/api/v1/links",
        json={"long_url": "https://example.com/f3-test"},
    )
    assert create.status_code == 201, create.text
    code = create.json()["data"]["short_code"]

    # GET /api/v1/links — should contain the new code
    listing = auth_client.get("/api/v1/links?limit=20")
    assert listing.status_code == 200, listing.text

    codes = [item["short_code"] for item in listing.json()["data"]]
    assert code in codes, f"Expected {code!r} in {codes}"
