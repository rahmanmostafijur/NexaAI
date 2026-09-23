"""Test doubles: a scripted LLM and a deterministic hashing embedder."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import AsyncIterator
from typing import Any

from app.embeddings.base import EmbeddingProvider
from app.llm.base import ChatMessage, LLMProvider, LLMResponse, TokenUsage
from app.llm.usage import record_usage

DEFAULT_SQL = "SELECT COUNT(*) AS total_orders FROM orders"


def prompt_kind(messages: list[ChatMessage]) -> str:
    system = messages[0].content if messages else ""
    last = messages[-1].content if messages else ""
    if "query router" in system:
        return "router"
    if "This query failed" in last:
        return "sql_correction"
    if "analytics engineer" in system:
        return "sql"
    if "You plan how to answer" in system:
        return "planner"
    if "Rate how useful" in system:
        return "rerank"
    return "answer"


class ScriptedLLM(LLMProvider):
    """Returns canned outputs per prompt type; records every call for assertions."""

    name = "scripted"
    model = "scripted-test-model"

    def __init__(self) -> None:
        self.routes: dict[str, dict[str, Any]] = {}
        self.sql: dict[str, str] = {}
        self.corrections: list[str] = []
        self.plan: dict[str, Any] | None = None
        self.answer: str | None = None
        self.fail_with: Exception | None = None
        self.calls: list[tuple[str, list[ChatMessage]]] = []

    def _match(self, mapping: dict[str, Any], text: str) -> Any:
        for key, value in mapping.items():
            if key.lower() in text.lower():
                return value
        return None

    async def complete(self, messages: list[ChatMessage], **_: Any) -> LLMResponse:
        kind = prompt_kind(messages)
        self.calls.append((kind, messages))
        if self.fail_with is not None:
            raise self.fail_with
        text = messages[-1].content
        if kind == "router":
            latest = text.rsplit("Latest user message:", 1)[-1]
            decision = self._match(self.routes, latest) or {
                "route": "GENERAL",
                "confidence": 0.9,
                "reason": "General question.",
                "standalone_query": latest.strip(),
            }
            payload: Any = decision
        elif kind in ("sql", "sql_correction"):
            if kind == "sql_correction" and self.corrections:
                sql = self.corrections.pop(0)
            else:
                question = text.rsplit("Question:", 1)[-1]
                sql = self._match(self.sql, question) or DEFAULT_SQL
            payload = {"sql": sql, "explanation": "Test query."}
        elif kind == "planner":
            payload = self.plan or {
                "steps": [
                    {
                        "id": "s1",
                        "tool": "sql",
                        "query": "top product by returns",
                        "depends_on": [],
                    },
                    {
                        "id": "s2",
                        "tool": "rag",
                        "query": "return policy for {s1}",
                        "depends_on": ["s1"],
                    },
                ]
            }
        else:
            payload = {"scores": []}
        record_usage(10, 5)
        return LLMResponse(text=json.dumps(payload), usage=TokenUsage(10, 5), model=self.model)

    async def stream(self, messages: list[ChatMessage], **_: Any) -> AsyncIterator[str]:
        self.calls.append(("stream", messages))
        if self.fail_with is not None:
            raise self.fail_with
        text = self.answer or self._default_answer(messages[-1].content)
        record_usage(20, 10)
        for start in range(0, len(text), 8):
            yield text[start : start + 8]

    @staticmethod
    def _default_answer(user_content: str) -> str:
        if '<document id="S1"' in user_content and "<database_result" in user_content:
            return "The data shows the result [DB1]. The policy says returns take 30 days [S1]."
        if '<document id="S1"' in user_content:
            return "Items can be returned within 30 days [S1]. See also [S99]."
        if "<database_result" in user_content:
            return "Here is the answer from the database [DB1]."
        return "A database index is a data structure that speeds up lookups."


class HashingEmbeddings(EmbeddingProvider):
    """Bag-of-words hashing embedder: deterministic, no model download, keyword-sensitive."""

    name = "hashing"
    model = "hashing-test"

    def __init__(self, dimension: int = 384) -> None:
        self.dimension = dimension

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for token in re.findall(r"[0-9a-zঀ-৿]+", text.lower()):
            digest = int(hashlib.md5(token.encode(), usedforsecurity=False).hexdigest(), 16)
            vector[digest % self.dimension] += 1.0
        vector[-1] += 0.01  # never a zero vector (cosine distance would be undefined)
        return vector
