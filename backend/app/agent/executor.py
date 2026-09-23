"""Tool executor: runs plan steps in dependency order, independent steps in parallel."""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Awaitable, Callable

from app.agent.tools.base import ToolContext, ToolRegistry, ToolResult
from app.agent.trace import Trace
from app.agent.types import AgentEvent, Plan, PlanStep
from app.core.errors import AppError, LLMUnavailableError

Emit = Callable[[AgentEvent], Awaitable[None]]

_PLACEHOLDER = re.compile(r"\{s\d+\}")
_MAX_SQL_ROWS_IN_EVENT = 50


def resolve_query(step: PlanStep, results: dict[str, ToolResult]) -> str:
    """Insert dependency results into the step query (e.g. "{s1}" -> "Electronics")."""
    query = step.query
    for dependency in step.depends_on:
        result = results.get(dependency)
        entity = (result.entity_text if result else None) or ""
        placeholder = "{" + dependency + "}"
        if placeholder in query:
            query = query.replace(placeholder, entity)
        elif entity:
            query = f"{query} ({entity})"
    return " ".join(_PLACEHOLDER.sub("", query).split())


class ToolExecutor:
    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    async def execute(
        self, plan: Plan, context: ToolContext, emit: Emit, trace: Trace
    ) -> dict[str, ToolResult]:
        results: dict[str, ToolResult] = {}
        remaining = list(plan.steps)
        while remaining:
            ready = [s for s in remaining if all(d in results for d in s.depends_on)]
            if not ready:  # unresolvable dependencies (should not happen after validation)
                for step in remaining:
                    step.status = "skipped"
                    await emit(AgentEvent("step", {"id": step.id, "status": "skipped"}))
                break
            await asyncio.gather(
                *(self._run_step(step, context, results, emit, trace) for step in ready)
            )
            remaining = [s for s in remaining if s not in ready]
        return results

    async def _run_step(
        self,
        step: PlanStep,
        context: ToolContext,
        results: dict[str, ToolResult],
        emit: Emit,
        trace: Trace,
    ) -> None:
        tool = self._registry.get(step.tool)
        query = resolve_query(step, results)
        await emit(AgentEvent("status", {"stage": tool.stage, "label": tool.stage_label}))
        step.status = "running"
        await emit(AgentEvent("step", {"id": step.id, "status": "running"}))

        started = time.perf_counter()
        try:
            result = await tool.run(query, context)
        except LLMUnavailableError:
            step.status = "failed"
            step.duration_ms = int((time.perf_counter() - started) * 1000)
            await emit(AgentEvent("step", step.as_dict()))
            trace.add(f"{tool.name}_tool", step.duration_ms, "error", "language model unavailable")
            raise
        except AppError as exc:
            result = ToolResult("failed", exc.message, error_code=exc.code)

        step.duration_ms = int((time.perf_counter() - started) * 1000)
        step.status = "failed" if result.status == "failed" else "completed"
        step.summary = result.summary
        results[step.id] = result
        trace.add(f"{tool.name}_tool", step.duration_ms, result.status, result.summary)

        if result.sql is not None:
            await emit(AgentEvent("sql", sql_event(step.id, result)))
        await emit(AgentEvent("step", step.as_dict()))


def sql_event(step_id: str, result: ToolResult) -> dict[str, object]:
    assert result.sql is not None
    run = result.sql
    return {
        "step_id": step_id,
        "sql": run.sql,
        "columns": run.result.columns,
        "rows": run.result.rows[:_MAX_SQL_ROWS_IN_EVENT],
        "row_count": run.result.row_count,
        "truncated": run.result.truncated or run.result.row_count > _MAX_SQL_ROWS_IN_EVENT,
        "attempts": len(run.attempts),
    }
