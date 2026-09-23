"""In-process sliding-window rate limiter.

Good enough for a single backend instance. For horizontal scaling, swap the
storage for Redis (same interface: `hit(key, limit, window)`).
"""

from __future__ import annotations

import asyncio
import math
import time
from collections import defaultdict, deque
from collections.abc import Callable

from app.core.errors import RateLimitedError

_MAX_TRACKED_KEYS = 10_000


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
                retry_after = max(1, math.ceil(hits[0] + window_seconds - now))
                raise RateLimitedError(
                    f"Too many requests. Please retry in {retry_after} seconds.", retry_after
                )
            hits.append(now)
            if len(self._hits) > _MAX_TRACKED_KEYS:
                self._evict_idle(now, window_seconds)

    def _evict_idle(self, now: float, window_seconds: float) -> None:
        idle = [k for k, v in self._hits.items() if not v or v[-1] <= now - window_seconds]
        for key in idle:
            del self._hits[key]

    def reset(self) -> None:
        self._hits.clear()


rate_limiter = SlidingWindowRateLimiter()
