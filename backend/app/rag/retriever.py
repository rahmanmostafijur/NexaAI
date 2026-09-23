"""Hybrid retrieval: pgvector similarity + PostgreSQL full-text, fused with RRF.

1. Vector search (cosine, HNSW index) finds semantically similar chunks,
   including cross-lingual matches (Bengali question, English policy).
2. Keyword search (`simple` tsvector, OR-query) catches exact terms such as
   "bKash", "EMI" or policy names that embeddings can blur.
3. Reciprocal Rank Fusion merges the ranked lists from every query variant.
4. A relevance threshold removes chunks that are merely "the nearest" but not
   actually related, so off-topic questions retrieve nothing.
5. An optional LLM reranker can reorder and prune the survivors.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, replace

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.embeddings.base import EmbeddingProvider
from app.llm.base import ChatMessage, LLMProvider
from app.llm.structured import complete_structured
from app.models import Document, DocumentChunk
from app.prompts import rag as rag_prompts

logger = logging.getLogger(__name__)

_CANDIDATES_PER_LIST = 20
_RRF_K = 60
_WORD = re.compile(r"[0-9A-Za-zঀ-৿]+")
_STOPWORDS = {
    "the",
    "a",
    "an",
    "is",
    "are",
    "was",
    "were",
    "what",
    "which",
    "who",
    "how",
    "our",
    "your",
    "for",
    "and",
    "or",
    "of",
    "to",
    "in",
    "on",
    "at",
    "do",
    "does",
    "can",
    "i",
    "we",
    "me",
    "about",
    "with",
    "this",
    "that",
    "it",
    "be",
    "tell",
    "please",
    "according",
    "say",
    "says",
    "কী",
    "কি",
    "কত",
    "এর",
    "এই",
    "আমাদের",
    "আমার",
    "হয়",
    "করে",
    "ki",
    "koto",
    "er",
    "amader",
}


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    title: str
    filename: str
    page: int | None
    section: str | None
    content: str
    score: float
    vector_score: float | None
    keyword_score: float | None
    suspicious: bool = False


def build_keyword_query(text: str) -> str | None:
    """OR-combined tsquery of meaningful tokens, safe from tsquery syntax injection."""
    tokens = [t.lower() for t in _WORD.findall(text)]
    terms = list(dict.fromkeys(t for t in tokens if len(t) > 2 and t not in _STOPWORDS))[:16]
    return " | ".join(terms) if terms else None


class HybridRetriever:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        embeddings: EmbeddingProvider,
        *,
        min_similarity: float,
        reranker: LLMReranker | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._embeddings = embeddings
        self._min_similarity = min_similarity
        self._reranker = reranker

    async def search(
        self,
        query: str,
        *,
        top_k: int,
        extra_queries: list[str] | None = None,
        document_ids: list[uuid.UUID] | None = None,
    ) -> list[RetrievedChunk]:
        queries = list(dict.fromkeys(q.strip() for q in [query, *(extra_queries or [])] if q))
        vectors = await self._embeddings.embed_documents(queries) if queries else []
        fused: dict[uuid.UUID, float] = {}
        chunks: dict[uuid.UUID, RetrievedChunk] = {}

        async with self._session_factory() as session:
            for text, vector in zip(queries, vectors, strict=True):
                for rank, chunk in enumerate(
                    await self._vector_search(session, vector, document_ids)
                ):
                    fused[chunk.chunk_id] = fused.get(chunk.chunk_id, 0.0) + 1 / (_RRF_K + rank + 1)
                    chunks[chunk.chunk_id] = _merge(chunks.get(chunk.chunk_id), chunk)
                keyword_query = build_keyword_query(text)
                if keyword_query:
                    results = await self._keyword_search(session, keyword_query, document_ids)
                    for rank, chunk in enumerate(results):
                        fused[chunk.chunk_id] = fused.get(chunk.chunk_id, 0.0) + 1 / (
                            _RRF_K + rank + 1
                        )
                        chunks[chunk.chunk_id] = _merge(chunks.get(chunk.chunk_id), chunk)
            missing_vectors = [cid for cid, c in chunks.items() if c.vector_score is None]
            if missing_vectors and vectors:
                similarities = await self._similarities(session, vectors[0], missing_vectors)
                for cid, similarity in similarities.items():
                    chunks[cid] = replace(chunks[cid], vector_score=similarity)

        max_fused = 2 * len(queries) / (_RRF_K + 1) or 1.0
        relevant = [
            replace(chunks[cid], score=min(1.0, fused[cid] / max_fused))
            for cid in fused
            if self._is_relevant(chunks[cid])
        ]
        relevant.sort(key=lambda c: c.score, reverse=True)
        candidates = relevant[: max(top_k * 2, top_k)]
        if self._reranker is not None and candidates:
            candidates = await self._reranker.rerank(query, candidates)
        return candidates[:top_k]

    def _is_relevant(self, chunk: RetrievedChunk) -> bool:
        similarity = chunk.vector_score or 0.0
        if similarity >= self._min_similarity:
            return True
        # Strong exact-term matches may pass with a slightly lower similarity.
        return chunk.keyword_score is not None and similarity >= self._min_similarity * 0.75

    def _base_query(self, document_ids: list[uuid.UUID] | None):
        query = (
            select(DocumentChunk, Document.title, Document.filename)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(Document.status == "indexed")
        )
        if document_ids:
            query = query.where(DocumentChunk.document_id.in_(document_ids))
        return query

    async def _vector_search(
        self, session: AsyncSession, vector: list[float], document_ids: list[uuid.UUID] | None
    ) -> list[RetrievedChunk]:
        distance = DocumentChunk.embedding.cosine_distance(vector)
        query = (
            self._base_query(document_ids)
            .add_columns(distance.label("distance"))
            .order_by(distance)
            .limit(_CANDIDATES_PER_LIST)
        )
        rows = (await session.execute(query)).all()
        return [
            _to_chunk(row[0], row[1], row[2], vector_score=round(1 - float(row[3]), 4))
            for row in rows
        ]

    async def _keyword_search(
        self, session: AsyncSession, keyword_query: str, document_ids: list[uuid.UUID] | None
    ) -> list[RetrievedChunk]:
        tsquery = func.to_tsquery("simple", keyword_query)
        rank = func.ts_rank_cd(DocumentChunk.search_vector, tsquery)
        query = (
            self._base_query(document_ids)
            .add_columns(rank.label("rank"))
            .where(DocumentChunk.search_vector.op("@@")(tsquery))
            .order_by(rank.desc())
            .limit(_CANDIDATES_PER_LIST)
        )
        rows = (await session.execute(query)).all()
        return [
            _to_chunk(row[0], row[1], row[2], keyword_score=round(float(row[3]), 4)) for row in rows
        ]

    async def _similarities(
        self, session: AsyncSession, vector: list[float], chunk_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, float]:
        distance = DocumentChunk.embedding.cosine_distance(vector)
        rows = (
            await session.execute(
                select(DocumentChunk.id, distance).where(DocumentChunk.id.in_(chunk_ids))
            )
        ).all()
        return {row[0]: round(1 - float(row[1]), 4) for row in rows}


def _to_chunk(
    chunk: DocumentChunk,
    title: str,
    filename: str,
    *,
    vector_score: float | None = None,
    keyword_score: float | None = None,
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk.id,
        document_id=chunk.document_id,
        title=title,
        filename=filename,
        page=chunk.page,
        section=chunk.section,
        content=chunk.content,
        score=0.0,
        vector_score=vector_score,
        keyword_score=keyword_score,
        suspicious=bool((chunk.meta or {}).get("suspicious")),
    )


def _merge(existing: RetrievedChunk | None, new: RetrievedChunk) -> RetrievedChunk:
    if existing is None:
        return new
    return replace(
        existing,
        vector_score=_max(existing.vector_score, new.vector_score),
        keyword_score=_max(existing.keyword_score, new.keyword_score),
    )


def _max(a: float | None, b: float | None) -> float | None:
    if a is None:
        return b
    return a if b is None else max(a, b)


class _RerankScore(BaseModel):
    id: int
    score: float = Field(ge=0, le=10)


class _RerankResult(BaseModel):
    scores: list[_RerankScore]


class LLMReranker:
    """Optional second-stage reranking: the LLM grades each passage 0-10 for relevance."""

    def __init__(self, llm: LLMProvider, min_score: float = 5.0) -> None:
        self._llm = llm
        self._min_score = min_score

    async def rerank(self, query: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        passages = [f"[{i}] {c.content[:700]}" for i, c in enumerate(chunks)]
        messages: list[ChatMessage] = rag_prompts.build_rerank_messages(query, passages)
        try:
            result = await complete_structured(self._llm, messages, _RerankResult, max_tokens=300)
        except Exception:
            logger.warning("Reranker failed; keeping fused order")
            return chunks
        scores = {s.id: s.score for s in result.scores if 0 <= s.id < len(chunks)}
        kept = [(scores.get(i, 0.0), c) for i, c in enumerate(chunks)]
        kept = [pair for pair in kept if pair[0] >= self._min_score]
        kept.sort(key=lambda pair: pair[0], reverse=True)
        return [c for _, c in kept]
