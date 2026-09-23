"""Hybrid retrieval against pgvector + full-text search in the test database."""

import pytest

from app.db.session import get_session_factory
from app.rag.retriever import HybridRetriever

pytestmark = pytest.mark.usefixtures("knowledge_base")


def retriever(embeddings, min_similarity: float = 0.2) -> HybridRetriever:
    return HybridRetriever(get_session_factory(), embeddings, min_similarity=min_similarity)


async def test_finds_the_relevant_policy_section(embeddings) -> None:
    # The hashing test embedder is not semantic, so only require the section in the top 5;
    # ranking quality with the real model is measured by the evaluation suite.
    results = await retriever(embeddings).search(
        "return window for electronics and mobile phones", top_k=5
    )
    assert results
    assert results[0].title == "Return Policy"
    assert "Electronics and Mobile Phones" in [r.section for r in results]
    assert results[0].vector_score is not None and results[0].keyword_score is not None
    assert results[0].score >= results[-1].score


async def test_document_filter_restricts_results(embeddings, knowledge_base) -> None:
    membership_id = knowledge_base["Customer_Membership_Policy.md"]
    results = await retriever(embeddings).search(
        "return window days", top_k=5, document_ids=[membership_id]
    )
    assert results and all(r.document_id == membership_id for r in results)


async def test_relevance_threshold_filters_unrelated_content(embeddings) -> None:
    assert await retriever(embeddings, min_similarity=0.95).search("return policy", top_k=3) == []
    assert await retriever(embeddings).search("zqxv wplk", top_k=3) == []


async def test_injected_instructions_are_flagged_as_suspicious(embeddings) -> None:
    results = await retriever(embeddings).search("supplier delivery partners parcel", top_k=3)
    suspicious = [r for r in results if r.title == "Supplier Notes"]
    assert suspicious and suspicious[0].suspicious


async def test_multiple_query_variants_are_fused(embeddings) -> None:
    results = await retriever(embeddings).search(
        "Platinum", top_k=3, extra_queries=["membership tier discount benefits"]
    )
    assert results[0].title == "Customer Membership Policy"
