import asyncio

import pytest

from app.agent.executor import ToolExecutor, resolve_query
from app.agent.language import detect_language
from app.agent.planner import Planner
from app.agent.tools.base import BaseTool, ToolContext, ToolRegistry, ToolResult
from app.agent.tools.sql_tool import entity_text
from app.agent.trace import Trace
from app.agent.types import AgentEvent, Plan, PlanStep, Route, RouteDecision
from app.core.errors import AppError, LLMUnavailableError
from app.sql.executor import QueryResult
from app.sql.service import SQLRunResult
from tests.fakes import ScriptedLLM

CONTEXT = ToolContext(language=detect_language("hello"), original_message="hello")


def test_resolve_query_substitutes_dependencies() -> None:
    results = {"s1": ToolResult("completed", "ok", entity_text="Electronics")}
    step = PlanStep("s2", "rag", "warranty policy for {s1} products", "d", depends_on=["s1"])
    assert resolve_query(step, results) == "warranty policy for Electronics products"
    step = PlanStep("s2", "rag", "return policy", "d", depends_on=["s1"])
    assert resolve_query(step, results) == "return policy (Electronics)"
    step = PlanStep("s2", "rag", "policy for {s1}", "d", depends_on=["s1"])
    assert resolve_query(step, {"s1": ToolResult("failed", "x")}) == "policy for"


class _GateTool(BaseTool):
    stage = "querying_database"
    stage_label = "Working..."

    def __init__(self, name: str, started: dict[str, asyncio.Event], peer: str | None) -> None:
        self.name = name  # type: ignore[misc]
        self._started = started
        self._peer = peer
        self.queries: list[str] = []

    async def run(self, query: str, context: ToolContext) -> ToolResult:
        self.queries.append(query)
        self._started[self.name].set()
        if self._peer:  # proves concurrency: waits until the peer has also started
            await asyncio.wait_for(self._started[self._peer].wait(), timeout=1)
        return ToolResult("completed", f"{self.name} done", entity_text=f"{self.name}-entity")


async def test_independent_steps_run_in_parallel_and_dependents_wait() -> None:
    started = {"a": asyncio.Event(), "b": asyncio.Event(), "c": asyncio.Event()}
    tools = {
        "a": _GateTool("a", started, "b"),
        "b": _GateTool("b", started, "a"),
        "c": _GateTool("c", started, None),
    }
    registry = ToolRegistry()
    for tool in tools.values():
        registry.register(tool)
    plan = Plan(
        [
            PlanStep("s1", "a", "first", "d"),  # type: ignore[arg-type]
            PlanStep("s2", "b", "second", "d"),  # type: ignore[arg-type]
            PlanStep("s3", "c", "use {s1}", "d", depends_on=["s1", "s2"]),  # type: ignore[arg-type]
        ]
    )
    events: list[AgentEvent] = []

    async def emit(event: AgentEvent) -> None:
        events.append(event)

    results = await ToolExecutor(registry).execute(plan, CONTEXT, emit, Trace())
    assert set(results) == {"s1", "s2", "s3"}
    assert tools["c"].queries == ["use a-entity (b-entity)"]
    assert [s.status for s in plan.steps] == ["completed"] * 3
    step_events = [e.data for e in events if e.type == "step" and e.data["status"] == "completed"]
    assert step_events[-1]["id"] == "s3"


class _FailingTool(BaseTool):
    name = "sql"
    stage = "querying_database"
    stage_label = "x"

    def __init__(self, error: Exception) -> None:
        self.error = error

    async def run(self, query: str, context: ToolContext) -> ToolResult:
        raise self.error


async def _run_single(error: Exception) -> tuple[Plan, dict]:
    registry = ToolRegistry()
    registry.register(_FailingTool(error))
    plan = Plan([PlanStep("s1", "sql", "q", "d")])

    async def emit(_: AgentEvent) -> None:
        return None

    return plan, await ToolExecutor(registry).execute(plan, CONTEXT, emit, Trace())


async def test_tool_errors_become_failed_steps() -> None:
    plan, results = await _run_single(AppError("database hiccup"))
    assert results["s1"].status == "failed"
    assert plan.steps[0].status == "failed"


async def test_llm_outage_propagates() -> None:
    with pytest.raises(LLMUnavailableError):
        await _run_single(LLMUnavailableError("down"))


def _decision(route: Route) -> RouteDecision:
    return RouteDecision(
        route=route,
        confidence=0.9,
        reason="r",
        standalone_query="question",
        database_question="data question",
        document_question="doc question",
    )


async def test_single_source_routes_get_deterministic_plans() -> None:
    planner = Planner(ScriptedLLM())
    sql_plan = await planner.plan(_decision(Route.SQL))
    assert [(s.tool, s.query) for s in sql_plan.steps] == [("sql", "data question")]
    rag_plan = await planner.plan(_decision(Route.RAG))
    assert [(s.tool, s.query) for s in rag_plan.steps] == [("rag", "doc question")]
    assert (await planner.plan(_decision(Route.GENERAL))).steps[0].tool == "general"


async def test_hybrid_plan_from_llm_is_validated() -> None:
    llm = ScriptedLLM()
    plan = await Planner(llm).plan(_decision(Route.HYBRID))
    assert plan.source == "llm"
    assert [s.tool for s in plan.steps] == ["sql", "rag"]
    assert plan.steps[1].depends_on == ["s1"]


@pytest.mark.parametrize(
    "bad_plan",
    [
        {"steps": [{"id": "s1", "tool": "sql", "query": "only data", "depends_on": []}]},
        {
            "steps": [
                {"id": "s1", "tool": "rag", "query": "docs", "depends_on": ["s2"]},
                {"id": "s2", "tool": "sql", "query": "data", "depends_on": []},
            ]
        },
        {"steps": [{"id": "s1", "tool": "shell", "query": "rm -rf /", "depends_on": []}]},
    ],
)
async def test_invalid_hybrid_plans_fall_back(bad_plan: dict) -> None:
    llm = ScriptedLLM()
    llm.plan = bad_plan
    plan = await Planner(llm).plan(_decision(Route.HYBRID))
    assert plan.source == "fallback"
    assert [(s.tool, s.depends_on) for s in plan.steps] == [("sql", []), ("rag", ["s1"])]


def test_entity_text_takes_labels_from_top_rows() -> None:
    run = SQLRunResult(
        sql="SELECT ...",
        result=QueryResult(
            ["category", "revenue", "month"],
            [["Electronics", 1200.5, "2026-08-01"], ["Books", 90, "2026-08-01"]],
            2,
            False,
            3,
        ),
        tables=["orders"],
        explanation="",
    )
    assert entity_text(run) == "Electronics, Books"
