"""Executes validated SQL as the read-only role, with hard resource limits.

* READ ONLY transaction (in addition to the role's `default_transaction_read_only`)
* `SET LOCAL statement_timeout` per query
* server-side cursor that fetches at most `max_rows + 1` rows (to detect truncation)
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from datetime import time as dt_time
from decimal import Decimal
from typing import Any

import asyncpg

from app.core.errors import SQLExecutionError

JsonScalar = str | int | float | bool | None


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[list[JsonScalar]]
    row_count: int
    truncated: bool
    duration_ms: int


def to_json_scalar(value: Any) -> JsonScalar:
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, Decimal):
        is_whole = value == value.to_integral_value() and int(value.as_tuple().exponent) >= 0
        return int(value) if is_whole else float(value)
    if isinstance(value, datetime | date | dt_time):
        return value.isoformat()
    if isinstance(value, timedelta):
        return str(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, bytes | bytearray | memoryview):
        return "<binary>"
    return str(value)


class SQLExecutor:
    def __init__(
        self,
        pool_provider: Callable[[], Awaitable[asyncpg.Pool]],
        *,
        timeout_ms: int,
        max_rows: int,
    ) -> None:
        self._pool_provider = pool_provider
        self._timeout_ms = int(timeout_ms)
        self._max_rows = max_rows

    async def _run(
        self, connection: asyncpg.Connection, sql: str
    ) -> tuple[list[asyncpg.Record], list[str]]:
        async with connection.transaction(readonly=True, isolation="repeatable_read"):
            await connection.execute(f"SET LOCAL statement_timeout = {self._timeout_ms}")
            await connection.execute("SET LOCAL search_path = commerce")
            statement = await connection.prepare(sql)
            columns = [attribute.name for attribute in statement.get_attributes()]
            cursor = await statement.cursor()
            records = await cursor.fetch(self._max_rows + 1)
        return records, columns

    async def execute(self, sql: str) -> QueryResult:
        started = time.perf_counter()
        try:
            pool = await self._pool_provider()
            async with pool.acquire() as connection:
                records, columns = await self._run(connection, sql)
        except asyncpg.QueryCanceledError as exc:
            raise SQLExecutionError(
                f"The query exceeded the {self._timeout_ms} ms time limit.",
                code="sql_timeout",
                correctable=False,
            ) from exc
        except (asyncpg.InsufficientPrivilegeError, asyncpg.ReadOnlySQLTransactionError) as exc:
            raise SQLExecutionError(
                "The query tried to access data it is not permitted to.",
                code="sql_permission_denied",
                correctable=False,
            ) from exc
        except asyncpg.PostgresError as exc:
            # Syntax / undefined column / type errors: safe to show the model for correction.
            raise SQLExecutionError(
                f"{type(exc).__name__}: {exc}"[:500], code="sql_database_error", correctable=True
            ) from exc
        except (OSError, asyncpg.InterfaceError) as exc:
            raise SQLExecutionError(
                "The analytics database is unavailable.",
                code="database_unavailable",
                correctable=False,
            ) from exc

        truncated = len(records) > self._max_rows
        rows = [[to_json_scalar(value) for value in record] for record in records[: self._max_rows]]
        return QueryResult(
            columns=columns,
            rows=rows,
            row_count=len(rows),
            truncated=truncated,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
