from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.models import Document, DocumentChunk


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(self) -> list[Document]:
        return list(
            await self._session.scalars(select(Document).order_by(Document.created_at.desc()))
        )

    async def get(self, document_id: uuid.UUID) -> Document:
        document = await self._session.get(Document, document_id)
        if document is None:
            raise NotFoundError("Document not found")
        return document

    async def indexed_titles(self) -> list[str]:
        rows = await self._session.scalars(
            select(Document.title).where(Document.status == "indexed").order_by(Document.title)
        )
        return list(rows)

    async def chunks(
        self, document_id: uuid.UUID, *, limit: int, offset: int
    ) -> tuple[list[DocumentChunk], int]:
        total = await self._session.scalar(
            select(func.count(DocumentChunk.id)).where(DocumentChunk.document_id == document_id)
        )
        rows = await self._session.scalars(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index)
            .limit(limit)
            .offset(offset)
        )
        return list(rows), int(total or 0)
