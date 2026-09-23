import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from pydantic import ValidationError

from app.agent.types import AgentEvent
from app.api.chat import format_sse, with_heartbeat
from app.core.config import INSECURE_JWT_DEFAULT, Settings
from app.core.errors import RateLimitedError, UnauthorizedError
from app.core.logging import redact
from app.core.rate_limit import SlidingWindowRateLimiter
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.schemas.auth import LoginRequest, RegisterRequest
from app.schemas.chat import ChatRequest

SETTINGS = Settings(jwt_secret="unit-test-secret-that-is-long-enough-123456")


def test_password_hashing() -> None:
    hashed = hash_password("Secret123")
    assert verify_password("Secret123", hashed)
    assert not verify_password("wrong", hashed)
    assert not verify_password("Secret123", "not-a-bcrypt-hash")


def test_jwt_round_trip_and_rejections() -> None:
    user_id = uuid.uuid4()
    claims = decode_access_token(create_access_token(user_id, "admin", SETTINGS), SETTINGS)
    assert claims.user_id == user_id and claims.role == "admin"

    other = Settings(jwt_secret="another-secret-that-is-also-long-enough-99")
    with pytest.raises(UnauthorizedError):
        decode_access_token(create_access_token(user_id, "user", other), SETTINGS)

    expired = jwt.encode(
        {
            "sub": str(user_id),
            "iss": "nexa-agent",
            "iat": datetime.now(UTC) - timedelta(hours=2),
            "exp": datetime.now(UTC) - timedelta(hours=1),
        },
        SETTINGS.jwt_secret.get_secret_value(),
        algorithm="HS256",
    )
    with pytest.raises(UnauthorizedError, match="expired"):
        decode_access_token(expired, SETTINGS)
    with pytest.raises(UnauthorizedError):
        decode_access_token("garbage.token.value", SETTINGS)


async def test_rate_limiter_sliding_window() -> None:
    now = [1000.0]
    limiter = SlidingWindowRateLimiter(clock=lambda: now[0])
    for _ in range(3):
        await limiter.hit("k", limit=3, window_seconds=60)
    with pytest.raises(RateLimitedError) as error:
        await limiter.hit("k", limit=3, window_seconds=60)
    assert error.value.retry_after == 60
    await limiter.hit("other", limit=3, window_seconds=60)  # keys are independent
    now[0] += 61
    await limiter.hit("k", limit=3, window_seconds=60)


@pytest.mark.parametrize(
    ("raw", "leak"),
    [
        ("Authorization: Bearer abc.def.ghi", "abc.def.ghi"),
        ('{"api_key": "sk-live-123"}', "sk-live-123"),
        ("postgresql+asyncpg://nexa:hunter2@db:5432/nexa", "hunter2"),
        ("token=deadbeef", "deadbeef"),
        ("key sk-abcdefghijklmnopqrstuvwxyz", "sk-abcdefghijklmnopqrstuvwxyz"),
    ],
)
def test_logs_redact_secrets(raw: str, leak: str) -> None:
    assert leak not in redact(raw)


def test_production_settings_require_real_secrets() -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings(_env_file=None, environment="production", jwt_secret=INSECURE_JWT_DEFAULT)
    with pytest.raises(ValidationError, match="ADMIN_PASSWORD"):
        Settings(
            _env_file=None,
            environment="production",
            jwt_secret="x" * 40,
            admin_password="ChangeMe123!",
        )
    ok = Settings(
        _env_file=None,
        environment="production",
        jwt_secret="x" * 40,
        admin_password="Strong-Pass-1",
    )
    assert ok.environment == "production"


def test_settings_helpers() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://app:pw@db:5432/nexa",
        sql_readonly_user="ro",
        sql_readonly_password="ro-pw",
        cors_origins="http://a, http://b",
    )
    assert settings.readonly_database_url == "postgresql+asyncpg://ro:ro-pw@db:5432/nexa"
    assert settings.cors_origins == ["http://a", "http://b"]
    assert not Settings(llm_provider="none").llm_configured


def test_sse_formatting_keeps_unicode() -> None:
    frame = format_sse(AgentEvent("token", {"delta": "বিক্রি"}))
    assert frame == 'event: token\ndata: {"delta": "বিক্রি"}\n\n'


async def test_heartbeat_is_sent_while_idle() -> None:
    async def slow_events():
        await asyncio.sleep(0.12)
        yield AgentEvent("done", {"ok": True})

    frames = [frame async for frame in with_heartbeat(slow_events(), interval=0.05)]
    assert frames[0] == ": keep-alive\n\n"
    assert frames[-1].startswith("event: done")


def test_request_validation() -> None:
    assert ChatRequest(message="  hi\x00 there  ").message == "hi there"
    with pytest.raises(ValidationError):
        ChatRequest(message="\x00\x01")
    with pytest.raises(ValidationError):
        ChatRequest(message="x" * 4001)
    assert LoginRequest(email="Admin@Nexa.Local", password="x").email == "admin@nexa.local"
    with pytest.raises(ValidationError):
        LoginRequest(email="not-an-email", password="x")
    with pytest.raises(ValidationError):
        RegisterRequest(email="a@b.co", password="lettersonly", full_name="Ann")
