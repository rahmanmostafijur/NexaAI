from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, ServicesDep, SettingsDep
from app.core.rate_limit import rate_limiter
from app.schemas.documents import SearchResponse, SearchResult

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.get("/search", response_model=SearchResponse)
async def search_knowledge(
    user: CurrentUser,
    services: ServicesDep,
    settings: SettingsDep,
    q: Annotated[str, Query(min_length=1, max_length=500)],
    top_k: Annotated[int, Query(ge=1, le=20)] = 5,
    document_id: uuid.UUID | None = None,
) -> SearchResponse:
    await rate_limiter.hit(f"search:{user.id}", settings.rate_limit_chat_per_minute * 3)
    chunks = await services.retriever.search(
        q.strip(), top_k=top_k, document_ids=[document_id] if document_id else None
    )
    return SearchResponse(
        query=q,
        results=[
            SearchResult(
                chunk_id=c.chunk_id,
                document_id=c.document_id,
                title=c.title,
                filename=c.filename,
                page=c.page,
                section=c.section,
                content=c.content,
                score=round(c.score, 4),
                vector_score=c.vector_score,
                keyword_score=c.keyword_score,
            )
            for c in chunks
        ],
    )
