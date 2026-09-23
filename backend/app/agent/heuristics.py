"""Heuristic (keyword-signal) router.

Used in two ways:
1. as a deterministic safeguard that can correct or down-weight the LLM router;
2. as a complete fallback when the language model is unavailable.
It is deliberately simple and explainable: every decision lists its signals.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.agent.types import Route
from app.sql.hints import ANALYTICS_TERMS, COMPANY_TERMS, DOCUMENT_TERMS, TABLE_KEYWORDS
from app.sql.schema_retriever import keyword_hits

GENERAL_TERMS = [
    "what is a",
    "what is an",
    "what are",
    "explain",
    "define",
    "definition",
    "meaning of",
    "how does",
    "difference between",
    "why is",
    "hello",
    "hi",
    "hey",
    "thanks",
    "thank you",
    "good morning",
    "who are you",
    "write a",
    "translate",
    "মানে কী",
    "ব্যাখ্যা",
    "কী",
    "হ্যালো",
    "ধন্যবাদ",
    "কাকে বলে",
    "mane ki",
    "bujhao",
    "bojhao",
    "dhonnobad",
    "hello",
]
CONJUNCTIONS = [" and ", " also ", " plus ", " এবং ", " আর ", " ও ", " ebong ", " ar ", " sathe "]


@dataclass(frozen=True)
class HeuristicResult:
    route: Route
    confidence: float
    db_score: float
    doc_score: float
    general_score: float
    matched_tables: list[str] = field(default_factory=list)

    def as_signals(self) -> dict[str, object]:
        return {
            "heuristic_route": self.route.value,
            "heuristic_confidence": round(self.confidence, 3),
            "db_score": round(self.db_score, 2),
            "doc_score": round(self.doc_score, 2),
            "general_score": round(self.general_score, 2),
            "matched_tables": self.matched_tables,
        }


def _normalise(text: str) -> str:
    return " " + re.sub(r"\s+", " ", text.lower()) + " "


def classify(text: str) -> HeuristicResult:
    padded = _normalise(text)
    tables = [name for name, terms in TABLE_KEYWORDS.items() if keyword_hits(padded, terms)]
    analytics = keyword_hits(padded, ANALYTICS_TERMS)
    documents = keyword_hits(padded, DOCUMENT_TERMS)
    company = keyword_hits(padded, COMPANY_TERMS)
    general = keyword_hits(padded, GENERAL_TERMS)

    # Business vocabulary only signals SQL strongly when combined with aggregation
    # ("how many returns"); on its own ("can I return a phone?") it is weak, because
    # policy questions mention the same entities.
    if not tables:
        db_score = 0.0
    elif analytics:
        db_score = len(tables) * 0.6 + analytics * 1.0
    else:
        db_score = len(tables) * 0.4
    doc_score = documents * 1.0 + (0.5 if company and documents else 0.0)
    has_conjunction = any(c in padded for c in CONJUNCTIONS)

    if db_score >= 1.5 and doc_score >= 1.0 and (has_conjunction or doc_score >= 2):
        route, confidence = Route.HYBRID, 0.55 + min(0.3, 0.05 * (db_score + doc_score))
    elif db_score > doc_score and db_score >= 1.0:
        route, confidence = Route.SQL, 0.5 + min(0.4, 0.1 * (db_score - doc_score + 1))
    elif doc_score >= 1.0:
        route, confidence = Route.RAG, 0.5 + min(0.4, 0.1 * (doc_score - db_score + 1))
    elif company:
        route, confidence = Route.RAG, 0.45
    else:
        route, confidence = Route.GENERAL, 0.5 + min(0.3, 0.1 * general)
    return HeuristicResult(
        route=route,
        confidence=round(min(confidence, 0.9), 3),
        db_score=db_score,
        doc_score=doc_score,
        general_score=float(general),
        matched_tables=tables,
    )
