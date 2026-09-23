"""Embeddings through any OpenAI-compatible `/embeddings` endpoint."""

from __future__ import annotations

import httpx

from app.core.errors import EmbeddingError
from app.embeddings.base import EmbeddingProvider

_BATCH_SIZE = 64


class OpenAICompatibleEmbeddingProvider(EmbeddingProvider):
    name = "openai_compatible"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        dimension: int,
        send_dimensions: bool = True,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.model = model
        self.dimension = dimension
        self._send_dimensions = send_dimensions
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"), headers=headers, timeout=60.0, transport=transport
        )

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), _BATCH_SIZE):
            vectors.extend(await self._embed_batch(texts[start : start + _BATCH_SIZE]))
        return vectors

    async def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        payload: dict[str, object] = {"model": self.model, "input": batch}
        if self._send_dimensions:
            payload["dimensions"] = self.dimension
        try:
            response = await self._client.post("/embeddings", json=payload)
        except httpx.HTTPError as exc:
            raise EmbeddingError("Could not reach the embedding service.") from exc
        if response.status_code >= 400:
            raise EmbeddingError(f"The embedding service failed (HTTP {response.status_code}).")
        data = sorted(response.json().get("data", []), key=lambda item: item.get("index", 0))
        vectors = [item["embedding"] for item in data]
        if len(vectors) != len(batch) or any(len(v) != self.dimension for v in vectors):
            raise EmbeddingError(
                "The embedding service returned vectors that do not match EMBEDDING_DIMENSION."
            )
        return vectors
