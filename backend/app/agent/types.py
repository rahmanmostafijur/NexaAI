"""Core agent data types shared by the router, planner, executor and orchestrator."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal

StepStatus = Literal["pending", "running", "completed", "failed", "skipped"]
ToolName = Literal["sql", "rag", "general"]


class Route(StrEnum):
    SQL = "SQL"
    RAG = "RAG"
    HYBRID = "HYBRID"
    GENERAL = "GENERAL"


@dataclass(frozen=True)
class LanguageInfo:
    code: Literal["en", "bn", "banglish", "mixed"]
    label: str
    bengali_ratio: float

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "label": self.label}


@dataclass
class RouteDecision:
    route: Route
    confidence: float
    reason: str
    standalone_query: str
    database_question: str | None = None
    document_question: str | None = None
    needs_clarification: bool = False
    clarification_question: str | None = None
    source: Literal["llm", "heuristic", "llm+safeguard"] = "llm"
    signals: dict[str, Any] = field(default_factory=dict)

    @property
    def requires_database(self) -> bool:
        return self.route in (Route.SQL, Route.HYBRID)

    @property
    def requires_documents(self) -> bool:
        return self.route in (Route.RAG, Route.HYBRID)

    def as_event(self, language: LanguageInfo) -> dict[str, Any]:
        return {
            "language": language.as_dict(),
            "route": self.route.value,
            "confidence": round(self.confidence, 3),
            "reason": self.reason,
            "requires_database": self.requires_database,
            "requires_documents": self.requires_documents,
            "standalone_query": self.standalone_query,
        }


@dataclass
class PlanStep:
    id: str
    tool: ToolName
    query: str
    description: str
    depends_on: list[str] = field(default_factory=list)
    status: StepStatus = "pending"
    summary: str | None = None
    duration_ms: int | None = None

    def as_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "tool": self.tool,
            "description": self.description,
            "status": self.status,
        }
        if self.summary is not None:
            data["summary"] = self.summary
        if self.duration_ms is not None:
            data["duration_ms"] = self.duration_ms
        return data


@dataclass
class Plan:
    steps: list[PlanStep]
    source: Literal["deterministic", "llm", "fallback"] = "deterministic"

    def as_event(self) -> dict[str, Any]:
        return {"steps": [step.as_dict() for step in self.steps]}


@dataclass(frozen=True)
class AgentEvent:
    """One server-sent event: `type` is the SSE event name, `data` its JSON payload."""

    type: str
    data: dict[str, Any]
