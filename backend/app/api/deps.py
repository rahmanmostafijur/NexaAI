"""Shared FastAPI dependencies: settings, services, authentication, authorization."""

from __future__ import annotations

import uuid
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.services import AgentServices
from app.core.config import Settings, get_settings
from app.core.errors import ForbiddenError, UnauthorizedError
from app.core.security import decode_access_token
from app.core.sessions import SessionService
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
    request: Request,
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
    if not await SessionService(session, settings).is_active(claims.session_id):
        raise UnauthorizedError("Your session has ended. Please sign in again.")
    request.state.session_id = claims.session_id
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def require_admin(user: CurrentUser) -> User:
    if user.role != "admin":
        raise ForbiddenError("Administrator access is required.")
    return user


AdminUser = Annotated[User, Depends(require_admin)]


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


CSRF_HEADER = "x-nexa-csrf"


def require_csrf(request: Request, settings: SettingsDep) -> None:
    """Guard for endpoints that act on the refresh cookie (refresh, logout).

    Browsers cannot attach a custom header to a cross-site form post or image request, and a
    cross-origin `fetch` with one triggers a CORS preflight we never approve. On top of that
    the cookie is `SameSite=Strict`, and a mismatching `Origin` header is rejected outright.
    """
    if request.headers.get(CSRF_HEADER) != "1":
        raise ForbiddenError("Missing CSRF header.", code="csrf_failed")
    origin = request.headers.get("origin")
    if origin is None:
        return
    same_host = urlsplit(origin).netloc == request.headers.get("host", "")
    if origin not in settings.cors_origins and not same_host:
        raise ForbiddenError("Cross-origin request rejected.", code="csrf_failed")


CsrfGuard = Depends(require_csrf)


def session_id_of(request: Request) -> uuid.UUID:
    """The session behind the access token that authenticated this request."""
    return request.state.session_id  # type: ignore[no-any-return]
