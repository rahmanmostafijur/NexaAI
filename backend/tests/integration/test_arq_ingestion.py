"""Document indexing through a real Redis queue and an arq worker."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest
from arq.connections import RedisSettings
from arq.worker import Worker

from app.core.config import Settings, get_settings
from app.db.session import get_session_factory
from app.models import Document
from app.rag.ingestion import IngestionService
from app.rag.queue import ArqIngestionQueue
from app.worker import index_document
from tests.integration.test_ingestion_recovery import FlakyEmbeddings

pytestmark = pytest.mark.usefixtures("database")


async def new_document(svc: IngestionService) -> uuid.UUID:
    document = await svc.create_document(
        data=f"# Notes\n\nQueue content {uuid.uuid4()} about dock scheduling.".encode(),
        filename=f"queue-{uuid.uuid4().hex[:6]}.md",
        content_type="text/markdown",
        title=None,
        uploaded_by=None,
    )
    return document.id


async def status_of(document_id: uuid.UUID) -> str:
    async with get_session_factory()() as session:
        document = await session.get(Document, document_id)
        assert document is not None
        return document.status


async def drain(url: str, queue_name: str, svc: IngestionService, settings: Settings) -> None:
    """Run burst workers until the queue has nothing left to do (deferred retries included)."""

    async def on_startup(ctx: dict[str, Any]) -> None:
        ctx["ingestion"] = svc
        ctx["settings"] = settings

    for _ in range(20):
        worker = Worker(
            functions=[index_document],
            redis_settings=RedisSettings.from_dsn(url),
            queue_name=queue_name,
            on_startup=on_startup,
            burst=True,
            max_tries=settings.ingestion_max_attempts,
            keep_result=0,
            handle_signals=False,
        )
        await worker.async_run()
        pending = await worker.pool.zcard(queue_name)
        # Worker.close() sends SIGUSR1, which does not exist on Windows; closing the pool is
        # all a finished burst worker needs.
        await worker.pool.aclose()
        if not pending:
            return
        await asyncio.sleep(0.3)


async def test_a_worker_indexes_an_enqueued_document(redis_url, embeddings) -> None:
    settings = get_settings()
    svc = IngestionService(get_session_factory(), embeddings, settings)
    queue_name = f"test:{uuid.uuid4().hex}"
    queue = ArqIngestionQueue(redis_url, queue_name=queue_name)
    await queue.start()
    document_id = await new_document(svc)

    await queue.enqueue(document_id)
    await queue.enqueue(document_id)  # duplicate while queued: ignored
    await drain(redis_url, queue_name, svc, settings)
    await queue.aclose()

    assert await status_of(document_id) == "indexed"


async def test_a_transient_failure_is_retried_with_backoff(redis_url, embeddings) -> None:
    settings = get_settings().model_copy(update={"ingestion_retry_base_seconds": 0.2})
    svc = IngestionService(get_session_factory(), FlakyEmbeddings(embeddings, failures=1), settings)
    queue_name = f"test:{uuid.uuid4().hex}"
    queue = ArqIngestionQueue(redis_url, queue_name=queue_name)
    await queue.start()
    document_id = await new_document(svc)

    await queue.enqueue(document_id)
    await drain(redis_url, queue_name, svc, settings)
    await queue.aclose()

    assert await status_of(document_id) == "indexed"


async def test_a_permanent_failure_is_not_retried_forever(redis_url, embeddings) -> None:
    settings = get_settings().model_copy(
        update={"ingestion_retry_base_seconds": 0.1, "ingestion_max_attempts": 2}
    )
    svc = IngestionService(
        get_session_factory(), FlakyEmbeddings(embeddings, failures=99), settings
    )
    queue_name = f"test:{uuid.uuid4().hex}"
    queue = ArqIngestionQueue(redis_url, queue_name=queue_name)
    await queue.start()
    document_id = await new_document(svc)

    await queue.enqueue(document_id)
    await drain(redis_url, queue_name, svc, settings)
    await queue.aclose()

    assert await status_of(document_id) == "failed"
