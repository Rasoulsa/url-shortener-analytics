from app.services.webhooks import (
    build_webhook_signature,
    canonical_json_bytes,
)


def test_webhook_signature_is_stable() -> None:
    payload = {
        "event_id": "link.threshold.1.10",
        "event_type": "link.click_threshold_reached",
        "data": {
            "short_code": "abc123",
            "click_count": 10,
        },
    }

    body_1 = canonical_json_bytes(payload)
    body_2 = canonical_json_bytes(
        {
            "data": {
                "click_count": 10,
                "short_code": "abc123",
            },
            "event_type": "link.click_threshold_reached",
            "event_id": "link.threshold.1.10",
        }
    )

    assert body_1 == body_2

    sig_1 = build_webhook_signature(
        secret="test-secret",
        timestamp="1234567890",
        body=body_1,
    )
    sig_2 = build_webhook_signature(
        secret="test-secret",
        timestamp="1234567890",
        body=body_2,
    )

    assert sig_1 == sig_2
    assert sig_1.startswith("sha256=")


def test_webhook_signature_changes_when_body_changes() -> None:
    body_1 = canonical_json_bytes({"a": 1})
    body_2 = canonical_json_bytes({"a": 2})

    sig_1 = build_webhook_signature(
        secret="test-secret",
        timestamp="1234567890",
        body=body_1,
    )
    sig_2 = build_webhook_signature(
        secret="test-secret",
        timestamp="1234567890",
        body=body_2,
    )

    assert sig_1 != sig_2
