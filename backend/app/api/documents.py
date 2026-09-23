"""Knowledge-base administration: upload, list, inspect, reindex, delete."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, File, Form, Query, Request, Response, UploadFile

from app.api.deps import AdminUser, CurrentUser, DbDep, ServicesDep, SettingsDep
from app.core.errors import PayloadTooLargeError
from app.core.rate_limit import rate_limiter
from app.repositories.documents import DocumentRepository
from app.schemas.documents import ChunkList, ChunkOut, DocumentList, DocumentOut

router = APIRouter(prefix="/documents", tags=["documents"])

_MULTIPART_OVERHEAD = 64 * 1024


@router.post("", response_model=DocumentOut, status_code=201)
async def upload_document(
    request: Request,
    background: BackgroundTasks,
    user: AdminUser,
    services: ServicesDep,
    settings: SettingsDep,
    file: Annotated[UploadFile, File()],
    title: Annotated[str | None, Form(max_length=300)] = None,
) -> DocumentOut:
    await rate_limiter.hit(f"upload:{user.id}", settings.rate_limit_upload_per_minute)
    declared = int(request.headers.get("content-length") or 0)
    if declared > settings.max_upload_bytes + _MULTIPART_OVERHEAD:
        raise PayloadTooLargeError(f"File exceeds the {settings.max_upload_mb} MB limit.")
    # Bounded read: never load more than the limit into memory.
    data = await file.read(settings.max_upload_bytes + 1)
    document = await services.ingestion.create_document(
        data=data,
        filename=file.filename or "document",
        content_type=file.content_type,
        title=title,
        uploaded_by=user.id,
    )
    background.add_task(services.ingestion.process_document, document.id)
    return DocumentOut.model_validate(document)


@router.get("", response_model=DocumentList)
async def list_documents(user: CurrentUser, session: DbDep) -> DocumentList:
    documents = await DocumentRepository(session).list()
    return DocumentList(
        items=[DocumentOut.model_validate(d) for d in documents], total=len(documents)
    )


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document(document_id: uuid.UUID, user: CurrentUser, session: DbDep) -> DocumentOut:
    return DocumentOut.model_validate(await DocumentRepository(session).get(document_id))


@router.get("/{document_id}/chunks", response_model=ChunkList)
async def list_chunks(
    document_id: uuid.UUID,
    user: CurrentUser,
    session: DbDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ChunkList:
    repository = DocumentRepository(session)
    await repository.get(document_id)
    chunks, total = await repository.chunks(document_id, limit=limit, offset=offset)
    return ChunkList(items=[ChunkOut.model_validate(c) for c in chunks], total=total)


@router.post("/{document_id}/reindex", response_model=DocumentOut)
async def reindex_document(
    document_id: uuid.UUID, background: BackgroundTasks, user: AdminUser, services: ServicesDep
) -> DocumentOut:
    document = await services.ingestion.mark_for_reindex(document_id)
    background.add_task(services.ingestion.process_document, document.id)
    return DocumentOut.model_validate(document)


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    document_id: uuid.UUID, user: AdminUser, services: ServicesDep
) -> Response:
    await services.ingestion.delete_document(document_id)
    return Response(status_code=204)
