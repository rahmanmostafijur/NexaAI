"""SQL tool: answers data questions through the Text-to-SQL pipeline."""

from __future__ import annotations

import re

from app.agent.tools.base import BaseTool, ToolContext, ToolResult
from app.core.errors import SQLExecutionError, SQLSafetyError
from app.sql.service import SQLNotAnswerableError, SQLRunResult, SQLService

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}")


class SQLTool(BaseTool):
    name = "sql"
    stage = "querying_database"
    stage_label = "Running database query..."

    def __init__(self, service: SQLService) -> None:
        self._service = service

    async def run(self, query: str, context: ToolContext) -> ToolResult:
        try:
            run = await self._service.run(query, context=context.history)
        except SQLNotAnswerableError as exc:
            return ToolResult("no_results", exc.message, error_code=exc.code)
        except SQLSafetyError as exc:
            return ToolResult(
                "failed",
                "The generated query was rejected by the safety checks.",
                error_code=exc.code,
            )
        except SQLExecutionError as exc:
            return ToolResult("failed", exc.message, error_code=exc.code)

        result = run.result
        attempts = len(run.attempts)
        summary = f"Queried {', '.join(run.tables) or 'the database'}: {result.row_count} row(s)"
        if result.truncated:
            summary += " (truncated)"
        if attempts > 1:
            summary += f", corrected after {attempts - 1} failed attempt(s)"
        return ToolResult(
            "completed" if result.row_count else "no_results",
            summary,
            sql=run,
            entity_text=entity_text(run),
        )


def entity_text(run: SQLRunResult, max_rows: int = 3) -> str | None:
    """Text labels from the top rows (e.g. "Electronics") for dependent document searches."""
    labels: list[str] = []
    for row in run.result.rows[:max_rows]:
        for value in row:
            if isinstance(value, str) and value.strip() and not _ISO_DATE.match(value):
                labels.append(value.strip())
                break
    return ", ".join(dict.fromkeys(labels)) or None
