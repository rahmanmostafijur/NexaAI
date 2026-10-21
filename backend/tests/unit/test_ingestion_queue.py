"""In-process ingestion queue: retries with backoff, bounded attempts, clean shutdown."""

from __future__ import annotations

import asyncio
import uuid

from app.rag.queue import InProcessIngestionQueue, JobOutcome


class Runner:
    def __init__(self, outcomes: list[JobOutcome]) -> None:
        self.outcomes = outcomes
        self.calls: list[tuple[uuid.UUID, int, int]] = []

    async def __call__(self, document_id: uuid.UUID, attempt: int, max_attempts: int) -> JobOutcome:
        self.calls.append((document_id, attempt, max_attempts))
        return self.outcomes.pop(0)


def make_queue(
    runner: Runner, *, max_attempts: int = 3
) -> tuple[InProcessIngestionQueue, list[float]]:
    delays: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        delays.append(seconds)

    queue = InProcessIngestionQueue(
        runner, max_attempts=max_attempts, retry_base_seconds=2.0, sleep=fake_sleep
    )
    return queue, delays


async def test_runs_the_job_once_when_it_succeeds() -> None:
    runner = Runner([JobOutcome.DONE])
    queue, delays = make_queue(runner)
    document_id = uuid.uuid4()

    await queue.enqueue(document_id)
    await queue.aclose()

    assert runner.calls == [(document_id, 1, 3)]
    assert delays == []


async def test_retries_with_exponential_backoff_until_it_succeeds() -> None:
    runner = Runner([JobOutcome.RETRY, JobOutcome.RETRY, JobOutcome.DONE])
    queue, delays = make_queue(runner)

    await queue.enqueue(uuid.uuid4())
    await queue.aclose()

    assert [attempt for _, attempt, _ in runner.calls] == [1, 2, 3]
    assert delays == [2.0, 4.0]


async def test_stops_after_the_last_attempt() -> None:
    runner = Runner([JobOutcome.RETRY, JobOutcome.RETRY])
    queue, _ = make_queue(runner, max_attempts=2)

    await queue.enqueue(uuid.uuid4())
    await queue.aclose()

    assert len(runner.calls) == 2


async def test_a_crashing_runner_does_not_kill_the_queue() -> None:
    class Boom(Runner):
        async def __call__(self, document_id, attempt, max_attempts):  # type: ignore[no-untyped-def]
            self.calls.append((document_id, attempt, max_attempts))
            raise RuntimeError("worker bug")

    runner = Boom([])
    queue, _ = make_queue(runner)

    await queue.enqueue(uuid.uuid4())
    await queue.aclose()
    await queue.enqueue(uuid.uuid4())
    await queue.aclose()

    assert len(runner.calls) == 2


async def test_enqueueing_the_same_document_twice_runs_it_once_while_in_flight() -> None:
    gate = asyncio.Event()

    class Slow(Runner):
        async def __call__(self, document_id, attempt, max_attempts):  # type: ignore[no-untyped-def]
            self.calls.append((document_id, attempt, max_attempts))
            await gate.wait()
            return JobOutcome.DONE

    runner = Slow([])
    queue, _ = make_queue(runner)
    document_id = uuid.uuid4()

    await queue.enqueue(document_id)
    await queue.enqueue(document_id)
    await asyncio.sleep(0)
    gate.set()
    await queue.aclose()

    assert len(runner.calls) == 1


async def test_shutdown_cancels_jobs_that_outlive_the_grace_period() -> None:
    cancelled = asyncio.Event()

    class Hang(Runner):
        async def __call__(self, document_id, attempt, max_attempts):  # type: ignore[no-untyped-def]
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                raise
            return JobOutcome.DONE

    queue, _ = make_queue(Hang([]))
    await queue.enqueue(uuid.uuid4())
    await asyncio.sleep(0)

    await queue.aclose(grace_seconds=0.05)

    assert cancelled.is_set()
