"""Composition root: builds and wires every agent dependency once per process."""

from __future__ import annotations

from dataclasses import dataclass

from app.agent.executor import ToolExecutor
from app.agent.planner import Planner
from app.agent.responder import ResponseGenerator
from app.agent.router import QueryRouter
from app.agent.tools.base import ToolRegistry
from app.agent.tools.rag_tool import GeneralTool, RAGTool
from app.agent.tools.sql_tool import SQLTool
from app.core.config import Settings
from app.db.session import get_readonly_pool, get_session_factory
from app.embeddings.base import EmbeddingProvider
from app.llm.base import LLMProvider
from app.rag.ingestion import IngestionService
from app.rag.retriever import HybridRetriever, LLMReranker
from app.sql.catalog import SchemaCatalog
from app.sql.executor import SQLExecutor
from app.sql.schema_retriever import SchemaRetriever
from app.sql.service import SQLService


@dataclass
class AgentServices:
    settings: Settings
    llm: LLMProvider
    embeddings: EmbeddingProvider
    catalog: SchemaCatalog
    retriever: HybridRetriever
    sql_service: SQLService
    ingestion: IngestionService
    router: QueryRouter
    planner: Planner
    registry: ToolRegistry
    executor: ToolExecutor
    responder: ResponseGenerator

    @classmethod
    def build(
        cls, settings: Settings, llm: LLMProvider, embeddings: EmbeddingProvider
    ) -> AgentServices:
        session_factory = get_session_factory()
        catalog = SchemaCatalog(session_factory, settings.business_schema)
        reranker = LLMReranker(llm) if settings.rag_reranker == "llm" and llm.configured else None
        retriever = HybridRetriever(
            session_factory,
            embeddings,
            min_similarity=settings.rag_min_similarity,
            reranker=reranker,
        )
        sql_service = SQLService(
            llm=llm,
            catalog=catalog,
            retriever=SchemaRetriever(embeddings),
            executor=SQLExecutor(
                get_readonly_pool,
                timeout_ms=settings.sql_statement_timeout_ms,
                max_rows=settings.sql_max_rows,
            ),
            max_rows=settings.sql_max_rows,
            max_corrections=settings.sql_max_correction_attempts,
        )
        registry = ToolRegistry()
        registry.register(SQLTool(sql_service))
        registry.register(RAGTool(retriever, settings.rag_top_k))
        registry.register(GeneralTool())
        return cls(
            settings=settings,
            llm=llm,
            embeddings=embeddings,
            catalog=catalog,
            retriever=retriever,
            sql_service=sql_service,
            ingestion=IngestionService(session_factory, embeddings, settings),
            router=QueryRouter(llm, retriever, clarify_threshold=settings.router_clarify_threshold),
            planner=Planner(llm),
            registry=registry,
            executor=ToolExecutor(registry),
            responder=ResponseGenerator(llm),
        )
