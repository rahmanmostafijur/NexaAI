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
from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.core.security import hash_password
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
        warm_up = asyncio.create_task(_warm_up(app.state.services.embeddings))
        if not settings.llm_configured:
            logger.warning("No LLM configured: chat will use heuristic routing and cannot answer")
        yield
        warm_up.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await warm_up
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
    register_exception_handlers(app)
    app.include_router(api_router)
    return app


app = create_app()
