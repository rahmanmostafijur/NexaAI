from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.deps import CurrentUser, DbDep, SettingsDep, client_ip
from app.core.errors import ConflictError, ForbiddenError, UnauthorizedError
from app.core.rate_limit import rate_limiter
from app.core.security import create_access_token, hash_password, verify_password
from app.models import User
from app.repositories.users import UserRepository
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])

# Verifying against a dummy hash when the user does not exist keeps response
# times similar, so the endpoint does not reveal which emails are registered.
_DUMMY_HASH = hash_password("dummy-password-for-timing")


def _token_response(user: User, settings: SettingsDep) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(user.id, user.role, settings),
        expires_in=settings.jwt_expire_minutes * 60,
        user=UserOut.model_validate(user),
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest, request: Request, session: DbDep, settings: SettingsDep
) -> TokenResponse:
    await rate_limiter.hit(f"login:{client_ip(request)}", settings.rate_limit_auth_per_minute)
    user = await UserRepository(session).get_by_email(body.email)
    password_ok = verify_password(body.password, user.password_hash if user else _DUMMY_HASH)
    if user is None or not password_ok or not user.is_active:
        raise UnauthorizedError("Incorrect email or password.")
    return _token_response(user, settings)


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(
    body: RegisterRequest, request: Request, session: DbDep, settings: SettingsDep
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
    return _token_response(user, settings)


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)
