"""Observability endpoints. Users see their own runs; admins see everyone's."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbDep
from app.models import User
from app.repositories.agent_runs import AgentRunRepository
from app.schemas.agent import RunDetail, RunSummary, Stats

router = APIRouter(prefix="/agent", tags=["agent"])


def _scope(user: User) -> uuid.UUID | None:
    return None if user.role == "admin" else user.id


@router.get("/runs", response_model=list[RunSummary])
async def list_runs(
    user: CurrentUser, session: DbDep, limit: Annotated[int, Query(ge=1, le=200)] = 50
) -> list[RunSummary]:
    runs = await AgentRunRepository(session).list(user_id=_scope(user), limit=limit)
    return [RunSummary.model_validate(run) for run in runs]


@router.get("/runs/{run_id}", response_model=RunDetail)
async def get_run(run_id: uuid.UUID, user: CurrentUser, session: DbDep) -> RunDetail:
    run = await AgentRunRepository(session).get(run_id, user_id=_scope(user))
    return RunDetail.model_validate(run)


@router.get("/stats", response_model=Stats)
async def stats(user: CurrentUser, session: DbDep) -> Stats:
    return Stats(**await AgentRunRepository(session).stats(user_id=_scope(user)))
