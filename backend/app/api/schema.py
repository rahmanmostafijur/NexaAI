"""Database schema introspection (what the Text-to-SQL engine can see)."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import AdminUser, ServicesDep
from app.schemas.system import (
    ColumnOut,
    ForeignKeyOut,
    IndexOut,
    SchemaOut,
    TableOut,
    TableSummary,
)
from app.sql.catalog import TableInfo

router = APIRouter(prefix="/schema", tags=["schema"])


def _table_out(table: TableInfo) -> TableOut:
    return TableOut(
        name=table.name,
        description=table.description,
        row_estimate=table.row_estimate,
        columns=[
            ColumnOut(
                name=c.name,
                type=c.type,
                nullable=c.nullable,
                description=c.description,
                is_primary_key=c.is_primary_key,
                foreign_key=ForeignKeyOut(table=c.foreign_key.table, column=c.foreign_key.column)
                if c.foreign_key
                else None,
            )
            for c in table.columns
        ],
        indexes=[IndexOut(name=i.name, columns=i.columns, unique=i.unique) for i in table.indexes],
    )


@router.get("", response_model=SchemaOut)
async def get_schema(user: AdminUser, services: ServicesDep) -> SchemaOut:
    snapshot = await services.catalog.snapshot()
    return SchemaOut(
        schema_name=snapshot.schema, tables=[_table_out(t) for t in snapshot.tables.values()]
    )


@router.get("/tables", response_model=list[TableSummary])
async def list_tables(user: AdminUser, services: ServicesDep) -> list[TableSummary]:
    snapshot = await services.catalog.snapshot()
    return [
        TableSummary(
            name=t.name,
            description=t.description,
            column_count=len(t.columns),
            row_estimate=t.row_estimate,
        )
        for t in snapshot.tables.values()
    ]
