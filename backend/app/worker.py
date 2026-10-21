"""Arq worker that indexes uploaded documents.

    python -m arq app.worker.WorkerSettings

Run it next to the API when `INGESTION_BACKEND=arq`. Several workers can share one queue.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from arq import Retry
from arq.connections import RedisSettings

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.db.session import dispose_engines, get_session_factory
from app.embeddings.factory import get_embedding_provider
from app.rag.ingestion import IngestionService
from app.rag.queue import DEFAULT_QUEUE, JobOutcome, backoff_seconds

logger = logging.getLogger(__name__)

_JOB_TIMEOUT_SECONDS = 30 * 60


async def index_document(ctx: dict[str, Any], document_id: str) -> None:
    """Index one document; ask arq to retry later after a transient failure."""
    service: IngestionService = ctx["ingestion"]
    settings: Settings = ctx["settings"]
    attempt: int = ctx["job_try"]
    outcome = await service.run_job(
        uuid.UUID(document_id), attempt=attempt, max_attempts=settings.ingestion_max_attempts
    )
    if outcome is JobOutcome.RETRY:
        raise Retry(defer=backoff_seconds(settings.ingestion_retry_base_seconds, attempt))


async def on_startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    ctx["settings"] = settings
    ctx["ingestion"] = IngestionService(get_session_factory(), get_embedding_provider(), settings)
    logger.info("Ingestion worker ready")


async def on_shutdown(ctx: dict[str, Any]) -> None:
    await dispose_engines()


class WorkerSettings:
    functions = [index_document]  # noqa: RUF012 - arq reads this class attribute
    on_startup = on_startup
    on_shutdown = on_shutdown
    queue_name = DEFAULT_QUEUE
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url or "redis://localhost:6379")
    max_tries = get_settings().ingestion_max_attempts
    job_timeout = _JOB_TIMEOUT_SECONDS
    max_jobs = 2
    keep_result = 0  # the document row is the result; lets a document be re-enqueued later
