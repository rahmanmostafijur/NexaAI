"""Shared FastAPI dependencies: settings, services, authentication, authorization."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.services import AgentServices
from app.core.config import Settings, get_settings
from app.core.errors import ForbiddenError, UnauthorizedError
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import User
from app.repositories.users import UserRepository

_bearer = HTTPBearer(auto_error=False)

SettingsDep = Annotated[Settings, Depends(get_settings)]
DbDep = Annotated[AsyncSession, Depends(get_db)]


def get_services(request: Request) -> AgentServices:
    return request.app.state.services


ServicesDep = Annotated[AgentServices, Depends(get_services)]


async def get_current_user(
    session: DbDep,
    settings: SettingsDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise UnauthorizedError("Authentication required.")
    claims = decode_access_token(credentials.credentials, settings)
    user = await UserRepository(session).get(claims.user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("Your account is not active.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def require_admin(user: CurrentUser) -> User:
    if user.role != "admin":
        raise ForbiddenError("Administrator access is required.")
    return user


AdminUser = Annotated[User, Depends(require_admin)]


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"
