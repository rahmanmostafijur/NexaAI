"""Redis-backed rate limiting: same `hit(key, limit, window)` contract as the in-memory limiter."""

from __future__ import annotations

import asyncio
import uuid

import pytest

from app.core.config import Settings
from app.core.errors import RateLimitedError
from app.core.rate_limit import (
    RateLimiterProxy,
    RedisRateLimiter,
    SlidingWindowRateLimiter,
    build_rate_limiter,
)


def unique_key() -> str:
    return f"test:{uuid.uuid4().hex}"


@pytest.fixture
async def limiter(redis_url):
    instance = RedisRateLimiter(redis_url, fallback=SlidingWindowRateLimiter())
    yield instance
    await instance.aclose()


async def test_allows_up_to_the_limit_then_rejects_with_retry_after(limiter) -> None:
    key = unique_key()
    for _ in range(3):
        await limiter.hit(key, limit=3, window_seconds=60)

    with pytest.raises(RateLimitedError) as caught:
        await limiter.hit(key, limit=3, window_seconds=60)

    assert 1 <= caught.value.retry_after <= 60


async def test_keys_are_independent(limiter) -> None:
    first, second = unique_key(), unique_key()
    await limiter.hit(first, limit=1, window_seconds=60)

    await limiter.hit(second, limit=1, window_seconds=60)
    with pytest.raises(RateLimitedError):
        await limiter.hit(first, limit=1, window_seconds=60)


async def test_the_window_slides(limiter) -> None:
    key = unique_key()
    await limiter.hit(key, limit=1, window_seconds=1)
    with pytest.raises(RateLimitedError):
        await limiter.hit(key, limit=1, window_seconds=1)

    await asyncio.sleep(1.2)

    await limiter.hit(key, limit=1, window_seconds=1)


async def test_the_limit_holds_under_concurrency(limiter) -> None:
    key = unique_key()

    async def attempt() -> bool:
        try:
            await limiter.hit(key, limit=10, window_seconds=60)
        except RateLimitedError:
            return False
        return True

    results = await asyncio.gather(*(attempt() for _ in range(60)))

    assert sum(results) == 10


async def test_two_limiters_share_one_budget(redis_url) -> None:
    """Simulates two backend replicas using the same Redis."""
    one = RedisRateLimiter(redis_url, fallback=SlidingWindowRateLimiter())
    two = RedisRateLimiter(redis_url, fallback=SlidingWindowRateLimiter())
    key = unique_key()
    try:
        await one.hit(key, limit=2, window_seconds=60)
        await two.hit(key, limit=2, window_seconds=60)
        with pytest.raises(RateLimitedError):
            await one.hit(key, limit=2, window_seconds=60)
    finally:
        await one.aclose()
        await two.aclose()


async def test_an_unreachable_redis_falls_back_to_the_local_limiter() -> None:
    limiter = RedisRateLimiter(
        "redis://127.0.0.1:1/0", fallback=SlidingWindowRateLimiter(), connect_timeout=0.2
    )
    key = unique_key()
    try:
        await limiter.hit(key, limit=1, window_seconds=60)  # does not raise: degraded, not down
        with pytest.raises(RateLimitedError):
            await limiter.hit(key, limit=1, window_seconds=60)  # still limited, per instance
    finally:
        await limiter.aclose()


async def test_the_proxy_delegates_to_the_configured_backend() -> None:
    proxy = RateLimiterProxy(SlidingWindowRateLimiter())
    await proxy.hit("k", limit=1, window_seconds=60)
    with pytest.raises(RateLimitedError):
        await proxy.hit("k", limit=1, window_seconds=60)

    proxy.use(SlidingWindowRateLimiter())

    await proxy.hit("k", limit=1, window_seconds=60)


def test_build_rate_limiter_selects_the_backend_from_settings() -> None:
    memory = build_rate_limiter(Settings(_env_file=None))
    shared = build_rate_limiter(
        Settings(_env_file=None, rate_limit_backend="redis", redis_url="redis://localhost:6379/0")
    )

    assert isinstance(memory, SlidingWindowRateLimiter)
    assert isinstance(shared, RedisRateLimiter)
