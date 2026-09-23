"""SQL safety layer: never trust generated SQL.

The query is parsed into an AST (sqlglot, PostgreSQL dialect) and checked:

1. exactly one statement, and it is a SELECT / set operation (CTEs allowed);
2. no data-modifying, DDL, locking, transaction or utility nodes anywhere in the tree;
3. every table is an allowlisted table of the business schema (no pg_catalog,
   information_schema or app tables);
4. no dangerous functions (file access, sleeping, config, backend control, dblink...);
5. referenced columns exist (errors here are fed back to the model for correction);
6. a row LIMIT is enforced.

The re-rendered SQL (comments stripped) is what gets executed, never the raw text.
This layer is one of four defences; the others are the prompt, a READ ONLY
transaction with a statement timeout, and a database role that only has SELECT.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from app.core.errors import SQLSafetyError
from app.sql.catalog import SchemaSnapshot

MAX_SQL_LENGTH = 8000

_FORBIDDEN_NODE_NAMES = [
    "Insert",
    "Update",
    "Delete",
    "Merge",
    "Create",
    "Drop",
    "Alter",
    "AlterTable",
    "TruncateTable",
    "Command",
    "Into",
    "Lock",
    "Set",
    "Grant",
    "Revoke",
    "Copy",
    "Transaction",
    "Commit",
    "Rollback",
    "Pragma",
    "Use",
    "Analyze",
    "Kill",
    "LoadData",
]
_FORBIDDEN_NODES: tuple[type[exp.Expression], ...] = tuple(
    node for name in _FORBIDDEN_NODE_NAMES if (node := getattr(exp, name, None)) is not None
)

BLOCKED_FUNCTIONS = {
    "pg_sleep",
    "pg_sleep_for",
    "pg_sleep_until",
    "pg_read_file",
    "pg_read_binary_file",
    "pg_ls_dir",
    "pg_stat_file",
    "pg_terminate_backend",
    "pg_cancel_backend",
    "pg_reload_conf",
    "pg_rotate_logfile",
    "set_config",
    "current_setting",
    "lo_import",
    "lo_export",
    "lo_get",
    "lo_put",
    "lo_create",
    "lo_unlink",
    "dblink",
    "dblink_exec",
    "dblink_connect",
    "query_to_xml",
    "query_to_json",
    "table_to_xml",
    "database_to_xml",
    "txid_current",
    "pg_advisory_lock",
    "pg_advisory_xact_lock",
    "pg_try_advisory_lock",
    "version",
    "inet_server_addr",
    "current_user",
    "session_user",
    "current_database",
    "has_table_privilege",
    "generate_series",
}
_BLOCKED_PREFIXES = ("pg_", "lo_", "dblink", "xpath")
_BLOCKED_SCHEMAS = {"pg_catalog", "information_schema", "public", "pg_toast"}
_BLOCKED_TEXT = re.compile(
    r"\b(" + "|".join(sorted(BLOCKED_FUNCTIONS | {"pg_\\w+", "lo_\\w+", "dblink\\w*"})) + r")\s*\(",
    re.IGNORECASE,
)


@dataclass
class ValidatedSQL:
    sql: str
    tables: list[str]
    limit: int
    warnings: list[str] = field(default_factory=list)


class SQLValidator:
    def __init__(self, snapshot: SchemaSnapshot, max_rows: int) -> None:
        self._snapshot = snapshot
        self._max_rows = max_rows

    def validate(self, sql: str) -> ValidatedSQL:
        if not sql or not sql.strip():
            raise SQLSafetyError("The generated query is empty.", code="sql_empty")
        if len(sql) > MAX_SQL_LENGTH:
            raise SQLSafetyError("The generated query is too long.", code="sql_too_long")

        root = self._parse_single_statement(sql)
        self._check_statement_type(root)
        self._check_forbidden_nodes(root)
        tables = self._check_tables(root)
        self._check_functions(root)
        self._check_columns(root)
        limit = self._enforce_limit(root)

        rendered = root.sql(dialect="postgres", comments=False)
        if _BLOCKED_TEXT.search(rendered):
            raise SQLSafetyError(
                "The query calls a function that is not allowed.", code="sql_blocked_function"
            )
        return ValidatedSQL(sql=rendered, tables=tables, limit=limit)

    # --- individual checks -------------------------------------------------

    def _parse_single_statement(self, sql: str) -> exp.Expression:
        try:
            statements = [s for s in sqlglot.parse(sql, read="postgres") if s is not None]
        except ParseError as exc:
            message = str(exc).splitlines()[0][:300]
            raise _correctable(f"SQL syntax error: {message}", "sql_syntax_error") from exc
        if len(statements) != 1:
            raise SQLSafetyError(
                "Only a single SQL statement is allowed.", code="sql_multiple_statements"
            )
        return statements[0]

    def _check_statement_type(self, root: exp.Expression) -> None:
        node = root
        while isinstance(node, exp.Subquery):
            node = node.this
        set_operation = getattr(exp, "SetOperation", exp.Union)
        if not isinstance(node, exp.Select | set_operation):
            raise SQLSafetyError(
                "Only read-only SELECT queries are allowed.", code="sql_not_select"
            )

    def _check_forbidden_nodes(self, root: exp.Expression) -> None:
        for node in root.walk():
            if isinstance(node, _FORBIDDEN_NODES):
                raise SQLSafetyError(
                    f"Statements of type {type(node).__name__.upper()} are not allowed.",
                    code="sql_forbidden_statement",
                )
            if isinstance(node, exp.Select) and node.args.get("locks"):
                raise SQLSafetyError("Row locking clauses are not allowed.", code="sql_locking")

    def _cte_names(self, root: exp.Expression) -> set[str]:
        return {cte.alias_or_name.lower() for cte in root.find_all(exp.CTE)}

    def _check_tables(self, root: exp.Expression) -> list[str]:
        ctes = self._cte_names(root)
        allowed = set(self._snapshot.tables)
        used: list[str] = []
        for table in root.find_all(exp.Table):
            name = table.name.lower()
            schema = (table.db or "").lower()
            if table.catalog:
                raise SQLSafetyError("Cross-database references are not allowed.", code="sql_table")
            if not name:
                # Table-valued function, e.g. FROM generate_series(...)
                raise SQLSafetyError("Table functions are not allowed.", code="sql_table_function")
            if schema in _BLOCKED_SCHEMAS or name.startswith("pg_"):
                raise SQLSafetyError(
                    "System and application tables cannot be queried.", code="sql_forbidden_table"
                )
            if not schema and name in ctes:
                continue
            if schema and schema != self._snapshot.schema:
                raise SQLSafetyError(
                    f"Only tables in the '{self._snapshot.schema}' schema can be queried.",
                    code="sql_forbidden_table",
                )
            if name not in allowed:
                raise _correctable(
                    f'Table "{name}" does not exist. Available tables: '
                    + ", ".join(sorted(allowed)),
                    "sql_unknown_table",
                )
            if name not in used:
                used.append(name)
        return used

    def _check_functions(self, root: exp.Expression) -> None:
        for func in root.find_all(exp.Func):
            name = (func.name if isinstance(func, exp.Anonymous) else func.sql_name()).lower()
            if name in BLOCKED_FUNCTIONS or name.startswith(_BLOCKED_PREFIXES):
                raise SQLSafetyError(
                    f"The function {name}() is not allowed.", code="sql_blocked_function"
                )

    def _check_columns(self, root: exp.Expression) -> None:
        """Verify qualified columns exist; unqualified ones only when unambiguous to check."""
        ctes = self._cte_names(root)
        alias_to_table: dict[str, str] = {}
        derived_aliases: set[str] = set(ctes)
        for table in root.find_all(exp.Table):
            name = table.name.lower()
            if name in self._snapshot.tables and name not in ctes:
                alias_to_table[table.alias_or_name.lower()] = name
                alias_to_table.setdefault(name, name)
        for subquery in root.find_all(exp.Subquery):
            if subquery.alias:
                derived_aliases.add(subquery.alias.lower())

        output_aliases = {a.alias.lower() for a in root.find_all(exp.Alias) if a.alias}
        real_tables = set(alias_to_table.values())
        has_derived = bool(derived_aliases) or any(
            isinstance(node, exp.Subquery) for node in root.walk()
        )

        for column in root.find_all(exp.Column):
            col_name = column.name.lower()
            if not col_name or col_name == "*":
                continue
            qualifier = (column.table or "").lower()
            if qualifier:
                table_name = alias_to_table.get(qualifier)
                if table_name is None:
                    continue  # CTE, subquery alias or unresolvable: the database will tell us
                if col_name not in self._snapshot.tables[table_name].column_names:
                    raise _correctable(
                        f'Column "{col_name}" does not exist on table "{table_name}". '
                        f"Its columns are: "
                        + ", ".join(sorted(self._snapshot.tables[table_name].column_names)),
                        "sql_unknown_column",
                    )
            elif not has_derived and col_name not in output_aliases:
                known = any(col_name in self._snapshot.tables[t].column_names for t in real_tables)
                if real_tables and not known:
                    raise _correctable(
                        f'Column "{col_name}" does not exist in the referenced tables '
                        f"({', '.join(sorted(real_tables))}).",
                        "sql_unknown_column",
                    )

    def _enforce_limit(self, root: exp.Expression) -> int:
        limit_node = root.args.get("limit")
        requested: int | None = None
        if isinstance(limit_node, exp.Limit):
            value = limit_node.expression
            if isinstance(value, exp.Literal) and value.is_int:
                requested = int(value.this)
        limit = min(requested, self._max_rows) if requested is not None else self._max_rows
        root.set("limit", exp.Limit(expression=exp.Literal.number(limit)))
        return limit


def _correctable(message: str, code: str) -> SQLSafetyError:
    error = SQLSafetyError(message, code=code)
    error.correctable = True  # type: ignore[attr-defined]
    return error


def is_correctable(error: Exception) -> bool:
    return bool(getattr(error, "correctable", False))
