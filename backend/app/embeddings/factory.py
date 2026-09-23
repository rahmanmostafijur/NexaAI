"""Builds the configured embedding provider."""

from __future__ import annotations

from functools import lru_cache

from app.core.config import Settings, get_settings
from app.embeddings.base import EmbeddingProvider
from app.embeddings.fastembed_provider import FastEmbedProvider
from app.embeddings.openai_compatible import OpenAICompatibleEmbeddingProvider


def build_embedding_provider(settings: Settings) -> EmbeddingProvider:
    if settings.embedding_provider == "openai_compatible":
        return OpenAICompatibleEmbeddingProvider(
            base_url=settings.embedding_base_url or settings.llm_base_url,
            api_key=(
                settings.embedding_api_key.get_secret_value()
                or settings.llm_api_key.get_secret_value()
            ),
            model=settings.embedding_model,
            dimension=settings.embedding_dimension,
        )
    return FastEmbedProvider(
        model=settings.embedding_model,
        dimension=settings.embedding_dimension,
        cache_dir=settings.fastembed_cache_dir,
    )


@lru_cache
def get_embedding_provider() -> EmbeddingProvider:
    return build_embedding_provider(get_settings())
