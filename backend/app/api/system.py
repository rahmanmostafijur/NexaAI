from __future__ import annotations

import logging

from fastapi import APIRouter
from sqlalchemy import text

from app.api.deps import CurrentUser, ServicesDep, SettingsDep
from app.db.session import session_scope
from app.rag.extractors import SOURCE_TYPES
from app.schemas.system import Health, SystemInfo

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
