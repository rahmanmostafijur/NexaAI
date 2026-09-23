import uuid

import pytest

from app.agent.language import detect_language
from app.agent.router import QueryRouter
from app.agent.types import Route
from app.core.errors import LLMUnavailableError
from app.rag.retriever import RetrievedChunk
from tests.fakes import ScriptedLLM

TABLES = ["orders", "order_items", "products", "customers", "returns"]
DOCUMENTS = ["Return Policy", "Refund Policy"]


class FakeRetriever:
    def __init__(self, similarity: float = 0.0) -> None:
        self.similarity = similarity

    async def search(self, query: str, **_: object) -> list[RetrievedChunk]:
        if not self.similarity:
            return []
        return [
            RetrievedChunk(
                chunk_id=uuid.uuid4(),
                document_id=uuid.uuid4(),
                title="Doc",
                filename="doc.md",
                page=None,
                section=None,
                content="text",
                score=1.0,
                vector_score=self.similarity,
                keyword_score=None,
            )
        ]


def make_router(llm: ScriptedLLM, similarity: float = 0.0) -> QueryRouter:
    return QueryRouter(llm, FakeRetriever(similarity), clarify_threshold=0.4)  # type: ignore[arg-type]


async def route(router: QueryRouter, message: str, documents: list[str] = DOCUMENTS):
    return await router.route(
        message,
        language=detect_language(message),
        history=None,
        tables=TABLES,
        documents=documents,
    )


async def test_llm_and_heuristic_agreement_raises_confidence() -> None:
    llm = ScriptedLLM()
    llm.routes["orders"] = {
        "route": "SQL",
        "confidence": 0.8,
        "reason": "Counts orders.",
        "standalone_query": "How many orders were placed last month?",
        "database_question": "How many orders were placed last month?",
    }
    decision = await route(make_router(llm), "How many orders were placed last month?")
    assert decision.route == Route.SQL
    assert decision.confidence == pytest.approx(0.85)
    assert decision.requires_database and not decision.requires_documents
    assert decision.source == "llm"


async def test_safeguard_overrides_general_for_company_policy() -> None:
    llm = ScriptedLLM()
    llm.routes["refund"] = {
        "route": "GENERAL",
        "confidence": 0.7,
        "reason": "Generic.",
        "standalone_query": "What is our refund policy?",
    }
    decision = await route(make_router(llm), "What is our refund policy?")
    assert decision.route == Route.RAG
    assert decision.source == "llm+safeguard"
    assert "Adjusted" in decision.reason
    assert decision.document_question == "What is our refund policy?"


async def test_strong_document_match_turns_general_into_rag() -> None:
    llm = ScriptedLLM()
    llm.routes["pickup"] = {
        "route": "GENERAL",
        "confidence": 0.6,
        "reason": "x",
        "standalone_query": "Tell me about pickup scanning",
    }
    decision = await route(make_router(llm, similarity=0.8), "Tell me about pickup scanning")
    assert decision.route == Route.RAG
    assert decision.signals["doc_relevance"] == 0.8


async def test_falls_back_to_heuristics_when_llm_fails() -> None:
    llm = ScriptedLLM()
    llm.fail_with = LLMUnavailableError("down")
    decision = await route(make_router(llm), "How many orders were placed last month?")
    assert decision.route == Route.SQL
    assert decision.source == "heuristic"
    assert decision.confidence <= 0.7
    assert decision.signals["llm_error"] == "llm_unavailable"


async def test_hybrid_degrades_to_sql_without_documents() -> None:
    llm = ScriptedLLM()
    llm.routes["returns"] = {
        "route": "HYBRID",
        "confidence": 0.9,
        "reason": "x",
        "standalone_query": "Top returned product and its policy",
    }
    decision = await route(make_router(llm), "Top returns and policy?", documents=[])
    assert decision.route == Route.SQL


async def test_low_confidence_triggers_clarification() -> None:
    llm = ScriptedLLM()
    llm.routes["this"] = {
        "route": "SQL",
        "confidence": 0.2,
        "reason": "Ambiguous.",
        "standalone_query": "this",
        "needs_clarification": True,
        "clarification_question": "Which product do you mean?",
    }
    decision = await route(make_router(llm), "what about this")
    assert decision.needs_clarification
    assert decision.clarification_question == "Which product do you mean?"


async def test_follow_up_questions_inherit_the_previous_subject() -> None:
    """A weak router saying GENERAL for "them" is corrected using conversation context."""
    llm = ScriptedLLM()
    llm.routes["them"] = {
        "route": "GENERAL",
        "confidence": 0.5,
        "reason": "x",
        "standalone_query": "How many of them were there?",
    }
    router = make_router(llm)
    message = "How many of them were there?"
    decision = await router.route(
        message,
        language=detect_language(message),
        tables=TABLES,
        documents=DOCUMENTS,
        history="User: How many orders were placed last month?\nAssistant: 107 orders.",
    )
    assert decision.route == Route.SQL
    assert decision.source == "llm+safeguard"
    without_history = await route(router, message)
    assert without_history.route == Route.GENERAL


async def test_policy_questions_misrouted_to_sql_are_corrected() -> None:
    llm = ScriptedLLM()
    llm.routes["bkash"] = {
        "route": "SQL",
        "confidence": 0.9,
        "reason": "Mentions refunds.",
        "standalone_query": "How long does a refund to bKash take?",
    }
    decision = await route(
        make_router(llm, similarity=0.6), "How long does a refund to bKash take?"
    )
    assert decision.route == Route.RAG
    assert "no data aggregation" in decision.reason
    # Without a matching document there is no evidence the question is about policy.
    unchanged = await route(
        make_router(llm, similarity=0.1), "How long does a refund to bKash take?"
    )
    assert unchanged.route == Route.SQL


async def test_real_aggregation_questions_stay_sql() -> None:
    llm = ScriptedLLM()
    llm.routes["refunds"] = {
        "route": "SQL",
        "confidence": 0.9,
        "reason": "Counts refunds.",
        "standalone_query": "How many refunds happened last month?",
    }
    decision = await route(
        make_router(llm, similarity=0.6), "How many refunds happened last month?"
    )
    assert decision.route == Route.SQL


async def test_router_accepts_lowercase_route_labels() -> None:
    llm = ScriptedLLM()
    llm.routes["index"] = {
        "route": "general",
        "confidence": 0.9,
        "reason": "x",
        "standalone_query": "Explain a database index",
    }
    decision = await route(make_router(llm), "Explain what a database index is.")
    assert decision.route == Route.GENERAL
