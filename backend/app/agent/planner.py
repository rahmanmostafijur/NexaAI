"""Query planner.

Single-source routes get a deterministic one-step plan (no extra LLM call).
HYBRID questions are decomposed by the LLM into ordered tool steps with
dependencies; the plan is validated (known tools, acyclic, bounded length)
and a deterministic two-step plan is used if planning fails.
"""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, Field

from app.agent.types import Plan, PlanStep, Route, RouteDecision
from app.core.errors import LLMUnavailableError
from app.llm.base import LLMProvider
from app.llm.structured import complete_structured
from app.prompts import planner as planner_prompt

logger = logging.getLogger(__name__)

_MAX_STEPS = 4
_DESCRIPTIONS = {
    "sql": "Query the business database",
    "rag": "Search the knowledge base",
    "general": "Answer from general knowledge",
}


class _PlannedStep(BaseModel):
    id: str = Field(pattern=r"^s[1-9]$")
    tool: Literal["sql", "rag"]
    query: str = Field(min_length=3, max_length=500)
    depends_on: list[str] = Field(default_factory=list)
    purpose: str = Field(default="", max_length=120)


class _PlannerOutput(BaseModel):
    steps: list[_PlannedStep] = Field(min_length=1, max_length=_MAX_STEPS)


class Planner:
    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm

    async def plan(self, decision: RouteDecision) -> Plan:
        query = decision.standalone_query
        match decision.route:
            case Route.SQL:
                return Plan([_step("s1", "sql", decision.database_question or query)])
            case Route.RAG:
                return Plan([_step("s1", "rag", decision.document_question or query)])
            case Route.GENERAL:
                return Plan([_step("s1", "general", query)])
        return await self._plan_hybrid(decision)

    async def _plan_hybrid(self, decision: RouteDecision) -> Plan:
        if self._llm.configured:
            try:
                output = await complete_structured(
                    self._llm,
                    planner_prompt.build_messages(decision.standalone_query),
                    _PlannerOutput,
                    max_tokens=500,
                )
                steps = _validate(output)
                if steps:
                    return Plan(steps, source="llm")
            except LLMUnavailableError:
                logger.warning("Hybrid planner failed; using the fallback plan")
        return Plan(
            [
                _step("s1", "sql", decision.database_question or decision.standalone_query),
                _step(
                    "s2",
                    "rag",
                    decision.document_question or decision.standalone_query,
                    depends_on=["s1"],
                ),
            ],
            source="fallback",
        )


def _step(step_id: str, tool: Literal["sql", "rag", "general"], query: str, **kwargs) -> PlanStep:
    return PlanStep(id=step_id, tool=tool, query=query, description=_DESCRIPTIONS[tool], **kwargs)


def _validate(output: _PlannerOutput) -> list[PlanStep] | None:
    """Reject plans with duplicate ids, forward/unknown dependencies or a single tool type."""
    seen: set[str] = set()
    steps: list[PlanStep] = []
    for planned in output.steps:
        if planned.id in seen or any(dep not in seen for dep in planned.depends_on):
            return None
        seen.add(planned.id)
        steps.append(
            PlanStep(
                id=planned.id,
                tool=planned.tool,
                query=planned.query,
                description=planned.purpose or _DESCRIPTIONS[planned.tool],
                depends_on=list(dict.fromkeys(planned.depends_on)),
            )
        )
    tools = {step.tool for step in steps}
    return steps if {"sql", "rag"} <= tools else None
