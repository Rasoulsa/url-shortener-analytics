import pytest

from app.services.rate_limiter import check_rate_limit


class FakeRedis:
    """Minimal fake that simulates ZCARD growth for the Lua eval."""

    def __init__(self) -> None:
        self.count = 0

    async def eval(self, script, numkeys, *args):
        # args = key, now_ms, window_ms, limit, member
        limit = int(args[3])
        self.count += 1
        if self.count > limit:
            return [0, 0, 5000]
        remaining = limit - self.count
        return [1, remaining, 5000]


@pytest.mark.asyncio
async def test_rate_limit_allows_then_blocks():
    redis = FakeRedis()

    results = []
    for _ in range(5):
        r = await check_rate_limit(
            redis,
            key="rate_limit:test",
            limit=3,
            window_seconds=60,
        )
        results.append(r.allowed)

    assert results == [True, True, True, False, False]


@pytest.mark.asyncio
async def test_rate_limit_fails_open_on_redis_error():
    class BrokenRedis:
        async def eval(self, *args, **kwargs):
            raise RuntimeError("redis down")

    result = await check_rate_limit(
        BrokenRedis(),
        key="rate_limit:test",
        limit=1,
        window_seconds=60,
    )

    assert result.allowed is True
