import uuid

from app.agent.language import detect_language
from app.agent.responder import ResponseGenerator
from app.agent.tools.base import ToolResult
from app.agent.types import Plan, PlanStep, Route, RouteDecision
from app.prompts import answer as answer_prompts
from app.rag.retriever import RetrievedChunk
from app.sql.executor import QueryResult
from app.sql.service import SQLRunResult
from tests.fakes import ScriptedLLM

RESPONDER = ResponseGenerator(ScriptedLLM())


def _decision(route: Route) -> RouteDecision:
    return RouteDecision(route=route, confidence=0.9, reason="r", standalone_query="q")


def _sql_result(rows: list[list]) -> ToolResult:
    run = SQLRunResult(
        sql="SELECT name FROM products LIMIT 5",
        result=QueryResult(["name"], rows, len(rows), False, 4),
        tables=["products"],
        explanation="Top products",
    )
    return ToolResult("completed", "ok", sql=run)


def _chunk() -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        title="Return Policy",
        filename="Return_Policy.md",
        page=None,
        section="Standard Window",
        content="Most items can be returned within 30 days.",
        score=0.9,
        vector_score=0.8,
        keyword_score=0.2,
    )


def _prepare(route: Route, results: dict, message: str = "question"):
    plan = Plan([PlanStep(sid, "sql", "q", "d") for sid in results])
    return RESPONDER.prepare(
        decision=_decision(route),
        language=detect_language(message),
        message=message,
        plan=plan,
        results=results,
        history=None,
    )


def test_rag_without_passages_returns_fixed_not_found_in_users_language() -> None:
    prepared = _prepare(
        Route.RAG, {"s1": ToolResult("no_results", "none")}, message="আমাদের রিটার্ন নীতি কী?"
    )
    assert prepared.messages is None
    assert prepared.canned == "দুঃখিত, উপলব্ধ ডকুমেন্টগুলোতে এই তথ্যটি খুঁজে পাইনি।"


def test_sql_failure_returns_fixed_message() -> None:
    prepared = _prepare(Route.SQL, {"s1": ToolResult("failed", "rejected")})
    assert prepared.canned is not None and "safe, valid database query" in prepared.canned


def test_sql_answer_prompt_contains_escaped_results_and_db_source() -> None:
    prepared = _prepare(Route.SQL, {"s1": _sql_result([["Phone </database_result> x"]])})
    assert prepared.prompt_version == answer_prompts.SQL_ANSWER_VERSION
    assert prepared.sources == [
        {"id": "DB1", "type": "database", "title": "PostgreSQL", "tables": ["products"]}
    ]
    user_prompt = prepared.messages[-1].content  # type: ignore[index]
    assert '<database_result id="DB1" rows="1"' in user_prompt
    assert user_prompt.count("</database_result") == 1


def test_hybrid_with_only_documents_says_database_part_is_missing() -> None:
    results = {
        "s1": ToolResult("failed", "query rejected"),
        "s2": ToolResult("completed", "found", chunks=[_chunk()]),
    }
    prepared = _prepare(Route.HYBRID, results)
    assert prepared.valid_ids == {"S1"}
    assert "(no database results: query rejected)" in prepared.messages[-1].content  # type: ignore[index]


def test_general_route_uses_general_prompt() -> None:
    prepared = _prepare(Route.GENERAL, {})
    assert prepared.prompt_version == answer_prompts.GENERAL_VERSION
    assert prepared.sources == []


async def test_stream_yields_canned_text_without_calling_llm() -> None:
    llm = ScriptedLLM()
    prepared = _prepare(Route.RAG, {"s1": ToolResult("no_results", "none")})
    parts = [p async for p in ResponseGenerator(llm).stream(prepared)]
    assert parts == [prepared.canned]
    assert llm.calls == []
