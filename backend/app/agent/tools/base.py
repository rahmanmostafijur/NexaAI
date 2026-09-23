"""Tool interface and registry.

A tool turns a natural-language sub-question into *evidence* (rows, passages...).
Tools never write the final answer; the ResponseGenerator does, from the
evidence of all tools. Adding a capability (e.g. a web search or a calculator)
means: subclass BaseTool, register it in AgentServices, and let the planner
emit steps with its name.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import ClassVar, Literal

from app.agent.types import LanguageInfo
from app.rag.retriever import RetrievedChunk
from app.sql.service import SQLRunResult

ToolStatus = Literal["completed", "no_results", "failed"]


@dataclass(frozen=True)
class ToolContext:
    language: LanguageInfo
    original_message: str
    history: str | None = None


@dataclass
class ToolResult:
    status: ToolStatus
    summary: str
    sql: SQLRunResult | None = None
    chunks: list[RetrievedChunk] = field(default_factory=list)
    error_code: str | None = None
    # Compact text other steps can depend on, e.g. the top category name.
    entity_text: str | None = None


class BaseTool(ABC):
    name: ClassVar[str]
    stage: ClassVar[str]
    stage_label: ClassVar[str]

    @abstractmethod
    async def run(self, query: str, context: ToolContext) -> ToolResult:
        """Gather evidence for `query`. Expected failures return status='failed'."""


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"Tool '{name}' is not registered") from exc

    def names(self) -> list[str]:
        return sorted(self._tools)
