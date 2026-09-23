"""Password hashing and JWT access tokens."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.core.config import Settings
from app.core.errors import UnauthorizedError

# bcrypt only uses the first 72 bytes of a password.
_BCRYPT_MAX_BYTES = 72


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode()[:_BCRYPT_MAX_BYTES], bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode()[:_BCRYPT_MAX_BYTES], password_hash.encode())
    except ValueError:
        return False


@dataclass(frozen=True)
class TokenClaims:
    user_id: uuid.UUID
    role: str


def create_access_token(user_id: uuid.UUID, role: str, settings: Settings) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
        "iss": "nexa-agent",
    }
    return jwt.encode(
        payload, settings.jwt_secret.get_secret_value(), algorithm=settings.jwt_algorithm
    )


def decode_access_token(token: str, settings: Settings) -> TokenClaims:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            issuer="nexa-agent",
            options={"require": ["sub", "exp", "iat"]},
        )
        return TokenClaims(user_id=uuid.UUID(payload["sub"]), role=str(payload.get("role", "user")))
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("Your session has expired. Please sign in again.") from exc
    except (jwt.InvalidTokenError, ValueError, KeyError) as exc:
        raise UnauthorizedError("Invalid authentication token.") from exc
