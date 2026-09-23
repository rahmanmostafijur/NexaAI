"""Schema inspection: reads tables, columns, keys, indexes and COMMENTs from PostgreSQL.

The catalog is the agent's understanding of the database. Descriptions come
from `COMMENT ON` statements (declared as `comment=` on the ORM models), so the
database documents itself.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

_TABLES_SQL = """
SELECT c.relname AS table_name,
       obj_description(c.oid, 'pg_class') AS description,
       GREATEST(c.reltuples, 0)::bigint AS row_estimate
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = :schema AND c.relkind IN ('r', 'v', 'm', 'f')
ORDER BY c.relname
"""

_COLUMNS_SQL = """
SELECT c.relname AS table_name,
       a.attname AS column_name,
       format_type(a.atttypid, a.atttypmod) AS data_type,
       NOT a.attnotnull AS nullable,
       col_description(c.oid, a.attnum) AS description
FROM pg_attribute a
JOIN pg_class c ON c.oid = a.attrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = :schema AND c.relkind IN ('r', 'v', 'm', 'f') AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY c.relname, a.attnum
"""

_KEYS_SQL = """
SELECT con.contype::text AS kind,
       cl.relname AS table_name,
       att.attname AS column_name,
       rcl.relname AS ref_table,
       ratt.attname AS ref_column
FROM pg_constraint con
JOIN pg_class cl ON cl.oid = con.conrelid
JOIN pg_namespace n ON n.oid = cl.relnamespace
CROSS JOIN LATERAL unnest(con.conkey, con.confkey) AS k(attnum, refattnum)
JOIN pg_attribute att ON att.attrelid = cl.oid AND att.attnum = k.attnum
LEFT JOIN pg_class rcl ON rcl.oid = con.confrelid
LEFT JOIN pg_attribute ratt ON ratt.attrelid = con.confrelid AND ratt.attnum = k.refattnum
WHERE n.nspname = :schema AND con.contype IN ('p', 'f')
"""

_INDEXES_SQL = """
SELECT t.relname AS table_name,
       i.relname AS index_name,
       ix.indisunique AS is_unique,
       array_agg(a.attname ORDER BY k.ord) AS columns
FROM pg_index ix
JOIN pg_class i ON i.oid = ix.indexrelid
JOIN pg_class t ON t.oid = ix.indrelid
JOIN pg_namespace n ON n.oid = t.relnamespace
CROSS JOIN LATERAL unnest(ix.indkey) WITH ORDINALITY AS k(attnum, ord)
JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = k.attnum
WHERE n.nspname = :schema
GROUP BY t.relname, i.relname, ix.indisunique
ORDER BY t.relname, i.relname
"""


@dataclass(frozen=True)
class ForeignKey:
    table: str
    column: str


@dataclass
class ColumnInfo:
    name: str
    type: str
    nullable: bool
    description: str | None = None
    is_primary_key: bool = False
    foreign_key: ForeignKey | None = None


@dataclass
class IndexInfo:
    name: str
    columns: list[str]
    unique: bool


@dataclass
class TableInfo:
    name: str
    description: str | None
    row_estimate: int
    columns: list[ColumnInfo] = field(default_factory=list)
    indexes: list[IndexInfo] = field(default_factory=list)

    def column(self, name: str) -> ColumnInfo | None:
        return next((c for c in self.columns if c.name == name), None)

    @property
    def column_names(self) -> set[str]:
        return {c.name for c in self.columns}

    def card(self) -> str:
        """Short natural-language summary used for embedding-based table retrieval."""
        cols = ", ".join(
            f"{c.name}" + (f" ({c.description})" if c.description else "") for c in self.columns
        )
        return f"Table {self.name}: {self.description or ''} Columns: {cols}"


@dataclass
class SchemaSnapshot:
    schema: str
    tables: dict[str, TableInfo]

    def related_tables(self) -> dict[str, set[str]]:
        """Undirected foreign-key adjacency, used to find join paths."""
        graph: dict[str, set[str]] = {name: set() for name in self.tables}
        for table in self.tables.values():
            for column in table.columns:
                if column.foreign_key and column.foreign_key.table in graph:
                    graph[table.name].add(column.foreign_key.table)
                    graph[column.foreign_key.table].add(table.name)
        return graph

    def render(self, table_names: list[str] | None = None) -> str:
        """Compact, LLM-friendly description of the selected tables."""
        names = table_names or sorted(self.tables)
        blocks = []
        for name in names:
            table = self.tables.get(name)
            if table is None:
                continue
            lines = [f"TABLE {self.schema}.{table.name}  -- {table.description or ''}".rstrip()]
            for col in table.columns:
                flags = []
                if col.is_primary_key:
                    flags.append("PK")
                if col.foreign_key:
                    flags.append(f"FK -> {col.foreign_key.table}.{col.foreign_key.column}")
                if not col.nullable and not col.is_primary_key:
                    flags.append("NOT NULL")
                flag_text = f" [{', '.join(flags)}]" if flags else ""
                desc = f"  -- {col.description}" if col.description else ""
                lines.append(f"  {col.name} {col.type}{flag_text}{desc}")
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks)


class SchemaCatalog:
    """Loads and caches a snapshot of the business schema."""

    def __init__(self, session_factory: async_sessionmaker, schema: str) -> None:
        self._session_factory = session_factory
        self._schema = schema
        self._snapshot: SchemaSnapshot | None = None
        self._lock = asyncio.Lock()

    async def snapshot(self) -> SchemaSnapshot:
        if self._snapshot is None:
            async with self._lock:
                if self._snapshot is None:
                    self._snapshot = await self._load()
        return self._snapshot

    def invalidate(self) -> None:
        self._snapshot = None

    async def _load(self) -> SchemaSnapshot:
        params = {"schema": self._schema}
        async with self._session_factory() as session:
            table_rows = (await session.execute(text(_TABLES_SQL), params)).mappings().all()
            column_rows = (await session.execute(text(_COLUMNS_SQL), params)).mappings().all()
            key_rows = (await session.execute(text(_KEYS_SQL), params)).mappings().all()
            index_rows = (await session.execute(text(_INDEXES_SQL), params)).mappings().all()

        tables = {
            row["table_name"]: TableInfo(
                name=row["table_name"],
                description=row["description"],
                row_estimate=int(row["row_estimate"]),
            )
            for row in table_rows
        }
        for row in column_rows:
            table = tables.get(row["table_name"])
            if table is not None:
                table.columns.append(
                    ColumnInfo(
                        name=row["column_name"],
                        type=row["data_type"],
                        nullable=bool(row["nullable"]),
                        description=row["description"],
                    )
                )
        for row in key_rows:
            table = tables.get(row["table_name"])
            column = table.column(row["column_name"]) if table else None
            if column is None:
                continue
            if row["kind"] == "p":
                column.is_primary_key = True
            elif row["ref_table"]:
                column.foreign_key = ForeignKey(row["ref_table"], row["ref_column"])
        for row in index_rows:
            table = tables.get(row["table_name"])
            if table is not None:
                table.indexes.append(
                    IndexInfo(row["index_name"], list(row["columns"]), bool(row["is_unique"]))
                )
        return SchemaSnapshot(schema=self._schema, tables=tables)
