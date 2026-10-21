from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Request, Response

from app.api.deps import (
    CsrfGuard,
    CurrentUser,
    DbDep,
    SettingsDep,
    client_ip,
)
from app.core.config import Settings
from app.core.errors import ConflictError, ForbiddenError, UnauthorizedError
from app.core.rate_limit import rate_limiter
from app.core.security import create_access_token, hash_password, verify_password
from app.core.sessions import IssuedSession, SessionService
from app.models import User
from app.repositories.users import UserRepository
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "nexa_refresh"
# The cookie is only ever sent to the auth endpoints, never to chat/documents/etc.
_COOKIE_PATH = "/api/auth"

# Verifying against a dummy hash when the user does not exist keeps response
# times similar, so the endpoint does not reveal which emails are registered.
_DUMMY_HASH = hash_password("dummy-password-for-timing")


def _set_refresh_cookie(response: Response, issued: IssuedSession, settings: Settings) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        issued.refresh_token,
        max_age=settings.refresh_token_expire_days * 24 * 3600,
        path=_COOKIE_PATH,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="strict",
    )


def _clear_refresh_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        REFRESH_COOKIE,
        path=_COOKIE_PATH,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="strict",
    )


def _token_response(user: User, issued: IssuedSession, settings: Settings) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(user.id, user.role, issued.session.id, settings),
        expires_in=settings.access_token_expire_minutes * 60,
        user=UserOut.model_validate(user),
    )


async def _sign_in(
    user: User, request: Request, response: Response, db: DbDep, settings: Settings
) -> TokenResponse:
    issued = await SessionService(db, settings).start(
        user, user_agent=request.headers.get("user-agent"), ip=client_ip(request)
    )
    _set_refresh_cookie(response, issued, settings)
    return _token_response(user, issued, settings)


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    session: DbDep,
    settings: SettingsDep,
) -> TokenResponse:
    await rate_limiter.hit(f"login:{client_ip(request)}", settings.rate_limit_auth_per_minute)
    user = await UserRepository(session).get_by_email(body.email)
    password_ok = verify_password(body.password, user.password_hash if user else _DUMMY_HASH)
    if user is None or not password_ok or not user.is_active:
        raise UnauthorizedError("Incorrect email or password.", code="invalid_credentials")
    return await _sign_in(user, request, response, session, settings)


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(
    body: RegisterRequest,
    request: Request,
    response: Response,
    session: DbDep,
    settings: SettingsDep,
) -> TokenResponse:
    if not settings.allow_registration:
        raise ForbiddenError("Registration is disabled.")
    await rate_limiter.hit(f"register:{client_ip(request)}", settings.rate_limit_auth_per_minute)
    users = UserRepository(session)
    if await users.get_by_email(body.email):
        raise ConflictError("An account with this email already exists.")
    user = await users.create(
        email=body.email,
        full_name=body.full_name,
        password_hash=hash_password(body.password),
        role="user",
    )
    return await _sign_in(user, request, response, session, settings)


@router.post("/refresh", response_model=TokenResponse, dependencies=[CsrfGuard])
async def refresh(
    request: Request,
    response: Response,
    session: DbDep,
    settings: SettingsDep,
    refresh_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
) -> TokenResponse:
    await rate_limiter.hit(f"refresh:{client_ip(request)}", settings.rate_limit_auth_per_minute * 6)
    if not refresh_token:
        raise UnauthorizedError("Please sign in.", code="no_refresh_token")
    issued, user = await SessionService(session, settings).rotate(refresh_token)
    _set_refresh_cookie(response, issued, settings)
    return _token_response(user, issued, settings)


@router.post("/logout", status_code=204, dependencies=[CsrfGuard])
async def logout(
    session: DbDep,
    settings: SettingsDep,
    refresh_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
) -> Response:
    """Ends this browser's session. Idempotent: safe to call when already signed out."""
    if refresh_token:
        await SessionService(session, settings).revoke_by_token(refresh_token)
    result = Response(status_code=204)
    _clear_refresh_cookie(result, settings)
    return result


@router.post("/logout-all", status_code=204, dependencies=[CsrfGuard])
async def logout_all(user: CurrentUser, session: DbDep, settings: SettingsDep) -> Response:
    await SessionService(session, settings).revoke_all(user.id, "logout_all")
    result = Response(status_code=204)
    _clear_refresh_cookie(result, settings)
    return result


@router.post("/change-password", response_model=TokenResponse)
async def change_password(
    body: ChangePasswordRequest,
    request: Request,
    response: Response,
    user: CurrentUser,
    session: DbDep,
    settings: SettingsDep,
) -> TokenResponse:
    """Sets a new password, signs every other device out and keeps this one signed in."""
    await rate_limiter.hit(f"password:{user.id}", settings.rate_limit_auth_per_minute)
    if not verify_password(body.current_password, user.password_hash):
        # A distinct code: clients must not mistake this for an expired access token.
        raise UnauthorizedError("Your current password is incorrect.", code="invalid_credentials")
    user.password_hash = hash_password(body.new_password)
    sessions = SessionService(session, settings)
    await sessions.revoke_all(user.id, "password_changed")
    return await _sign_in(user, request, response, session, settings)


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)
