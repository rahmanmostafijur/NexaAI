from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    filename: str
    content_type: str
    source_type: Literal["pdf", "docx", "txt", "markdown", "csv"]
    size_bytes: int
    status: Literal["pending", "processing", "indexed", "failed"]
    chunk_count: int
    page_count: int | None
    error: str | None
    created_at: datetime
    updated_at: datetime
    indexed_at: datetime | None


class DocumentList(BaseModel):
    items: list[DocumentOut]
    total: int


class ChunkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    chunk_index: int
    page: int | None
    section: str | None
    content: str
    token_estimate: int


class ChunkList(BaseModel):
    items: list[ChunkOut]
    total: int


class SearchResult(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    title: str
    filename: str
    page: int | None
    section: str | None
    content: str
    score: float
    vector_score: float | None
    keyword_score: float | None


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]
