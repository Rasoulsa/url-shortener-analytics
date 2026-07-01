from __future__ import annotations

from typing import Any

import pytest

from app.services.counters import (
    PENDING_CLICK_COUNTER_SET_KEY,
    increment_link_click_counter,
    link_click_counter_key,
)
from app.tasks import analytics


def test_pending_click_counter_set_key() -> None:
    assert PENDING_CLICK_COUNTER_SET_KEY == "analytics:click_counters:pending"


def test_link_click_counter_key() -> None:
    assert link_click_counter_key("abc123") == "link:abc123:clicks"


@pytest.mark.asyncio
async def test_increment_link_click_counter_tracks_pending_short_code() -> None:
    class FakePipeline:
        def __init__(self) -> None:
            self.incremented_key: str | None = None
            self.pending_set_key: str | None = None
            self.pending_short_code: str | None = None
            self.expired_key: str | None = None
            self.ttl_seconds: int | None = None

        def incr(self, key: str) -> None:
            self.incremented_key = key

        def sadd(self, key: str, value: str) -> None:
            self.pending_set_key = key
            self.pending_short_code = value

        def expire(self, key: str, seconds: int) -> None:
            self.expired_key = key
            self.ttl_seconds = seconds

        async def execute(self) -> list[Any]:
            return [1, 1, True]

    class FakeRedis:
        def __init__(self) -> None:
            self.pipeline_instance = FakePipeline()

        def pipeline(self, transaction: bool = True) -> FakePipeline:
            assert transaction is True
            return self.pipeline_instance

    redis = FakeRedis()

    value = await increment_link_click_counter(redis, "abc123")  # type: ignore[arg-type]

    assert value == 1
    assert redis.pipeline_instance.incremented_key == link_click_counter_key("abc123")
    assert redis.pipeline_instance.pending_set_key == PENDING_CLICK_COUNTER_SET_KEY
    assert redis.pipeline_instance.pending_short_code == "abc123"
    assert redis.pipeline_instance.expired_key == link_click_counter_key("abc123")
    assert redis.pipeline_instance.ttl_seconds is not None


def test_flush_pending_click_counters_updates_database_counter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeRedis:
        def __init__(self) -> None:
            self.values: dict[str, Any] = {
                link_click_counter_key("abc123"): "3",
            }
            self.sets: dict[str, set[str]] = {
                PENDING_CLICK_COUNTER_SET_KEY: {"abc123"},
            }

        def smembers(self, key: str) -> set[str]:
            return self.sets.get(key, set())

        def getdel(self, key: str) -> Any:
            return self.values.pop(key, None)

        def srem(self, key: str, value: str) -> int:
            self.sets.setdefault(key, set()).discard(value)
            return 1

        def sadd(self, key: str, value: str) -> int:
            self.sets.setdefault(key, set()).add(value)
            return 1

        def exists(self, key: str) -> int:
            return 1 if key in self.values else 0

        def pipeline(self, transaction: bool = True) -> Any:
            raise AssertionError("pipeline should not be used in successful test")

    calls: list[tuple[str, int]] = []

    async def fake_increment_link_click_count_by(
        *,
        short_code: str,
        count: int,
    ) -> bool:
        calls.append((short_code, count))
        return True

    monkeypatch.setattr(
        analytics,
        "_increment_link_click_count_by",
        fake_increment_link_click_count_by,
    )

    redis = FakeRedis()

    result = analytics._flush_pending_click_counters(redis)  # type: ignore[arg-type]

    assert result["processed_short_codes"] == 1
    assert result["flushed_links"] == 1
    assert result["flushed_clicks"] == 3
    assert result["skipped"] == 0
    assert calls == [("abc123", 3)]
    assert redis.values == {}
    assert redis.sets[PENDING_CLICK_COUNTER_SET_KEY] == set()
