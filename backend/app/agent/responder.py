"""Response generator: turns tool evidence into the final prompt (or a fixed reply).

It also owns the list of citable sources: `DB<n>` for each SQL result and
`S<n>` for each retrieved passage.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from app.agent.messages import localized
from app.agent.tools.base import ToolResult
from app.agent.types import LanguageInfo, Plan, Route, RouteDecision
from app.llm.base import ChatMessage, LLMProvider
from app.prompts import answer as answer_prompts
from app.prompts import rag as rag_prompts
from app.prompts.common import escape_tag_content
from app.rag.context import build_document_context
from app.rag.retriever import RetrievedChunk

_ROWS_IN_PROMPT = 50
_MAX_PASSAGES = 8


@dataclass
class PreparedAnswer:
    messages: list[ChatMessage] | None
    canned: str | None
    sources: list[dict[str, Any]] = field(default_factory=list)
    prompt_version: str | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def valid_ids(self) -> set[str]:
        return {str(source["id"]) for source in self.sources}


class ResponseGenerator:
    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm

    def prepare(
        self,
        *,
        decision: RouteDecision,
        language: LanguageInfo,
        message: str,
        plan: Plan,
        results: dict[str, ToolResult],
        history: str | None,
    ) -> PreparedAnswer:
        question = message
        if decision.standalone_query and decision.standalone_query.strip() != message.strip():
            question = f"{message}\n(Interpreted as: {decision.standalone_query})"
        code = language.code

        sql_results = [(sid, r) for sid, r in _ordered(plan, results) if r.sql is not None]
        db_block, db_sources = _database_evidence(sql_results)
        chunks = _unique_chunks(r.chunks for _, r in _ordered(plan, results))
        doc_block, doc_sources = build_document_context(chunks[:_MAX_PASSAGES])
        sources = db_sources + [s.as_dict() for s in doc_sources]
        failures = [r.summary for _, r in _ordered(plan, results) if r.status == "failed"]

        if decision.route == Route.GENERAL:
            return PreparedAnswer(
                answer_prompts.build_general_messages(message, code, history),
                None,
                prompt_version=answer_prompts.GENERAL_VERSION,
            )

        if decision.route == Route.SQL:
            if not sql_results:
                reason = next((r.summary for r in results.values()), None)
                key = "sql_failed" if failures else "no_data"
                return PreparedAnswer(None, localized(key, code, reason), warnings=failures)
            return PreparedAnswer(
                answer_prompts.build_sql_answer_messages(question, db_block, code),
                None,
                sources,
                answer_prompts.SQL_ANSWER_VERSION,
                failures,
            )

        if decision.route == Route.RAG:
            if not chunks:
                return PreparedAnswer(None, localized("no_documents", code), warnings=failures)
            return PreparedAnswer(
                rag_prompts.build_answer_messages(question, doc_block, code, history),
                None,
                sources,
                rag_prompts.ANSWER_VERSION,
                failures,
            )

        # HYBRID
        if not sql_results and not chunks:
            return PreparedAnswer(None, localized("nothing_found", code), warnings=failures)
        if not sql_results:
            db_block = "(no database results: " + ("; ".join(failures) or "no matching data") + ")"
        return PreparedAnswer(
            answer_prompts.build_hybrid_answer_messages(question, db_block, doc_block, code),
            None,
            sources,
            answer_prompts.HYBRID_ANSWER_VERSION,
            failures,
        )

    async def stream(self, prepared: PreparedAnswer) -> AsyncIterator[str]:
        if prepared.canned is not None:
            yield prepared.canned
            return
        assert prepared.messages is not None
        async for delta in self._llm.stream(prepared.messages):
            yield delta


def _ordered(plan: Plan, results: dict[str, ToolResult]) -> list[tuple[str, ToolResult]]:
    return [(step.id, results[step.id]) for step in plan.steps if step.id in results]


def _unique_chunks(groups) -> list[RetrievedChunk]:
    seen: set[object] = set()
    unique: list[RetrievedChunk] = []
    for group in groups:
        for chunk in group:
            if chunk.chunk_id not in seen:
                seen.add(chunk.chunk_id)
                unique.append(chunk)
    return unique


def _database_evidence(
    sql_results: list[tuple[str, ToolResult]],
) -> tuple[str, list[dict[str, Any]]]:
    blocks: list[str] = []
    sources: list[dict[str, Any]] = []
    for index, (_, result) in enumerate(sql_results, start=1):
        assert result.sql is not None
        run = result.sql
        source_id = f"DB{index}"
        sources.append(
            {"id": source_id, "type": "database", "title": "PostgreSQL", "tables": run.tables}
        )
        header = " | ".join(run.result.columns)
        rows = [
            " | ".join("NULL" if v is None else escape_tag_content(str(v)) for v in row)
            for row in run.result.rows[:_ROWS_IN_PROMPT]
        ]
        truncated = run.result.truncated or run.result.row_count > _ROWS_IN_PROMPT
        blocks.append(
            f'<database_result id="{source_id}" rows="{run.result.row_count}" '
            f'truncated="{str(truncated).lower()}">\n'
            f"What it computes: {escape_tag_content(run.explanation)}\n"
            f"SQL: {run.sql}\n{header}\n"
            + ("\n".join(rows) or "(no rows)")
            + "\n</database_result>"
        )
    return "\n\n".join(blocks), sources
