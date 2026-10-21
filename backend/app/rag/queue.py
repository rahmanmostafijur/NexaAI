"""Job queues for document indexing.

Two interchangeable backends:

* `InProcessIngestionQueue` (default): asyncio tasks inside the API process. No extra
  infrastructure; jobs lost in a crash are re-queued by the startup/periodic recovery sweep.
* `ArqIngestionQueue`: jobs go to Redis and are executed by one or more `arq` workers
  (`python -m arq app.worker.WorkerSettings`), so indexing survives API restarts and scales
  out. Retries use arq's own deferral.

Both retry transient failures with exponential backoff and stop after `max_attempts`.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Protocol

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

logger = logging.getLogger(__name__)

JOB_NAME = "index_document"
DEFAULT_QUEUE = "arq:queue"
_SHUTDOWN_GRACE_SECONDS = 20.0


class JobOutcome(StrEnum):
    DONE = "done"  # finished: indexed, or failed for good
    RETRY = "retry"  # transient failure: run again after a backoff


JobRunner = Callable[[uuid.UUID, int, int], Awaitable[JobOutcome]]
Sleeper = Callable[[float], Awaitable[None]]


def backoff_seconds(base: float, attempt: int) -> float:
    """Delay before attempt `attempt + 1`: base, 2*base, 4*base, ..."""
    return base * (2 ** (attempt - 1))


class IngestionQueue(Protocol):
    async def start(self) -> None: ...

    async def enqueue(self, document_id: uuid.UUID) -> None: ...

    async def aclose(self) -> None: ...


class InProcessIngestionQueue:
    def __init__(
        self,
        runner: JobRunner,
        *,
        max_attempts: int,
        retry_base_seconds: float,
        sleep: Sleeper = asyncio.sleep,
    ) -> None:
        self._runner = runner
        self._max_attempts = max_attempts
        self._retry_base = retry_base_seconds
        self._sleep = sleep
        self._tasks: dict[uuid.UUID, asyncio.Task[None]] = {}

    async def start(self) -> None:
        return None

    async def enqueue(self, document_id: uuid.UUID) -> None:
        if document_id in self._tasks:
            return  # already queued or running
        task = asyncio.create_task(self._run(document_id), name=f"index-{document_id}")
        self._tasks[document_id] = task
        task.add_done_callback(lambda _: self._tasks.pop(document_id, None))

    async def _run(self, document_id: uuid.UUID) -> None:
        for attempt in range(1, self._max_attempts + 1):
            try:
                outcome = await self._runner(document_id, attempt, self._max_attempts)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Indexing job crashed for document %s", document_id)
                return
            if outcome is JobOutcome.DONE or attempt == self._max_attempts:
                return
            await self._sleep(backoff_seconds(self._retry_base, attempt))

    async def aclose(self, grace_seconds: float = _SHUTDOWN_GRACE_SECONDS) -> None:
        """Let running jobs finish, then cancel stragglers. Cancelled documents are recovered
        by the stuck-document sweep on the next start."""
        pending = list(self._tasks.values())
        if not pending:
            return
        _, still_running = await asyncio.wait(pending, timeout=grace_seconds)
        for task in still_running:
            task.cancel()
        for task in still_running:
            with contextlib.suppress(asyncio.CancelledError):
                await task


class ArqIngestionQueue:
    def __init__(self, redis_url: str, *, queue_name: str = DEFAULT_QUEUE) -> None:
        self._settings = RedisSettings.from_dsn(redis_url)
        self._queue_name = queue_name
        self._pool: ArqRedis | None = None

    async def start(self) -> None:
        self._pool = await create_pool(self._settings)

    async def enqueue(self, document_id: uuid.UUID) -> None:
        if self._pool is None:
            await self.start()
        assert self._pool is not None
        # A fixed job id de-duplicates while the job is queued or running.
        await self._pool.enqueue_job(
            JOB_NAME,
            str(document_id),
            _job_id=f"index-{document_id}",
            _queue_name=self._queue_name,
        )

    async def aclose(self) -> None:
        if self._pool is not None:
            await self._pool.aclose()
            self._pool = None
