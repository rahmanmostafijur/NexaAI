from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.models import Conversation, Message


class ConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_user(
        self, user_id: uuid.UUID, limit: int = 100
    ) -> list[tuple[Conversation, int]]:
        counts = (
            select(Message.conversation_id, func.count(Message.id).label("n"))
            .group_by(Message.conversation_id)
            .subquery()
        )
        # Inner join: conversations whose only message failed (and was removed) stay
        # reachable by id for a retry, but do not clutter the sidebar.
        rows = await self._session.execute(
            select(Conversation, counts.c.n)
            .join(counts, counts.c.conversation_id == Conversation.id)
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.updated_at.desc())
            .limit(limit)
        )
        return [(conversation, int(count)) for conversation, count in rows.all()]

    async def get_for_user(self, conversation_id: uuid.UUID, user_id: uuid.UUID) -> Conversation:
        """Ownership is enforced here: other users' conversations look like 404s."""
        conversation = await self._session.scalar(
            select(Conversation).where(
                Conversation.id == conversation_id, Conversation.user_id == user_id
            )
        )
        if conversation is None:
            raise NotFoundError("Conversation not found")
        return conversation

    async def create(self, user_id: uuid.UUID, title: str) -> Conversation:
        conversation = Conversation(user_id=user_id, title=title[:200] or "New conversation")
        self._session.add(conversation)
        await self._session.flush()
        return conversation

    async def rename(self, conversation: Conversation, title: str) -> Conversation:
        conversation.title = title[:200]
        await self._session.flush()
        return conversation

    async def touch(self, conversation_id: uuid.UUID) -> None:
        conversation = await self._session.get(Conversation, conversation_id)
        if conversation is not None:
            conversation.updated_at = datetime.now(UTC)

    async def delete(self, conversation: Conversation) -> None:
        await self._session.delete(conversation)

    async def message_count(self, conversation_id: uuid.UUID) -> int:
        return int(
            await self._session.scalar(
                select(func.count(Message.id)).where(Message.conversation_id == conversation_id)
            )
            or 0
        )


class MessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        conversation_id: uuid.UUID,
        role: str,
        content: str,
        details: dict[str, Any] | None = None,
    ) -> Message:
        message = Message(
            conversation_id=conversation_id, role=role, content=content, details=details
        )
        self._session.add(message)
        await self._session.flush()
        await self._session.refresh(message)
        return message

    async def list(self, conversation_id: uuid.UUID) -> list[Message]:
        rows = await self._session.scalars(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at, Message.id)
        )
        return list(rows)

    async def recent(self, conversation_id: uuid.UUID, limit: int) -> list[Message]:
        if limit <= 0:
            return []
        rows = await self._session.scalars(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        return list(reversed(list(rows)))

    async def delete(self, message_id: uuid.UUID) -> None:
        await self._session.execute(delete(Message).where(Message.id == message_id))
