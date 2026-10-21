"""Server-side sessions with rotating, single-use refresh tokens.

Each sign-in creates an `AuthSession`. Its refresh token is used exactly once: refreshing
marks it used and issues a successor. Presenting an already-used token after the short
grace window means the token was copied, so the whole session is revoked and the
legitimate holder has to sign in again. Access tokens carry the session id and are
rejected as soon as the session is revoked.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError, UnauthorizedError
from app.core.security import hash_refresh_token, new_refresh_token
from app.models import AuthSession, RefreshToken, User

# Revoked/expired sessions are kept briefly for forensics, then purged.
_PURGE_AFTER = timedelta(days=7)


class RefreshInProgressError(AppError):
    """The token was rotated a moment ago; the caller should retry with the new cookie."""

    status_code = 409
    code = "refresh_in_progress"
    retryable = True


@dataclass(frozen=True)
class IssuedSession:
    session: AuthSession
    refresh_token: str


def _now() -> datetime:
    return datetime.now(UTC)


class SessionService:
    def __init__(self, db: AsyncSession, settings: Settings) -> None:
        self._db = db
        self._settings = settings

    async def start(
        self, user: User, *, user_agent: str | None = None, ip: str | None = None
    ) -> IssuedSession:
        now = _now()
        session = AuthSession(
            user_id=user.id,
            expires_at=now + timedelta(days=self._settings.session_max_days),
            last_used_at=now,
            user_agent=(user_agent or "")[:300] or None,
            ip=(ip or "")[:64] or None,
        )
        self._db.add(session)
        await self._db.flush()
        return IssuedSession(session, await self._issue_token(session, now))

    async def rotate(self, raw_token: str) -> tuple[IssuedSession, User]:
        """Exchange a refresh token for a new one. Raises when the token is not acceptable."""
        now = _now()
        token = await self._db.scalar(
            select(RefreshToken)
            .where(RefreshToken.token_hash == hash_refresh_token(raw_token))
            .with_for_update()
        )
        if token is None:
            raise UnauthorizedError("Please sign in again.", code="invalid_refresh_token")
        session = await self._db.get(AuthSession, token.session_id)
        if session is None or session.revoked_at is not None or session.expires_at <= now:
            raise UnauthorizedError("Your session has ended. Please sign in again.")

        if token.used_at is not None:
            if (now - token.used_at).total_seconds() <= self._settings.refresh_reuse_grace_seconds:
                raise RefreshInProgressError("Another request is refreshing this session.")
            await self._revoke(session.id, "reuse_detected", now)
            await self._db.commit()  # persist the revocation even though we raise
            raise UnauthorizedError(
                "This session was signed out for your safety. Please sign in again.",
                code="refresh_reuse_detected",
            )
        if token.expires_at <= now:
            raise UnauthorizedError("Your session has expired. Please sign in again.")

        user = await self._db.get(User, session.user_id)
        if user is None or not user.is_active:
            await self._revoke(session.id, "inactive_user", now)
            await self._db.commit()
            raise UnauthorizedError("Your account is not active.")

        token.used_at = now
        session.last_used_at = now
        return IssuedSession(session, await self._issue_token(session, now)), user

    async def is_active(self, session_id: uuid.UUID) -> bool:
        session = await self._db.get(AuthSession, session_id)
        return session is not None and session.revoked_at is None and session.expires_at > _now()

    async def revoke_by_token(self, raw_token: str, reason: str = "logout") -> None:
        session_id = await self._db.scalar(
            select(RefreshToken.session_id).where(
                RefreshToken.token_hash == hash_refresh_token(raw_token)
            )
        )
        if session_id is not None:
            await self._revoke(session_id, reason, _now())

    async def revoke_session(self, session_id: uuid.UUID, reason: str = "logout") -> None:
        await self._revoke(session_id, reason, _now())

    async def revoke_all(
        self, user_id: uuid.UUID, reason: str, *, except_session: uuid.UUID | None = None
    ) -> None:
        statement = (
            update(AuthSession)
            .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=_now(), revoked_reason=reason)
        )
        if except_session is not None:
            statement = statement.where(AuthSession.id != except_session)
        await self._db.execute(statement)

    async def purge_expired(self) -> int:
        cutoff = _now() - _PURGE_AFTER
        result = await self._db.execute(
            delete(AuthSession).where(
                (AuthSession.expires_at < cutoff)
                | (AuthSession.revoked_at.is_not(None) & (AuthSession.revoked_at < cutoff))
            )
        )
        return int(getattr(result, "rowcount", 0) or 0)

    async def _revoke(self, session_id: uuid.UUID, reason: str, now: datetime) -> None:
        await self._db.execute(
            update(AuthSession)
            .where(AuthSession.id == session_id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=now, revoked_reason=reason)
        )

    async def _issue_token(self, session: AuthSession, now: datetime) -> str:
        raw = new_refresh_token()
        expires = min(
            now + timedelta(days=self._settings.refresh_token_expire_days), session.expires_at
        )
        self._db.add(
            RefreshToken(
                session_id=session.id, token_hash=hash_refresh_token(raw), expires_at=expires
            )
        )
        await self._db.flush()
        return raw
