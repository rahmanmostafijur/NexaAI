"""RAG tool: retrieves relevant knowledge-base passages."""

from __future__ import annotations

from app.agent.tools.base import BaseTool, ToolContext, ToolResult
from app.core.errors import EmbeddingError
from app.rag.retriever import HybridRetriever


class RAGTool(BaseTool):
    name = "rag"
    stage = "searching_documents"
    stage_label = "Searching knowledge base..."

    def __init__(self, retriever: HybridRetriever, top_k: int) -> None:
        self._retriever = retriever
        self._top_k = top_k

    async def run(self, query: str, context: ToolContext) -> ToolResult:
        extra = [context.original_message] if context.original_message != query else []
        try:
            chunks = await self._retriever.search(query, top_k=self._top_k, extra_queries=extra)
        except EmbeddingError as exc:
            return ToolResult("failed", exc.message, error_code=exc.code)
        if not chunks:
            return ToolResult("no_results", "No relevant passages found in the knowledge base.")
        documents = {chunk.title for chunk in chunks}
        return ToolResult(
            "completed",
            f"Found {len(chunks)} relevant passage(s) in {len(documents)} document(s)",
            chunks=chunks,
        )


class GeneralTool(BaseTool):
    """No external data: the answer comes from the model's general knowledge."""

    name = "general"
    stage = "generating"
    stage_label = "Preparing answer..."

    async def run(self, query: str, context: ToolContext) -> ToolResult:
        return ToolResult("completed", "No company data needed for this question.")
