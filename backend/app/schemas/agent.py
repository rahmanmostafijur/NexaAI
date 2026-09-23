from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class RunSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID | None
    created_at: datetime
    route: str | None
    language: str | None
    confidence: float | None
    status: str
    total_ms: int | None
    tools_used: list[str]


class RunDetail(RunSummary):
    error_code: str | None
    error_message: str | None
    token_usage: dict[str, int] | None
    trace: list[dict[str, Any]]


class Stats(BaseModel):
    total_runs: int
    success_rate: float
    avg_latency_ms: float
    p95_latency_ms: float
    routes: dict[str, int]
    languages: dict[str, int]
