"""Sliding-window rate limiting with interchangeable storage.

Every limiter implements `hit(key, limit, window_seconds)`, which records a request and raises
`RateLimitedError` once `key` has made `limit` requests inside the window.

* `SlidingWindowRateLimiter` keeps timestamps in process memory: right for one backend instance
  and for development.
* `RedisRateLimiter` keeps them in a Redis sorted set updated by one atomic Lua script, so
  every backend replica shares one budget. If Redis cannot be reached it degrades to the
  in-memory limiter instead of rejecting traffic (limits then apply per instance).

API modules use the module-level `rate_limiter` proxy; `configure_rate_limiter` chooses the
backend at startup from `RATE_LIMIT_BACKEND`.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
import uuid
from collections import defaultdict, deque
from collections.abc import Callable
from typing import Any, Protocol

import redis.asyncio as aioredis

from app.core.config import Settings
from app.core.errors import RateLimitedError

logger = logging.getLogger(__name__)

_MAX_TRACKED_KEYS = 10_000
_LOG_EVERY_SECONDS = 30.0

# KEYS[1] = window key; ARGV = window_ms, limit, member.
# Uses the Redis server clock so replicas with skewed clocks still agree.
# Returns {1, 0} when allowed, or {0, retry_after_ms} when the limit is reached.
_SLIDING_WINDOW_LUA = """
local time = redis.call('TIME')
local now = tonumber(time[1]) * 1000 + math.floor(tonumber(time[2]) / 1000)
local window = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])
redis.call('ZREMRANGEBYSCORE', KEYS[1], 0, now - window)
if redis.call('ZCARD', KEYS[1]) >= limit then
    local oldest = redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')
    return {0, tonumber(oldest[2]) + window - now}
end
redis.call('ZADD', KEYS[1], now, ARGV[3])
redis.call('PEXPIRE', KEYS[1], window)
return {1, 0}
"""


class RateLimiter(Protocol):
    async def hit(self, key: str, limit: int, window_seconds: float = 60.0) -> None: ...

    async def aclose(self) -> None: ...


def _too_many(retry_after_seconds: float) -> RateLimitedError:
    retry_after = max(1, math.ceil(retry_after_seconds))
    return RateLimitedError(
        f"Too many requests. Please retry in {retry_after} seconds.", retry_after
    )


class SlidingWindowRateLimiter:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()
        self._clock = clock

    async def hit(self, key: str, limit: int, window_seconds: float = 60.0) -> None:
        """Record a request for `key`; raise RateLimitedError if over the limit."""
        async with self._lock:
            now = self._clock()
            hits = self._hits[key]
            while hits and hits[0] <= now - window_seconds:
                hits.popleft()
            if len(hits) >= limit:
                raise _too_many(hits[0] + window_seconds - now)
            hits.append(now)
            if len(self._hits) > _MAX_TRACKED_KEYS:
                self._evict_idle(now, window_seconds)

    def _evict_idle(self, now: float, window_seconds: float) -> None:
        idle = [k for k, v in self._hits.items() if not v or v[-1] <= now - window_seconds]
        for key in idle:
            del self._hits[key]

    def reset(self) -> None:
        self._hits.clear()

    async def aclose(self) -> None:
        return None


class RedisRateLimiter:
    def __init__(
        self,
        url: str,
        *,
        fallback: SlidingWindowRateLimiter | None = None,
        prefix: str = "nexa:rl:",
        connect_timeout: float = 1.0,
    ) -> None:
        self._client: aioredis.Redis = aioredis.from_url(
            url, socket_connect_timeout=connect_timeout, socket_timeout=connect_timeout
        )
        self._script: Any = self._client.register_script(_SLIDING_WINDOW_LUA)
        self._fallback = fallback or SlidingWindowRateLimiter()
        self._prefix = prefix
        self._last_logged = 0.0

    async def hit(self, key: str, limit: int, window_seconds: float = 60.0) -> None:
        window_ms = max(1, int(window_seconds * 1000))
        try:
            allowed, retry_after_ms = await self._script(
                keys=[f"{self._prefix}{key}"], args=[window_ms, limit, uuid.uuid4().hex]
            )
        except (aioredis.RedisError, OSError, TimeoutError):
            self._log_degraded()
            await self._fallback.hit(key, limit, window_seconds)
            return
        if not allowed:
            raise _too_many(int(retry_after_ms) / 1000)

    def _log_degraded(self) -> None:
        now = time.monotonic()
        if now - self._last_logged >= _LOG_EVERY_SECONDS:
            self._last_logged = now
            logger.warning("Redis unavailable for rate limiting; using per-instance limits")

    async def aclose(self) -> None:
        await self._client.aclose()


class RateLimiterProxy:
    """Stable import target for API modules; the backend behind it is chosen at startup."""

    def __init__(self, backend: RateLimiter) -> None:
        self._backend = backend

    def use(self, backend: RateLimiter) -> None:
        self._backend = backend

    async def hit(self, key: str, limit: int, window_seconds: float = 60.0) -> None:
        await self._backend.hit(key, limit, window_seconds)

    def reset(self) -> None:
        """Forget in-memory counters (tests). Redis counters expire on their own."""
        if isinstance(self._backend, SlidingWindowRateLimiter):
            self._backend.reset()

    async def aclose(self) -> None:
        await self._backend.aclose()


def build_rate_limiter(settings: Settings) -> RateLimiter:
    if settings.rate_limit_backend == "redis":
        return RedisRateLimiter(settings.redis_url)
    return SlidingWindowRateLimiter()


rate_limiter = RateLimiterProxy(SlidingWindowRateLimiter())


def configure_rate_limiter(settings: Settings) -> None:
    """Select the limiter for this process; called once from the application lifespan."""
    rate_limiter.use(build_rate_limiter(settings))
