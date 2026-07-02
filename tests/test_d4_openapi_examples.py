from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _operations(openapi: dict[str, Any]) -> list[dict[str, Any]]:
    ops: list[dict[str, Any]] = []
    for path_item in openapi["paths"].values():
        for method in ("get", "post", "put", "patch", "delete"):
            op = path_item.get(method)
            if op:
                ops.append(op)
    return ops


def test_operations_have_tags() -> None:
    openapi = client.get("/openapi.json").json()
    ops = _operations(openapi)

    assert ops
    assert all(op.get("tags") for op in ops)


def test_operations_have_summary_or_description() -> None:
    openapi = client.get("/openapi.json").json()
    ops = _operations(openapi)

    missing = [
        op.get("operationId", "<unknown>")
        for op in ops
        if not op.get("summary") and not op.get("description")
    ]

    assert not missing, f"Operations missing summary/description: {missing}"


def test_openapi_has_analytics_tag() -> None:
    openapi = client.get("/openapi.json").json()
    ops = _operations(openapi)

    tags = {tag for op in ops for tag in op.get("tags", [])}

    assert any("analytics" in tag.lower() for tag in tags)


def test_openapi_mentions_webhook_somewhere() -> None:
    openapi = client.get("/openapi.json").json()

    assert "webhook" in str(openapi).lower()
