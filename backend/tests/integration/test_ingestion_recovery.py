"""Documents never stay stuck: retries for transient failures, recovery after a crash."""

from __future__ import annotations

import asyncio
import pathlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update

from app.core.config import get_settings
from app.core.errors import EmbeddingError
from app.db.session import get_session_factory
from app.models import Document
from app.rag.ingestion import IngestionService
from app.rag.queue import JobOutcome

pytestmark = pytest.mark.usefixtures("database")

STUCK_AFTER = 600
MAX_ATTEMPTS = 3


class FlakyEmbeddings:
    """Delegates to the hashing embedder but fails the first `failures` calls."""

    name = "flaky"
    model = "flaky-test"
    dimension = 384

    def __init__(self, inner, failures: int) -> None:
        self._inner = inner
        self.failures = failures

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if self.failures > 0:
            self.failures -= 1
            raise EmbeddingError("embedding service unavailable")
        return await self._inner.embed_documents(texts)

    async def embed_query(self, text: str) -> list[float]:
        return (await self.embed_documents([text]))[0]


def service(embeddings) -> IngestionService:
    return IngestionService(get_session_factory(), embeddings, get_settings())


async def new_document(svc: IngestionService) -> uuid.UUID:
    document = await svc.create_document(
        data=f"# Notes\n\nFresh content {uuid.uuid4()} about warehouse safety.".encode(),
        filename=f"notes-{uuid.uuid4().hex[:6]}.md",
        content_type="text/markdown",
        title=None,
        uploaded_by=None,
    )
    return document.id


async def age(document_id: uuid.UUID, *, status: str, seconds: int, attempts: int = 0) -> None:
    async with get_session_factory()() as session:
        await session.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(
                status=status,
                updated_at=datetime.now(UTC) - timedelta(seconds=seconds),
                meta={"ingest_attempts": attempts},
            )
        )
        await session.commit()


async def state(document_id: uuid.UUID) -> Document:
    async with get_session_factory()() as session:
        document = await session.get(Document, document_id)
        assert document is not None
        return document


class Recorder:
    def __init__(self) -> None:
        self.ids: list[uuid.UUID] = []

    async def __call__(self, document_id: uuid.UUID) -> None:
        self.ids.append(document_id)


async def test_a_transient_failure_returns_the_document_to_pending_for_a_retry(embeddings) -> None:
    svc = service(FlakyEmbeddings(embeddings, failures=1))
    document_id = await new_document(svc)

    outcome = await svc.run_job(document_id, attempt=1, max_attempts=MAX_ATTEMPTS)

    assert outcome is JobOutcome.RETRY
    document = await state(document_id)
    assert document.status == "pending"
    assert "retry" in (document.error or "").lower()
    assert document.meta["ingest_attempts"] == 1


async def test_the_retry_succeeds_once_the_dependency_recovers(embeddings) -> None:
    svc = service(FlakyEmbeddings(embeddings, failures=1))
    document_id = await new_document(svc)
    await svc.run_job(document_id, attempt=1, max_attempts=MAX_ATTEMPTS)

    outcome = await svc.run_job(document_id, attempt=2, max_attempts=MAX_ATTEMPTS)

    assert outcome is JobOutcome.DONE
    document = await state(document_id)
    assert document.status == "indexed" and document.error is None


async def test_the_last_attempt_marks_the_document_failed(embeddings) -> None:
    svc = service(FlakyEmbeddings(embeddings, failures=99))
    document_id = await new_document(svc)

    outcome = await svc.run_job(document_id, attempt=MAX_ATTEMPTS, max_attempts=MAX_ATTEMPTS)

    assert outcome is JobOutcome.DONE
    document = await state(document_id)
    assert document.status == "failed"
    assert document.error


async def test_unreadable_documents_fail_immediately_without_retrying(embeddings) -> None:
    svc = service(embeddings)
    document_id = await new_document(svc)
    await asyncio.to_thread(pathlib.Path((await state(document_id)).stored_path).unlink)

    outcome = await svc.run_job(document_id, attempt=1, max_attempts=MAX_ATTEMPTS)

    assert outcome is JobOutcome.DONE
    assert (await state(document_id)).status == "failed"


async def test_recovery_requeues_documents_orphaned_by_a_crash(embeddings) -> None:
    svc = service(embeddings)
    processing, pending = await new_document(svc), await new_document(svc)
    await age(processing, status="processing", seconds=STUCK_AFTER + 60, attempts=1)
    await age(pending, status="pending", seconds=STUCK_AFTER + 60)
    recorder = Recorder()

    report = await svc.recover_stuck(
        recorder, stuck_after_seconds=STUCK_AFTER, max_attempts=MAX_ATTEMPTS
    )

    assert {processing, pending} <= set(recorder.ids)
    assert report.requeued >= 2
    assert (await state(processing)).status == "pending"


async def test_recovery_leaves_active_and_finished_documents_alone(embeddings) -> None:
    svc = service(embeddings)
    active, done = await new_document(svc), await new_document(svc)
    await age(active, status="processing", seconds=5)
    await age(done, status="indexed", seconds=STUCK_AFTER * 10)
    recorder = Recorder()

    await svc.recover_stuck(recorder, stuck_after_seconds=STUCK_AFTER, max_attempts=MAX_ATTEMPTS)

    assert active not in recorder.ids and done not in recorder.ids
    assert (await state(active)).status == "processing"
    assert (await state(done)).status == "indexed"


async def test_recovery_gives_up_on_documents_that_keep_crashing_the_indexer(embeddings) -> None:
    svc = service(embeddings)
    poison = await new_document(svc)
    await age(poison, status="processing", seconds=STUCK_AFTER + 60, attempts=MAX_ATTEMPTS)
    recorder = Recorder()

    report = await svc.recover_stuck(
        recorder, stuck_after_seconds=STUCK_AFTER, max_attempts=MAX_ATTEMPTS
    )

    assert poison not in recorder.ids
    assert report.failed >= 1
    document = await state(poison)
    assert document.status == "failed"
    assert "interrupted" in (document.error or "").lower()


async def test_a_restart_reindexes_a_document_orphaned_mid_processing(embeddings, fake_llm) -> None:
    from app.main import create_app

    svc = service(embeddings)
    document_id = await new_document(svc)
    stuck_for = get_settings().ingestion_stuck_timeout_seconds + 60
    await age(document_id, status="processing", seconds=stuck_for, attempts=1)

    application = create_app(get_settings(), llm=fake_llm, embeddings=embeddings)
    async with application.router.lifespan_context(application):
        for _ in range(200):
            if (await state(document_id)).status == "indexed":
                break
            await asyncio.sleep(0.1)

    assert (await state(document_id)).status == "indexed"


async def test_reindex_resets_the_attempt_counter(embeddings) -> None:
    svc = service(embeddings)
    document_id = await new_document(svc)
    await age(document_id, status="failed", seconds=1, attempts=MAX_ATTEMPTS)

    await svc.mark_for_reindex(document_id)

    document = await state(document_id)
    assert document.status == "pending"
    assert document.meta.get("ingest_attempts", 0) == 0
