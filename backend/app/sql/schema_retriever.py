"""Selects the few tables relevant to a question instead of sending the whole schema.

Scoring combines two signals:
1. Keyword hits from a multilingual vocabulary (`hints.TABLE_KEYWORDS`).
2. Embedding similarity between the question and each table's description card.

Selected tables are then expanded with the tables needed to *join* them
(shortest foreign-key path), e.g. `customers` + `products` pulls in `orders`
and `order_items`.
"""

from __future__ import annotations

import asyncio
import math
import re
from collections import deque
from dataclasses import dataclass

from app.embeddings.base import EmbeddingProvider
from app.sql.catalog import SchemaSnapshot
from app.sql.hints import TABLE_KEYWORDS

_DEFAULT_TABLES = ["orders", "order_items", "products", "customers"]
_MAX_TABLES = 7
_MIN_EMBEDDING_SIMILARITY = 0.25


@dataclass(frozen=True)
class TableScore:
    table: str
    score: float
    keyword_hits: int
    similarity: float


def keyword_hits(text: str, terms: list[str]) -> int:
    """Count terms present in text. ASCII terms match on word boundaries."""
    lowered = text.lower()
    hits = 0
    for term in terms:
        if term.isascii():
            if re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", lowered):
                hits += 1
        elif term in lowered:
            hits += 1
    return hits


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


class SchemaRetriever:
    def __init__(self, embeddings: EmbeddingProvider) -> None:
        self._embeddings = embeddings
        self._card_vectors: dict[str, list[float]] = {}
        self._lock = asyncio.Lock()

    async def _ensure_cards(self, snapshot: SchemaSnapshot) -> None:
        missing = [name for name in snapshot.tables if name not in self._card_vectors]
        if not missing:
            return
        async with self._lock:
            missing = [name for name in snapshot.tables if name not in self._card_vectors]
            if missing:
                cards = [snapshot.tables[name].card() for name in missing]
                vectors = await self._embeddings.embed_documents(cards)
                self._card_vectors.update(zip(missing, vectors, strict=True))

    async def score_tables(self, question: str, snapshot: SchemaSnapshot) -> list[TableScore]:
        similarities: dict[str, float] = {}
        try:
            await self._ensure_cards(snapshot)
            query_vector = await self._embeddings.embed_query(question)
            similarities = {
                name: _cosine(query_vector, self._card_vectors[name])
                for name in snapshot.tables
                if name in self._card_vectors
            }
        except Exception:
            similarities = {}

        scores = []
        for name in snapshot.tables:
            hits = keyword_hits(question, TABLE_KEYWORDS.get(name, [name]))
            similarity = similarities.get(name, 0.0)
            score = hits * 1.0 + max(0.0, similarity - _MIN_EMBEDDING_SIMILARITY) * 4
            scores.append(TableScore(name, round(score, 4), hits, round(similarity, 4)))
        return sorted(scores, key=lambda s: s.score, reverse=True)

    async def select_tables(self, question: str, snapshot: SchemaSnapshot) -> list[str]:
        scores = await self.score_tables(question, snapshot)
        chosen = [s.table for s in scores if s.keyword_hits > 0][:4]
        if not chosen:
            chosen = [s.table for s in scores[:3] if s.similarity >= _MIN_EMBEDDING_SIMILARITY]
        if not chosen:
            chosen = [t for t in _DEFAULT_TABLES if t in snapshot.tables]
        return expand_join_path(chosen, snapshot)


def expand_join_path(tables: list[str], snapshot: SchemaSnapshot) -> list[str]:
    """Add intermediate tables so every selected table can be joined to the first one."""
    graph = snapshot.related_tables()
    result = list(dict.fromkeys(t for t in tables if t in graph))
    if not result:
        return result
    anchor = result[0]
    for target in list(result[1:]):
        for node in _shortest_path(graph, anchor, target):
            if node not in result:
                result.append(node)
    # A product question usually needs the category name, and categories is tiny.
    if "products" in result and "categories" in graph and "categories" not in result:
        result.append("categories")
    return result[:_MAX_TABLES]


def _shortest_path(graph: dict[str, set[str]], start: str, goal: str) -> list[str]:
    if start == goal:
        return [start]
    previous: dict[str, str | None] = {start: None}
    queue: deque[str] = deque([start])
    while queue:
        node = queue.popleft()
        for neighbour in sorted(graph.get(node, ())):
            if neighbour in previous:
                continue
            previous[neighbour] = node
            if neighbour == goal:
                path = [goal]
                while previous[path[-1]] is not None:
                    path.append(previous[path[-1]])  # type: ignore[arg-type]
                return list(reversed(path))
            queue.append(neighbour)
    return []
