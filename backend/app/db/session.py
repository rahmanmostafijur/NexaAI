"""Database engines and session factories.

Two engines are deliberately kept separate:

* app engine — the application role. Owns app tables (users, conversations,
  documents, agent runs) and is used by repositories.
* read-only pool — a raw asyncpg pool for the `nexa_readonly` role. Used *only* by the Text-to-SQL
  executor. The role has SELECT on the `commerce` schema and nothing else, so
  even SQL that slipped past the validator could not write or read app data.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

_app_engine: AsyncEngine | None = None
_readonly_pool: asyncpg.Pool | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_app_engine() -> AsyncEngine:
    global _app_engine, _session_factory
    if _app_engine is None:
        settings = get_settings()
        _app_engine = create_async_engine(
            settings.database_url, pool_size=10, max_overflow=10, pool_pre_ping=True
        )
        _session_factory = async_sessionmaker(_app_engine, expire_on_commit=False)
    return _app_engine


async def get_readonly_pool() -> asyncpg.Pool:
    global _readonly_pool
    if _readonly_pool is None:
        settings = get_settings()
        dsn = make_url(settings.readonly_database_url).set(drivername="postgresql")
        _readonly_pool = await asyncpg.create_pool(
            dsn.render_as_string(hide_password=False),
            min_size=1,
            max_size=5,
            command_timeout=settings.sql_statement_timeout_ms / 1000 + 5,
            server_settings={"application_name": "nexa-text-to-sql"},
        )
    return _readonly_pool


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    get_app_engine()
    assert _session_factory is not None
    return _session_factory


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Session for work outside a request (background tasks, streaming, scripts)."""
    async with get_session_factory()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request, committed on success."""
    async with session_scope() as session:
        yield session


async def dispose_engines() -> None:
    global _app_engine, _readonly_pool, _session_factory
    if _app_engine is not None:
        await _app_engine.dispose()
    if _readonly_pool is not None:
        await _readonly_pool.close()
    _app_engine = _readonly_pool = _session_factory = None
