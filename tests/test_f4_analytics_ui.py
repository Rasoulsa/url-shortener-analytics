from __future__ import annotations

# ── Analytics page ──────────────────────────────────────────────


def test_analytics_page_requires_login(client):
    res = client.get("/dashboard/analytics/abc123", follow_redirects=False)
    assert res.status_code in (302, 303)


def test_analytics_page_loads_with_cookie(auth_client):
    res = auth_client.get("/dashboard/analytics/abc123")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]


def test_analytics_page_has_range_controls(auth_client):
    html = auth_client.get("/dashboard/analytics/abc123").text

    assert 'data-days="7"' in html or 'value="7"' in html
    assert 'data-days="30"' in html or 'value="30"' in html
    assert 'data-days="90"' in html or 'value="90"' in html


def test_analytics_page_has_chart_and_tables(auth_client):
    html = auth_client.get("/dashboard/analytics/abc123").text
    lower = html.lower()

    assert "<canvas" in html
    assert "country" in lower or "countries" in lower
    assert "referrer" in lower or "referrers" in lower
    assert "browser" in lower or "browsers" in lower


def test_analytics_page_uses_api_key_fetch_logic(auth_client):
    html = auth_client.get("/dashboard/analytics/abc123").text

    assert "X-API-Key" in html
    assert "timeseries" in html
    assert "country" in html.lower() or "countries" in html.lower()
    assert "browser" in html.lower() or "browsers" in html.lower()
    assert "referrer" in html.lower() or "referrers" in html.lower()


# ── Compare page ────────────────────────────────────────────────


def test_compare_page_requires_login(client):
    res = client.get("/dashboard/compare", follow_redirects=False)
    assert res.status_code in (302, 303)


def test_compare_page_loads_with_cookie(auth_client):
    res = auth_client.get("/dashboard/compare")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]


def test_compare_page_has_api_key_form_and_chart(auth_client):
    html = auth_client.get("/dashboard/compare").text

    assert 'id="apiKeyInput"' in html
    assert 'id="codes"' in html
    assert 'id="period"' in html
    assert 'id="compareBtn"' in html
    assert 'id="compareChart"' in html
    assert 'id="summaryTable"' in html


def test_compare_page_uses_inline_api_key_fetch_logic(auth_client):
    html = auth_client.get("/dashboard/compare").text

    assert "function getApiKey()" in html
    assert "function loadCompare()" in html
    assert "X-API-Key" in html
    assert "/api/v1/analytics/compare" in html
