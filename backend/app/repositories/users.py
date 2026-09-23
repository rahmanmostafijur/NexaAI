from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: uuid.UUID) -> User | None:
        return await self._session.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        return await self._session.scalar(select(User).where(User.email == email.lower()))

    async def create(self, *, email: str, full_name: str, password_hash: str, role: str) -> User:
        user = User(
            email=email.lower(), full_name=full_name, password_hash=password_hash, role=role
        )
        self._session.add(user)
        await self._session.flush()
        return user

    async def count(self) -> int:
        return int(await self._session.scalar(select(func.count(User.id))) or 0)
