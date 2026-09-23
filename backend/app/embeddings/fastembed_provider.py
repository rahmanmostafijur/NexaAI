"""Local embeddings with fastembed (ONNX runtime, no API key required).

The default model, paraphrase-multilingual-MiniLM-L12-v2, maps Bengali,
Banglish and English text into one vector space, so a Bengali question can
retrieve an English policy paragraph.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

from app.core.errors import EmbeddingError
from app.embeddings.base import EmbeddingProvider

logger = logging.getLogger(__name__)

_BATCH_SIZE = 32


class FastEmbedProvider(EmbeddingProvider):
    name = "fastembed"

    def __init__(self, model: str, dimension: int, cache_dir: str | None = None) -> None:
        self.model = model
        self.dimension = dimension
        self._cache_dir = cache_dir
        self._engine: Any = None
        self._lock = threading.Lock()

    def _load(self) -> Any:
        with self._lock:
            if self._engine is None:
                from fastembed import TextEmbedding

                logger.info("Loading embedding model %s", self.model)
                self._engine = TextEmbedding(model_name=self.model, cache_dir=self._cache_dir)
        return self._engine

    def _embed_sync(self, texts: list[str]) -> list[list[float]]:
        engine = self._load()
        vectors = [vector.tolist() for vector in engine.embed(texts, batch_size=_BATCH_SIZE)]
        if vectors and len(vectors[0]) != self.dimension:
            raise EmbeddingError(
                f"Embedding model returns {len(vectors[0])} dimensions but "
                f"EMBEDDING_DIMENSION is {self.dimension}."
            )
        return vectors

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            return await asyncio.to_thread(self._embed_sync, texts)
        except EmbeddingError:
            raise
        except Exception as exc:
            logger.exception("Local embedding failed")
            raise EmbeddingError("The embedding model failed to process the text.") from exc
