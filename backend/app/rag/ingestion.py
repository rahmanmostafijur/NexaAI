"""Document ingestion service: upload validation, storage and indexing.

upload -> validate (extension, size, magic bytes) -> store file -> Document(status=pending)
background: extract -> clean -> chunk -> detect injection -> embed -> store chunks -> indexed
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import uuid
import zipfile
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.errors import (
    AppError,
    ConflictError,
    DocumentProcessingError,
    NotFoundError,
    PayloadTooLargeError,
    UnsupportedMediaTypeError,
)
from app.embeddings.base import EmbeddingProvider
from app.models import Document, DocumentChunk
from app.rag.chunker import chunk_document
from app.rag.cleaning import clean_text
from app.rag.extractors import SOURCE_TYPES, PageText, extract, source_type_for
from app.rag.injection import find_injection_markers

logger = logging.getLogger(__name__)

_SAFE_FILENAME = re.compile(r"[^\w.\- ()ঀ-৿]+")
_EMBED_BATCH = 64


def sanitize_filename(filename: str) -> str:
    name = Path(filename.replace("\\", "/")).name
    name = _SAFE_FILENAME.sub("_", name).strip(" .") or "document"
    return name[:200]


def validate_upload(filename: str, data: bytes, max_bytes: int) -> str:
    """Return the source type or raise. Checks extension, size and file signature."""
    source_type = source_type_for(filename)
    if source_type is None:
        allowed = ", ".join(sorted(SOURCE_TYPES))
        raise UnsupportedMediaTypeError(f"Unsupported file type. Allowed: {allowed}")
    if not data:
        raise DocumentProcessingError("The uploaded file is empty.")
    if len(data) > max_bytes:
        raise PayloadTooLargeError(f"File exceeds the {max_bytes // (1024 * 1024)} MB limit.")
    if source_type == "pdf" and not data.startswith(b"%PDF-"):
        raise UnsupportedMediaTypeError("The file does not look like a valid PDF.")
    if source_type == "docx":
        try:
            with zipfile.ZipFile(BytesIO(data)) as archive:
                if "word/document.xml" not in archive.namelist():
                    raise UnsupportedMediaTypeError("The file is not a valid DOCX document.")
        except zipfile.BadZipFile as exc:
            raise UnsupportedMediaTypeError("The file is not a valid DOCX document.") from exc
    is_text = source_type in {"txt", "markdown", "csv"}
    has_nul = b"\x00" in data[:4096] and not data.startswith((b"\xff\xfe", b"\xfe\xff"))
    if is_text and has_nul:
        raise UnsupportedMediaTypeError("Text files must not contain binary data.")
    return source_type


def title_from_filename(filename: str) -> str:
    stem = Path(filename).stem.replace("_", " ").replace("-", " ").strip()
    return " ".join(word.capitalize() if word.islower() else word for word in stem.split())


class IngestionService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        embeddings: EmbeddingProvider,
        settings: Settings,
    ) -> None:
        self._session_factory = session_factory
        self._embeddings = embeddings
        self._settings = settings

    async def create_document(
        self,
        *,
        data: bytes,
        filename: str,
        content_type: str | None,
        title: str | None,
        uploaded_by: uuid.UUID | None,
    ) -> Document:
        safe_name = sanitize_filename(filename)
        source_type = validate_upload(safe_name, data, self._settings.max_upload_bytes)
        checksum = hashlib.sha256(data).hexdigest()
        async with self._session_factory() as session:
            duplicate = await session.scalar(select(Document).where(Document.checksum == checksum))
            if duplicate is not None:
                raise ConflictError(
                    f'This file is already in the knowledge base as "{duplicate.title}".'
                )

            document_id = uuid.uuid4()
            upload_dir = Path(self._settings.upload_dir)
            await asyncio.to_thread(upload_dir.mkdir, parents=True, exist_ok=True)
            stored_path = upload_dir / f"{document_id}{Path(safe_name).suffix.lower()}"
            await asyncio.to_thread(stored_path.write_bytes, data)

            document = Document(
                id=document_id,
                title=(title or "").strip()[:300] or title_from_filename(safe_name),
                filename=safe_name,
                stored_path=str(stored_path),
                content_type=(content_type or "application/octet-stream")[:150],
                source_type=source_type,
                size_bytes=len(data),
                checksum=checksum,
                status="pending",
                uploaded_by=uploaded_by,
                meta={},
            )
            session.add(document)
            await session.commit()
            await session.refresh(document)
            return document

    async def process_document(self, document_id: uuid.UUID) -> None:
        """Index a document. Never raises: failures are recorded on the document row."""
        try:
            await self._set_status(document_id, "processing", error=None)
            await self._index(document_id)
        except Exception as exc:
            message = exc.message if isinstance(exc, AppError) else "Unexpected processing error."
            if not isinstance(exc, AppError):
                logger.exception("Indexing failed for document %s", document_id)
            await self._set_status(document_id, "failed", error=message)

    async def _index(self, document_id: uuid.UUID) -> None:
        async with self._session_factory() as session:
            document = await session.get(Document, document_id)
            if document is None:
                raise NotFoundError("Document not found")
            path = Path(document.stored_path)
            if not await asyncio.to_thread(path.exists):
                raise DocumentProcessingError("The stored file is missing; please upload it again.")
            data = await asyncio.to_thread(path.read_bytes)
            extracted = await asyncio.to_thread(extract, data, document.source_type)
            is_markdown = extracted.heading_style == "markdown"
            pages = [
                PageText(clean_text(p.text, markdown=is_markdown), p.page) for p in extracted.pages
            ]
            chunks = chunk_document(
                pages,
                chunk_size=self._settings.rag_chunk_size,
                overlap=self._settings.rag_chunk_overlap,
                heading_style=extracted.heading_style,
                title=document.title,
            )
            if not chunks:
                raise DocumentProcessingError("The document does not contain any readable text.")

            embed_texts = [
                f"{document.title}\n{c.section or ''}\n{c.content}".strip() for c in chunks
            ]
            vectors: list[list[float]] = []
            for start in range(0, len(embed_texts), _EMBED_BATCH):
                vectors.extend(
                    await self._embeddings.embed_documents(
                        embed_texts[start : start + _EMBED_BATCH]
                    )
                )

            now = datetime.now(UTC)
            suspicious_chunks = 0
            await session.execute(
                delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
            )
            for chunk, vector in zip(chunks, vectors, strict=True):
                markers = find_injection_markers(chunk.content)
                suspicious_chunks += bool(markers)
                session.add(
                    DocumentChunk(
                        document_id=document_id,
                        chunk_index=chunk.index,
                        content=chunk.content,
                        page=chunk.page,
                        section=chunk.section,
                        source_type=document.source_type,
                        token_estimate=chunk.token_estimate,
                        embedding=vector,
                        meta={
                            "document_id": str(document_id),
                            "filename": document.filename,
                            "page": chunk.page,
                            "section": chunk.section,
                            "chunk_index": chunk.index,
                            "source_type": document.source_type,
                            "created_at": now.isoformat(),
                            "suspicious": bool(markers),
                            "injection_markers": markers,
                        },
                    )
                )
            document.status = "indexed"
            document.error = None
            document.chunk_count = len(chunks)
            document.page_count = extracted.page_count
            document.indexed_at = now
            document.meta = {
                **(document.meta or {}),
                "suspicious_chunks": suspicious_chunks,
                "characters": sum(len(c.content) for c in chunks),
            }
            await session.commit()
            logger.info("Indexed document %s into %d chunks", document_id, len(chunks))

    async def _set_status(self, document_id: uuid.UUID, status: str, *, error: str | None) -> None:
        async with self._session_factory() as session:
            document = await session.get(Document, document_id)
            if document is not None:
                document.status = status
                document.error = error
                await session.commit()

    async def mark_for_reindex(self, document_id: uuid.UUID) -> Document:
        async with self._session_factory() as session:
            document = await session.get(Document, document_id)
            if document is None:
                raise NotFoundError("Document not found")
            if document.status == "processing":
                raise ConflictError("This document is already being indexed.")
            document.status = "pending"
            document.error = None
            await session.commit()
            await session.refresh(document)
            return document

    async def delete_document(self, document_id: uuid.UUID) -> None:
        async with self._session_factory() as session:
            document = await session.get(Document, document_id)
            if document is None:
                raise NotFoundError("Document not found")
            path = Path(document.stored_path)
            await session.delete(document)
            await session.commit()
        try:
            await asyncio.to_thread(path.unlink, missing_ok=True)
        except OSError:
            logger.warning("Could not delete stored file for document %s", document_id)
