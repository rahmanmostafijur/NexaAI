from __future__ import annotations

import uuid

from fastapi import APIRouter, Response

from app.api.deps import CurrentUser, DbDep
from app.repositories.conversations import ConversationRepository, MessageRepository
from app.schemas.chat import MessageOut
from app.schemas.conversations import ConversationDetail, ConversationSummary, ConversationUpdate

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("", response_model=list[ConversationSummary])
async def list_conversations(user: CurrentUser, session: DbDep) -> list[ConversationSummary]:
    rows = await ConversationRepository(session).list_for_user(user.id)
    return [
        ConversationSummary(
            id=c.id,
            title=c.title,
            created_at=c.created_at,
            updated_at=c.updated_at,
            message_count=count,
        )
        for c, count in rows
    ]


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: uuid.UUID, user: CurrentUser, session: DbDep
) -> ConversationDetail:
    conversation = await ConversationRepository(session).get_for_user(conversation_id, user.id)
    messages = await MessageRepository(session).list(conversation.id)
    return ConversationDetail(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        messages=[MessageOut.model_validate(m) for m in messages],
    )


@router.patch("/{conversation_id}", response_model=ConversationSummary)
async def rename_conversation(
    conversation_id: uuid.UUID, body: ConversationUpdate, user: CurrentUser, session: DbDep
) -> ConversationSummary:
    repository = ConversationRepository(session)
    conversation = await repository.get_for_user(conversation_id, user.id)
    await repository.rename(conversation, body.title)
    await session.refresh(conversation)
    return ConversationSummary(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        message_count=await repository.message_count(conversation.id),
    )


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: uuid.UUID, user: CurrentUser, session: DbDep
) -> Response:
    repository = ConversationRepository(session)
    conversation = await repository.get_for_user(conversation_id, user.id)
    await repository.delete(conversation)
    return Response(status_code=204)
