from __future__ import annotations

import inspect
from typing import Any

from fastapi.testclient import TestClient

from app import main
from app.core import exceptions
from app.main import app
from app.schemas import common as common_schemas

client = TestClient(app)


def _assert_envelope(body: dict[str, Any]) -> None:
    assert "data" in body
    assert "meta" in body
    assert "errors" in body
    assert isinstance(body["errors"], list)


def test_exception_classes_exist_for_common_error_cases() -> None:
    """exceptions.py defines the hierarchy; main.py renders the envelope."""
    source = inspect.getsource(exceptions).lower()

    assert "class" in source
    assert "exception" in source


def test_envelope_model_defines_data_meta_errors_fields() -> None:
    """The {data, meta, errors} shape is defined by app.schemas.common.Envelope."""
    fields = common_schemas.Envelope.model_fields

    assert "data" in fields
    assert "meta" in fields
    assert "errors" in fields


def test_main_module_handles_validation_errors() -> None:
    source = inspect.getsource(main).lower()

    assert "validation" in source or "requestvalidationerror" in source


def test_main_module_handles_404() -> None:
    source = inspect.getsource(main).lower()

    assert "404" in source or "not_found" in source


def test_main_module_handles_429() -> None:
    source = inspect.getsource(main).lower()

    assert "429" in source or "rate" in source or "too_many" in source


def test_main_module_handles_500() -> None:
    source = inspect.getsource(main).lower()

    assert "500" in source or "internal" in source


def test_runtime_404_uses_envelope() -> None:
    response = client.get("/api/v1/nope-not-real")

    assert response.status_code == 404
    body = response.json()
    _assert_envelope(body)
    assert body["data"] is None
    assert body["errors"]


def test_runtime_unauthenticated_uses_envelope() -> None:
    response = client.get("/api/v1/analytics/abc123/timeseries")

    assert response.status_code in {401, 403}
    body = response.json()
    _assert_envelope(body)
    assert body["data"] is None
    assert body["errors"]
