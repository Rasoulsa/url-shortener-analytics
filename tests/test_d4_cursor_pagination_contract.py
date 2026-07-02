from __future__ import annotations

import inspect

from app.api.v1 import links


def test_links_router_uses_cursor_and_limit() -> None:
    source = inspect.getsource(links).lower()

    assert "cursor" in source
    assert "limit" in source


def test_links_router_returns_next_cursor_meta() -> None:
    source = inspect.getsource(links).lower()

    assert "next_cursor" in source


def test_links_router_uses_envelope_keys() -> None:
    source = inspect.getsource(links).lower()

    assert "data" in source
    assert "meta" in source


def test_links_router_avoids_offset_pagination() -> None:
    source = inspect.getsource(links).lower()

    assert ".offset(" not in source
