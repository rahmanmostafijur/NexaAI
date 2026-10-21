"""Password hashing and JWT access tokens."""

from __future__ import annotations

import hashlib
import secrets
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
    session_id: uuid.UUID


def new_refresh_token() -> str:
    """256 bits of randomness; opaque to the client."""
    return secrets.token_urlsafe(32)


def hash_refresh_token(token: str) -> str:
    """Only this digest is stored, so a database leak does not yield usable tokens."""
    return hashlib.sha256(token.encode()).hexdigest()


def create_access_token(
    user_id: uuid.UUID, role: str, session_id: uuid.UUID, settings: Settings
) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "sid": str(session_id),
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
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
            options={"require": ["sub", "sid", "exp", "iat"]},
        )
        return TokenClaims(
            user_id=uuid.UUID(payload["sub"]),
            role=str(payload.get("role", "user")),
            session_id=uuid.UUID(payload["sid"]),
        )
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("Your session has expired. Please sign in again.") from exc
    except (jwt.InvalidTokenError, ValueError, KeyError) as exc:
        raise UnauthorizedError("Invalid authentication token.") from exc
