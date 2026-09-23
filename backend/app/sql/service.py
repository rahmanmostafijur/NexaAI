"""Text-to-SQL pipeline with bounded self-correction.

question -> schema retrieval -> SQL generation -> validation -> execution
                                   ^                  |            |
                                   +---- correction <-+------------+   (max N attempts)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date

from pydantic import BaseModel, Field

from app.core.errors import AppError, SQLExecutionError, SQLSafetyError
from app.llm.base import LLMProvider
from app.llm.structured import complete_structured
from app.prompts import sql as sql_prompts
from app.sql.catalog import SchemaCatalog
from app.sql.executor import QueryResult, SQLExecutor
from app.sql.schema_retriever import SchemaRetriever
from app.sql.validator import SQLValidator, is_correctable

logger = logging.getLogger(__name__)


class GeneratedSQL(BaseModel):
    sql: str | None = None
    explanation: str = Field(default="", max_length=600)


class SQLNotAnswerableError(AppError):
    code = "sql_not_answerable"


@dataclass
class SQLAttempt:
    sql: str
    error: str | None = None


@dataclass
class SQLRunResult:
    sql: str
    result: QueryResult
    tables: list[str]
    explanation: str
    attempts: list[SQLAttempt] = field(default_factory=list)


class SQLService:
    def __init__(
        self,
        *,
        llm: LLMProvider,
        catalog: SchemaCatalog,
        retriever: SchemaRetriever,
        executor: SQLExecutor,
        max_rows: int,
        max_corrections: int,
    ) -> None:
        self._llm = llm
        self._catalog = catalog
        self._retriever = retriever
        self._executor = executor
        self._max_rows = max_rows
        self._max_corrections = max_corrections

    async def run(self, question: str, *, context: str | None = None) -> SQLRunResult:
        snapshot = await self._catalog.snapshot()
        if not snapshot.tables:
            raise SQLNotAnswerableError("The analytics database schema is not available.")
        tables = await self._retriever.select_tables(
            f"{question}\n{context or ''}" if context else question, snapshot
        )
        schema_text = snapshot.render(tables)
        today = date.today()
        validator = SQLValidator(snapshot, self._max_rows)

        generated = await complete_structured(
            self._llm,
            sql_prompts.build_generation_messages(question, schema_text, today, context),
            GeneratedSQL,
            max_tokens=700,
        )
        attempts: list[SQLAttempt] = []
        for attempt_number in range(self._max_corrections + 1):
            if not generated.sql:
                raise SQLNotAnswerableError(
                    generated.explanation or "The database does not contain data to answer this."
                )
            attempt = SQLAttempt(sql=generated.sql)
            attempts.append(attempt)
            try:
                validated = validator.validate(generated.sql)
                attempt.sql = validated.sql
                result = await self._executor.execute(validated.sql)
                return SQLRunResult(
                    sql=validated.sql,
                    result=result,
                    tables=validated.tables,
                    explanation=generated.explanation,
                    attempts=attempts,
                )
            except (SQLSafetyError, SQLExecutionError) as exc:
                attempt.error = exc.message
                logger.info("SQL attempt %d rejected: %s", attempt_number + 1, exc.code)
                if not is_correctable(exc) or attempt_number >= self._max_corrections:
                    raise
                generated = await complete_structured(
                    self._llm,
                    sql_prompts.build_correction_messages(
                        question, schema_text, today, generated.sql, exc.message
                    ),
                    GeneratedSQL,
                    max_tokens=700,
                )
        raise SQLExecutionError("Could not produce a valid query.", correctable=False)
