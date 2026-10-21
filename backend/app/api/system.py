from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.deps import CurrentUser, ServicesDep, SettingsDep
from app.core.readiness import check_database, check_migrations, check_redis
from app.db.session import session_scope
from app.rag.extractors import SOURCE_TYPES
from app.schemas.system import Health, ReadinessChecks, Ready, SystemInfo

router = APIRouter(tags=["system"])
logger = logging.getLogger(__name__)


@router.get("/health", response_model=Health)
async def health(settings: SettingsDep) -> Health:
    database = True
    try:
        async with session_scope() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        logger.warning("Health check: database unreachable")
        database = False
    return Health(
        status="ok" if database else "degraded",
        database=database,
        llm_configured=settings.llm_configured,
    )


@router.get("/ready", response_model=Ready, responses={503: {"model": Ready}})
async def ready(settings: SettingsDep) -> JSONResponse:
    """Readiness: database reachable, schema at the latest migration, Redis if configured."""
    database = await check_database()
    checks = ReadinessChecks(
        database=database,
        # Without a database the migration state is unknowable, which counts as not ready.
        migrations=database and await check_migrations(),
        redis=await check_redis(settings),
    )
    is_ready = checks.database and checks.migrations and checks.redis is not False
    body = Ready(status="ready" if is_ready else "not_ready", checks=checks)
    return JSONResponse(body.model_dump(), status_code=200 if is_ready else 503)


@router.get("/system/info", response_model=SystemInfo)
async def system_info(
    user: CurrentUser, services: ServicesDep, settings: SettingsDep
) -> SystemInfo:
    return SystemInfo(
        app_name=settings.app_name,
        version=settings.app_version,
        llm_provider=services.llm.name,
        llm_model=services.llm.model or "not configured",
        embedding_provider=services.embeddings.name,
        embedding_model=services.embeddings.model,
        max_upload_mb=settings.max_upload_mb,
        allowed_extensions=sorted(SOURCE_TYPES),
    )
