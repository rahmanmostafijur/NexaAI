"""Readiness checks: is this instance able to serve traffic right now?

Liveness (`/api/health`) only says the process is up. Readiness additionally requires a
reachable database whose schema is at the latest migration, and Redis when it is configured.
"""

from __future__ import annotations

import logging
from functools import lru_cache

import redis.asyncio as aioredis
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text

from app.core.config import BACKEND_DIR, Settings
from app.db.session import session_scope

logger = logging.getLogger(__name__)

_REDIS_TIMEOUT_SECONDS = 2.0


@lru_cache
def migration_head() -> str | None:
    """The newest revision shipped with this build."""
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    return ScriptDirectory.from_config(config).get_current_head()


async def check_database() -> bool:
    try:
        async with session_scope() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        logger.warning("Readiness: database unreachable")
        return False
    return True


async def check_migrations() -> bool:
    """True when the database is at the head revision this build expects."""
    try:
        async with session_scope() as session:
            current = await session.scalar(text("SELECT version_num FROM alembic_version"))
    except Exception:
        logger.warning("Readiness: could not read the migration version")
        return False
    return current == migration_head()


async def check_redis(settings: Settings) -> bool | None:
    """None when Redis is not configured (nothing to check)."""
    if not settings.redis_url:
        return None
    client = aioredis.from_url(
        settings.redis_url,
        socket_connect_timeout=_REDIS_TIMEOUT_SECONDS,
        socket_timeout=_REDIS_TIMEOUT_SECONDS,
    )
    try:
        await client.ping()
    except (aioredis.RedisError, OSError, TimeoutError):
        logger.warning("Readiness: Redis unreachable")
        return False
    finally:
        await client.aclose()
    return True
