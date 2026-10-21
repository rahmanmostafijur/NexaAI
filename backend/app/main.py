"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.agent.services import AgentServices
from app.api.metrics import router as metrics_router
from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.metrics import MetricsMiddleware
from app.core.middleware import RequestContextMiddleware
from app.core.rate_limit import configure_rate_limiter, rate_limiter
from app.core.security import hash_password
from app.core.sessions import SessionService
from app.db.session import dispose_engines, session_scope
from app.embeddings.base import EmbeddingProvider
from app.embeddings.factory import get_embedding_provider
from app.llm.base import LLMProvider
from app.llm.factory import get_llm_provider
from app.models import User

logger = logging.getLogger(__name__)


async def ensure_admin(settings: Settings) -> None:
    """A fresh deployment always has one administrator (from ADMIN_EMAIL/ADMIN_PASSWORD)."""
    async with session_scope() as session:
        if await session.scalar(select(User.id).where(User.role == "admin").limit(1)):
            return
        session.add(
            User(
                email=settings.admin_email.lower(),
                full_name="Administrator",
                password_hash=hash_password(settings.admin_password.get_secret_value()),
                role="admin",
            )
        )
        logger.info("Bootstrapped administrator account %s", settings.admin_email)


async def purge_stale_sessions(settings: Settings) -> None:
    """Drop long-expired and long-revoked sessions so the auth tables stay small."""
    async with session_scope() as session:
        removed = await SessionService(session, settings).purge_expired()
    if removed:
        logger.info("Purged %d stale auth sessions", removed)


async def sweep_stuck_documents(services: AgentServices, settings: Settings) -> None:
    """Re-queue documents orphaned by a crash, now and then periodically."""
    while True:
        try:
            await services.ingestion.recover_stuck(
                services.ingestion_queue.enqueue,
                stuck_after_seconds=settings.ingestion_stuck_timeout_seconds,
                max_attempts=settings.ingestion_max_attempts,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Stuck-document recovery failed; will retry on the next sweep")
        await asyncio.sleep(settings.ingestion_sweep_interval_seconds)


async def _warm_up(embeddings: EmbeddingProvider) -> None:
    """Load the embedding model in the background so the first question is fast."""
    try:
        await embeddings.embed_query("warm up")
    except Exception:
        logger.warning("Embedding warm-up failed; the model will load on first use")


def create_app(
    settings: Settings | None = None,
    *,
    llm: LLMProvider | None = None,
    embeddings: EmbeddingProvider | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.services = AgentServices.build(
            settings, llm or get_llm_provider(), embeddings or get_embedding_provider()
        )
        try:
            await ensure_admin(settings)
        except Exception:
            logger.exception("Could not verify the administrator account at startup")
        try:
            await purge_stale_sessions(settings)
        except Exception:
            logger.exception("Could not purge stale auth sessions at startup")
        configure_rate_limiter(settings)
        warm_up = asyncio.create_task(_warm_up(app.state.services.embeddings))
        try:
            await app.state.services.ingestion_queue.start()
        except Exception:
            logger.exception("Could not start the ingestion queue; uploads will stay pending")
        sweeper = asyncio.create_task(sweep_stuck_documents(app.state.services, settings))
        if not settings.llm_configured:
            logger.warning("No LLM configured: chat will use heuristic routing and cannot answer")
        yield
        for task in (warm_up, sweeper):
            task.cancel()
        for task in (warm_up, sweeper):
            with contextlib.suppress(asyncio.CancelledError):
                await task
        await app.state.services.ingestion_queue.aclose()
        await rate_limiter.aclose()
        await app.state.services.llm.aclose()
        await dispose_engines()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
        docs_url="/api/docs" if settings.environment != "production" else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if settings.environment != "production" else None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID", "Retry-After"],
    )
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(MetricsMiddleware)
    register_exception_handlers(app)
    app.include_router(api_router)
    app.include_router(metrics_router)
    return app


app = create_app()
