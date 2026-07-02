from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _assert_envelope(body: dict[str, Any]) -> None:
    assert "data" in body
    assert "meta" in body
    assert "errors" in body
    assert isinstance(body["errors"], list)


# ── OpenAPI / Swagger / ReDoc ───────────────────────────────────────────────


def test_openapi_json_is_available() -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200

    body = response.json()
    assert "openapi" in body
    assert isinstance(body.get("paths"), dict)


def test_swagger_docs_are_available() -> None:
    response = client.get("/docs")

    assert response.status_code == 200
    assert "swagger" in response.text.lower()


def test_redoc_is_available() -> None:
    response = client.get("/redoc")

    assert response.status_code == 200
    assert "redoc" in response.text.lower()


# ── URL versioning ──────────────────────────────────────────────────────────


def test_openapi_contains_versioned_api_paths() -> None:
    body = client.get("/openapi.json").json()
    paths = body["paths"]

    assert any(
        path.startswith("/api/v1/") for path in paths
    ), "Expected at least one /api/v1/ path in OpenAPI"


def test_openapi_documents_dashboard_analytics_paths() -> None:
    body = client.get("/openapi.json").json()
    paths = set(body["paths"].keys())

    expected = {
        "/api/v1/analytics/{short_code}/timeseries",
        "/api/v1/analytics/{short_code}/countries",
        "/api/v1/analytics/{short_code}/browsers",
        "/api/v1/analytics/{short_code}/referrers",
        "/api/v1/analytics/compare",
    }

    missing = expected.difference(paths)
    assert not missing, f"Missing dashboard analytics paths: {sorted(missing)}"


# ── API-key security scheme ─────────────────────────────────────────────────


def test_openapi_contains_api_key_header_security_scheme() -> None:
    body = client.get("/openapi.json").json()
    schemes = body.get("components", {}).get("securitySchemes", {})

    assert schemes, "Expected securitySchemes in OpenAPI components"

    api_key_header = [
        scheme
        for scheme in schemes.values()
        if scheme.get("type") == "apiKey"
        and scheme.get("in") == "header"
        and scheme.get("name", "").lower() == "x-api-key"
    ]

    assert api_key_header, "Expected X-API-Key apiKey header security scheme"


# ── Envelope on API errors ──────────────────────────────────────────────────


def test_unauthenticated_analytics_uses_envelope() -> None:
    response = client.get("/api/v1/analytics/doesnotexist/timeseries")

    assert response.status_code in {401, 403}

    body = response.json()
    _assert_envelope(body)
    assert body["data"] is None
    assert body["errors"]


def test_unknown_api_route_uses_envelope() -> None:
    response = client.get("/api/v1/this-route-does-not-exist")

    assert response.status_code == 404

    body = response.json()
    _assert_envelope(body)
    assert body["data"] is None
    assert body["errors"]
