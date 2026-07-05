from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

# ── helpers ─────────────────────────────────────────────────────────────────


def _create_protected_link(auth_client: TestClient) -> str:
    """Create a password-protected short link; return its short_code."""
    res = auth_client.post(
        "/api/v1/links",
        json={
            "long_url": f"https://example.com/{uuid.uuid4().hex}",
            "password": "secret123",
        },
    )
    assert res.status_code in (200, 201), res.text
    return res.json()["data"]["short_code"]


def _create_plain_link(auth_client: TestClient) -> str:
    """Create an unprotected short link; return its short_code."""
    res = auth_client.post(
        "/api/v1/links",
        json={"long_url": f"https://example.com/{uuid.uuid4().hex}"},
    )
    assert res.status_code in (200, 201), res.text
    return res.json()["data"]["short_code"]


# ── gate rendering ───────────────────────────────────────────────────────────


def test_protected_link_shows_password_gate(auth_client: TestClient) -> None:
    code = _create_protected_link(auth_client)

    res = auth_client.get(f"/{code}", follow_redirects=False)

    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    html = res.text
    # inherits base.html nav + footer
    assert "URL Shortener" in html
    # card content
    assert "Protected Link" in html
    assert 'type="password"' in html
    assert f'action="/{code}/unlock"' in html


def test_protected_gate_shows_no_error_by_default(auth_client: TestClient) -> None:
    code = _create_protected_link(auth_client)

    html = auth_client.get(f"/{code}", follow_redirects=False).text

    assert "Incorrect password" not in html


def test_protected_gate_inherits_base_nav(auth_client: TestClient) -> None:
    """Gate must extend base.html so visitors see the public navbar."""
    code = _create_protected_link(auth_client)

    html = auth_client.get(f"/{code}", follow_redirects=False).text

    # base.html nav anchor
    assert 'href="/"' in html
    # base.html footer
    assert "API Docs" in html or "v1.0.0" in html


# ── wrong password ───────────────────────────────────────────────────────────


def test_wrong_password_reshows_gate_with_error(auth_client: TestClient) -> None:
    code = _create_protected_link(auth_client)

    res = auth_client.post(
        f"/{code}/unlock",
        data={"password": "wrongpassword"},
        follow_redirects=False,
    )

    assert res.status_code == 403
    html = res.text
    assert "Incorrect password" in html
    assert 'type="password"' in html
    assert f'action="/{code}/unlock"' in html


def test_wrong_password_still_has_nav(auth_client: TestClient) -> None:
    code = _create_protected_link(auth_client)

    html = auth_client.post(
        f"/{code}/unlock",
        data={"password": "wrongpassword"},
        follow_redirects=False,
    ).text

    assert 'href="/"' in html
    assert "API Docs" in html or "v1.0.0" in html


# ── correct password ─────────────────────────────────────────────────────────


def test_correct_password_redirects(auth_client: TestClient) -> None:
    code = _create_protected_link(auth_client)

    res = auth_client.post(
        f"/{code}/unlock",
        data={"password": "secret123"},
        follow_redirects=False,
    )

    assert res.status_code in (301, 302)
    assert res.headers["location"].startswith("https://example.com/")


# ── plain links unaffected ───────────────────────────────────────────────────


def test_plain_link_redirects_without_gate(auth_client: TestClient) -> None:
    code = _create_plain_link(auth_client)

    res = auth_client.get(f"/{code}", follow_redirects=False)

    assert res.status_code in (301, 302)
    assert res.headers["location"].startswith("https://example.com/")
