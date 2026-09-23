"""Provider-agnostic embedding interface."""

from __future__ import annotations

from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    name: str = "base"
    model: str = ""
    dimension: int = 0

    @abstractmethod
    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed passages for storage."""

    async def embed_query(self, text: str) -> list[float]:
        """Embed a search query (override for models that need query prefixes)."""
        return (await self.embed_documents([text]))[0]
