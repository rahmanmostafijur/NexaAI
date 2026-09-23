from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    database: bool
    llm_configured: bool


class SystemInfo(BaseModel):
    app_name: str
    version: str
    llm_provider: str
    llm_model: str
    embedding_provider: str
    embedding_model: str
    max_upload_mb: int
    allowed_extensions: list[str]


class ForeignKeyOut(BaseModel):
    table: str
    column: str


class ColumnOut(BaseModel):
    name: str
    type: str
    nullable: bool
    description: str | None
    is_primary_key: bool
    foreign_key: ForeignKeyOut | None


class IndexOut(BaseModel):
    name: str
    columns: list[str]
    unique: bool


class TableOut(BaseModel):
    name: str
    description: str | None
    row_estimate: int
    columns: list[ColumnOut]
    indexes: list[IndexOut]


class SchemaOut(BaseModel):
    # "schema" collides with a BaseModel attribute, so it is exposed via an alias.
    model_config = ConfigDict(populate_by_name=True)

    schema_name: str = Field(serialization_alias="schema")
    tables: list[TableOut]


class TableSummary(BaseModel):
    name: str
    description: str | None
    column_count: int
    row_estimate: int
