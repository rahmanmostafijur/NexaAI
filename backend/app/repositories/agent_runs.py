from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.models import AgentRun


class AgentRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, **fields: Any) -> AgentRun:
        run = AgentRun(**fields)
        self._session.add(run)
        await self._session.flush()
        return run

    async def update(self, run_id: uuid.UUID, **fields: Any) -> None:
        run = await self._session.get(AgentRun, run_id)
        if run is not None:
            for key, value in fields.items():
                setattr(run, key, value)

    async def list(self, *, user_id: uuid.UUID | None, limit: int) -> list[AgentRun]:
        query = select(AgentRun).order_by(AgentRun.created_at.desc()).limit(limit)
        if user_id is not None:
            query = query.where(AgentRun.user_id == user_id)
        return list(await self._session.scalars(query))

    async def get(self, run_id: uuid.UUID, *, user_id: uuid.UUID | None) -> AgentRun:
        query = select(AgentRun).where(AgentRun.id == run_id)
        if user_id is not None:
            query = query.where(AgentRun.user_id == user_id)
        run = await self._session.scalar(query)
        if run is None:
            raise NotFoundError("Agent run not found")
        return run

    async def stats(self, *, user_id: uuid.UUID | None) -> dict[str, Any]:
        base = select(AgentRun).where(AgentRun.status != "running")
        if user_id is not None:
            base = base.where(AgentRun.user_id == user_id)
        runs = base.subquery()

        summary = (
            await self._session.execute(
                select(
                    func.count(runs.c.id),
                    func.count(runs.c.id).filter(runs.c.status == "success"),
                    func.avg(runs.c.total_ms),
                    func.percentile_cont(0.95).within_group(runs.c.total_ms),
                )
            )
        ).one()
        routes = await self._session.execute(
            select(runs.c.route, func.count())
            .where(runs.c.route.is_not(None))
            .group_by(runs.c.route)
        )
        languages = await self._session.execute(
            select(runs.c.language, func.count())
            .where(runs.c.language.is_not(None))
            .group_by(runs.c.language)
        )
        total = int(summary[0] or 0)
        return {
            "total_runs": total,
            "success_rate": round((summary[1] or 0) / total, 4) if total else 0.0,
            "avg_latency_ms": round(float(summary[2] or 0), 1),
            "p95_latency_ms": round(float(summary[3] or 0), 1),
            "routes": {route: int(count) for route, count in routes.all()},
            "languages": {language: int(count) for language, count in languages.all()},
        }
