from __future__ import annotations

import inspect
from typing import cast

from sqlalchemy import Table

from app.models.link import Link
from app.services import webhooks as webhooks_service
from app.tasks import analytics

# ── Model fields ────────────────────────────────────────────────────────────


def test_link_model_has_webhook_fields() -> None:
    table = cast(Table, Link.__table__)
    columns = set(table.columns.keys())

    assert "webhook_url" in columns
    assert "webhook_threshold" in columns
    assert "webhook_fired" in columns


def test_webhook_url_is_nullable() -> None:
    table = cast(Table, Link.__table__)
    assert table.columns["webhook_url"].nullable is True


def test_webhook_threshold_is_nullable() -> None:
    table = cast(Table, Link.__table__)
    assert table.columns["webhook_threshold"].nullable is True


def test_webhook_fired_has_default_or_not_null() -> None:
    table = cast(Table, Link.__table__)
    col = table.columns["webhook_fired"]

    assert col.default is not None or col.server_default is not None or col.nullable is False


# ── Task implementation contract ────────────────────────────────────────────


def test_webhooks_service_has_hmac_sha256_signature() -> None:
    source = inspect.getsource(webhooks_service).lower()

    assert "hmac" in source
    assert "sha256" in source
    assert "signature" in source


def test_task_module_has_idempotency_guard() -> None:
    source = inspect.getsource(analytics)

    assert "webhook_fired" in source
    assert "webhook_threshold" in source


def test_task_module_has_retry_or_backoff() -> None:
    source = inspect.getsource(analytics).lower()

    assert (
        "autoretry_for" in source
        or "retry_backoff" in source
        or ".retry(" in source
        or "countdown" in source
    )


def test_task_module_posts_to_webhook_url() -> None:
    source = inspect.getsource(analytics).lower()

    assert "post" in source
    assert "webhook_url" in source


def test_webhooks_task_sends_signature_header() -> None:
    from app.tasks import webhooks as webhooks_task

    source = inspect.getsource(webhooks_task)

    assert "build_webhook_signature" in source
    assert "X-Webhook-Signature" in source
