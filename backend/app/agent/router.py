"""Query router: structured LLM classification + deterministic safeguards.

Signals combined:
* LLM classification (intent, route, confidence, standalone rewrite using history)
* heuristic keyword signals (analytics terms, table vocabulary, policy vocabulary)
* document relevance probe (best vector similarity in the knowledge base)
* tool availability (is the knowledge base empty? is the schema loaded?)

If the LLM fails, the heuristic decision is used with a capped confidence, so
the agent degrades gracefully instead of failing outright.
"""

from __future__ import annotations

import logging
import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.agent import heuristics
from app.agent.types import LanguageInfo, Route, RouteDecision
from app.core.errors import LLMUnavailableError
from app.llm.base import LLMProvider
from app.llm.structured import complete_structured
from app.prompts import router as router_prompt
from app.rag.retriever import HybridRetriever

logger = logging.getLogger(__name__)

_STRONG_DOC_MATCH = 0.55
_HEURISTIC_FALLBACK_CAP = 0.7
# db_score below this means business nouns were mentioned without any aggregation words.
_AGGREGATION_SCORE = 1.0
_DOC_MATCH_FOR_POLICY = 0.35
_FOLLOW_UP = re.compile(
    r"(?<![\w])(them|those|these|it|its|that|they|their|same|ওগুলো|সেগুলো|এগুলো|এটার|ওটার|"
    r"egula|ogula|ogulo|egulo|ota|eta|tader)(?![\w])",
    re.IGNORECASE,
)


def _previous_user_message(history: str | None) -> str | None:
    if not history:
        return None
    lines = [line[6:] for line in history.splitlines() if line.startswith("User: ")]
    return lines[-1] if lines else None


class RouterOutput(BaseModel):
    route: Literal["SQL", "RAG", "HYBRID", "GENERAL"]
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(default="", max_length=500)
    standalone_query: str = Field(default="", max_length=1000)
    database_question: str | None = Field(default=None, max_length=1000)
    document_question: str | None = Field(default=None, max_length=1000)
    needs_clarification: bool = False
    clarification_question: str | None = Field(default=None, max_length=500)

    @field_validator("route", mode="before")
    @classmethod
    def _upper(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value


class QueryRouter:
    def __init__(
        self,
        llm: LLMProvider,
        retriever: HybridRetriever,
        *,
        clarify_threshold: float,
    ) -> None:
        self._llm = llm
        self._retriever = retriever
        self._clarify_threshold = clarify_threshold

    async def route(
        self,
        message: str,
        *,
        language: LanguageInfo,
        history: str | None,
        tables: list[str],
        documents: list[str],
    ) -> RouteDecision:
        llm_output: RouterOutput | None = None
        llm_error: str | None = None
        if self._llm.configured:
            try:
                llm_output = await complete_structured(
                    self._llm,
                    router_prompt.build_messages(message, history, tables, documents),
                    RouterOutput,
                    max_tokens=400,
                )
            except LLMUnavailableError as exc:
                llm_error = exc.code
                logger.warning("LLM routing failed (%s); using heuristic router", exc.code)

        standalone = (llm_output.standalone_query if llm_output else "") or message
        signal_text = f"{message} {standalone}"
        previous = _previous_user_message(history)
        if previous and _FOLLOW_UP.search(message):
            # "How many of them were cancelled?" inherits the previous question's subject.
            signal_text = f"{previous} {signal_text}"
        heuristic = heuristics.classify(signal_text)
        doc_relevance = await self._document_relevance(standalone, message) if documents else 0.0
        signals: dict[str, object] = {
            **heuristic.as_signals(),
            "doc_relevance": round(doc_relevance, 3),
            "knowledge_base_documents": len(documents),
            "language": language.code,
        }

        if llm_output is None:
            return self._heuristic_decision(message, heuristic, doc_relevance, signals, llm_error)
        return self._fuse(llm_output, heuristic, doc_relevance, documents, signals)

    async def _document_relevance(self, *queries: str) -> float:
        try:
            chunks = await self._retriever.search(
                queries[0], top_k=1, extra_queries=list(queries[1:])
            )
        except Exception:
            logger.warning("Document relevance probe failed")
            return 0.0
        return max((c.vector_score or 0.0) for c in chunks) if chunks else 0.0

    def _heuristic_decision(
        self,
        message: str,
        heuristic: heuristics.HeuristicResult,
        doc_relevance: float,
        signals: dict[str, object],
        llm_error: str | None,
    ) -> RouteDecision:
        route = heuristic.route
        if route == Route.GENERAL and doc_relevance >= _STRONG_DOC_MATCH:
            route = Route.RAG
        signals["llm_error"] = llm_error
        return RouteDecision(
            route=route,
            confidence=min(heuristic.confidence, _HEURISTIC_FALLBACK_CAP),
            reason="Routed by keyword signals because the language model router was unavailable.",
            standalone_query=message,
            database_question=message if route in (Route.SQL, Route.HYBRID) else None,
            document_question=message if route in (Route.RAG, Route.HYBRID) else None,
            source="heuristic",
            signals=signals,
        )

    def _fuse(
        self,
        output: RouterOutput,
        heuristic: heuristics.HeuristicResult,
        doc_relevance: float,
        documents: list[str],
        signals: dict[str, object],
    ) -> RouteDecision:
        route = Route(output.route)
        confidence = output.confidence
        overrides: list[str] = []

        # Safeguard 1: the LLM called it general knowledge but the wording clearly
        # targets company data (e.g. "our", table vocabulary, policy words).
        if (
            route == Route.GENERAL
            and heuristic.route != Route.GENERAL
            and heuristic.confidence >= 0.6
        ):
            overrides.append(f"company-data signals point to {heuristic.route.value}")
            route = heuristic.route
            confidence = min(confidence, heuristic.confidence)
        # Safeguard 2: general question that strongly matches an internal document.
        elif route == Route.GENERAL and doc_relevance >= _STRONG_DOC_MATCH + 0.1:
            overrides.append("a knowledge-base document closely matches the question")
            route = Route.RAG
            confidence = min(confidence, 0.7)
        # Safeguard 3: the LLM wants the database, but the question has no aggregation
        # intent, a clear rule/entitlement intent, and a matching document
        # ("How long does a refund to bKash take?" mentions refunds but asks for policy).
        elif (
            route in (Route.SQL, Route.HYBRID)
            and heuristic.route == Route.RAG
            and heuristic.db_score < _AGGREGATION_SCORE
            and doc_relevance >= _DOC_MATCH_FOR_POLICY
        ):
            overrides.append("no data aggregation requested and a policy document matches")
            route = Route.RAG
            confidence = min(confidence, heuristic.confidence)
        # Safeguard 4: tool availability — nothing to retrieve from.
        if route == Route.HYBRID and not documents:
            overrides.append("knowledge base is empty, using the database only")
            route = Route.SQL

        if route == heuristic.route:
            confidence = min(0.99, 0.75 * confidence + 0.25)
        elif heuristic.route != Route.GENERAL and heuristic.confidence >= 0.6:
            confidence *= 0.85

        standalone = output.standalone_query or output.database_question or ""
        reason = output.reason or "Classified by the language model."
        if overrides:
            reason = f"{reason} Adjusted: {'; '.join(overrides)}."
        signals["llm_route"] = output.route
        signals["llm_confidence"] = output.confidence

        needs_clarification = (
            output.needs_clarification
            and bool(output.clarification_question)
            and confidence < self._clarify_threshold
        )
        return RouteDecision(
            route=route,
            confidence=round(confidence, 3),
            reason=reason,
            standalone_query=standalone,
            database_question=(output.database_question or standalone)
            if route in (Route.SQL, Route.HYBRID)
            else None,
            document_question=(output.document_question or standalone)
            if route in (Route.RAG, Route.HYBRID)
            else None,
            needs_clarification=needs_clarification,
            clarification_question=output.clarification_question if needs_clarification else None,
            source="llm+safeguard" if overrides else "llm",
            signals=signals,
        )
