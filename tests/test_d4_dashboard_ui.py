from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

# ── Routes ──────────────────────────────────────────────────────────────────


def test_dashboard_redirects_to_slash(client: TestClient) -> None:
    response = client.get("/dashboard", follow_redirects=False)

    assert response.status_code in {301, 302, 307, 308}
    assert response.headers["location"] == "/dashboard/"


def test_dashboard_redirects_when_unauthenticated(client: TestClient) -> None:
    client.cookies.clear()
    response = client.get("/dashboard/", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/?auth=required"


def test_compare_redirects_when_unauthenticated(client: TestClient) -> None:
    client.cookies.clear()
    response = client.get("/dashboard/compare", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/?auth=required"


def test_dashboard_index_loads(auth_client: TestClient) -> None:
    response = auth_client.get("/dashboard/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Analytics Dashboard" in response.text


def test_dashboard_compare_loads(auth_client: TestClient) -> None:
    response = auth_client.get("/dashboard/compare")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Multi-Link Comparison" in response.text


def test_static_css_served(client: TestClient) -> None:
    response = client.get("/static/dashboard.css")

    assert response.status_code == 200


# ── Index content ───────────────────────────────────────────────────────────


def test_index_has_controls_and_targets(auth_client: TestClient) -> None:
    html = auth_client.get("/dashboard/").text

    for token in (
        "apiKeyValue",
        "shortCode",
        "timeseriesChart",
        "browserChart",
        "countryTable",
        "referrerList",
    ):
        assert token in html


def test_index_calls_expected_endpoints(auth_client: TestClient) -> None:
    html = auth_client.get("/dashboard/").text

    assert "/api/v1/analytics/" in html
    assert "timeseries" in html
    assert "countries" in html
    assert "browsers" in html
    assert "referrers" in html
    assert "X-API-Key" in html


def test_index_shows_api_key(auth_client: TestClient) -> None:
    me = auth_client.get("/api/v1/auth/me").json()["data"]
    html = auth_client.get("/dashboard/").text

    assert me["api_key"] in html
    assert me["email"] in html


# ── Compare content ─────────────────────────────────────────────────────────


def test_compare_has_controls_and_targets(auth_client: TestClient) -> None:
    html = auth_client.get("/dashboard/compare").text

    for token in ("codes", "compareChart", "summaryTable"):
        assert token in html


def test_compare_calls_compare_endpoint(auth_client: TestClient) -> None:
    html = auth_client.get("/dashboard/compare").text

    assert "/api/v1/analytics/compare" in html
    assert "X-API-Key" in html


# ── Template/static files exist ─────────────────────────────────────────────


def test_dashboard_template_files_exist() -> None:
    templates = Path("app/templates")

    assert (templates / "base.html").exists()
    assert (templates / "dashboard" / "index.html").exists()
    assert (templates / "dashboard" / "compare.html").exists()


def test_base_template_includes_chartjs_and_nav() -> None:
    content = Path("app/templates/base.html").read_text()

    assert "chart" in content.lower()
    assert "navbar-actions" in content
    assert "/static/js/auth.js" in content
