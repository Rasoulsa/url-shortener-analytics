"""Envelope builders for non-router contexts.

Route handlers use the Pydantic Envelope[T] (drives response_model +
OpenAPI). Exception handlers and middleware can't use response_model,
so they build the same dict shape here — guaranteeing every response,
success or error, is byte-for-byte the same structure.
"""

from __future__ import annotations

from typing import Any


def error_body(
    *,
    code: str,
    message: str,
    field: str | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Canonical error envelope as a plain dict.

    Matches Envelope shape: data=null, structured errors[].
    """
    err: dict[str, Any] = {"code": code, "message": message}
    if field is not None:
        err["field"] = field
    return {"data": None, "meta": meta or {}, "errors": [err]}


def errors_body(
    errors: list[dict[str, Any]],
    *,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Canonical error envelope carrying multiple errors (e.g. validation)."""
    return {"data": None, "meta": meta or {}, "errors": errors}


def success_body(
    data: Any,
    *,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Canonical success envelope as a plain dict."""
    return {"data": data, "meta": meta or {}, "errors": []}
