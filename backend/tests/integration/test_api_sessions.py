"""Cookie-based sessions: rotating refresh tokens, reuse detection, revocation, CSRF."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select, update

from app.core.config import get_settings
from app.db.session import session_scope
from app.models import AuthSession, User

CSRF = {"X-Nexa-CSRF": "1"}
COOKIE = "nexa_refresh"
PASSWORD = "Password123"


def _bearer(response: httpx.Response) -> dict[str, str]:
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
async def fresh_client(app):
    """Independent cookie jars, one per simulated browser."""

    clients: list[httpx.AsyncClient] = []

    def make() -> httpx.AsyncClient:
        http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
        clients.append(http)
        return http

    yield make
    for http in clients:
        await http.aclose()


async def _register(http: httpx.AsyncClient) -> tuple[str, httpx.Response]:
    email = f"sess-{uuid.uuid4().hex[:10]}@test.local"
    response = await http.post(
        "/api/auth/register",
        json={"email": email, "password": PASSWORD, "full_name": "Session User"},
    )
    assert response.status_code == 201, response.text
    return email, response


async def test_login_sets_httponly_strict_cookie_and_keeps_refresh_token_out_of_body(
    fresh_client,
):
    http = fresh_client()
    _, response = await _register(http)

    set_cookie = response.headers["set-cookie"]
    assert f"{COOKIE}=" in set_cookie
    lowered = set_cookie.lower()
    assert "httponly" in lowered
    assert "samesite=strict" in lowered
    assert "path=/api/auth" in lowered
    assert "refresh" not in response.json()
    assert response.json()["expires_in"] == get_settings().access_token_expire_minutes * 60


async def test_refresh_rotates_cookie_and_returns_working_access_token(fresh_client):
    http = fresh_client()
    await _register(http)
    first_cookie = http.cookies.get(COOKIE)

    refreshed = await http.post("/api/auth/refresh", headers=CSRF)

    assert refreshed.status_code == 200, refreshed.text
    assert http.cookies.get(COOKIE) not in (None, first_cookie)
    me = await http.get("/api/auth/me", headers=_bearer(refreshed))
    assert me.status_code == 200


async def test_refresh_requires_csrf_header(fresh_client):
    http = fresh_client()
    await _register(http)

    response = await http.post("/api/auth/refresh")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_failed"


async def test_refresh_rejects_foreign_origin(fresh_client):
    http = fresh_client()
    await _register(http)

    response = await http.post(
        "/api/auth/refresh", headers={**CSRF, "Origin": "https://evil.example"}
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_failed"


async def test_refresh_accepts_configured_origin(fresh_client):
    http = fresh_client()
    await _register(http)
    origin = get_settings().cors_origins[0]

    response = await http.post("/api/auth/refresh", headers={**CSRF, "Origin": origin})

    assert response.status_code == 200


async def test_refresh_without_cookie_is_unauthorized(fresh_client):
    response = await fresh_client().post("/api/auth/refresh", headers=CSRF)

    assert response.status_code == 401


async def test_reused_refresh_token_revokes_the_whole_session(fresh_client, monkeypatch):
    monkeypatch.setattr(get_settings(), "refresh_reuse_grace_seconds", 0)
    http = fresh_client()
    await _register(http)
    stolen = http.cookies.get(COOKIE)
    refreshed = await http.post("/api/auth/refresh", headers=CSRF)
    assert refreshed.status_code == 200

    attacker = fresh_client()
    attacker.cookies.set(COOKIE, stolen, path="/api/auth")
    replay = await attacker.post("/api/auth/refresh", headers=CSRF)

    assert replay.status_code == 401
    assert replay.json()["error"]["code"] == "refresh_reuse_detected"
    # The legitimate holder of the newer token is signed out as well,
    legit = await http.post("/api/auth/refresh", headers=CSRF)
    assert legit.status_code == 401
    # and access tokens minted for the compromised session stop working immediately.
    me = await http.get("/api/auth/me", headers=_bearer(refreshed))
    assert me.status_code == 401


async def test_reuse_inside_grace_window_is_a_retryable_conflict_not_a_revocation(
    fresh_client, monkeypatch
):
    monkeypatch.setattr(get_settings(), "refresh_reuse_grace_seconds", 30)
    http = fresh_client()
    await _register(http)
    previous = http.cookies.get(COOKIE)
    assert (await http.post("/api/auth/refresh", headers=CSRF)).status_code == 200

    racing = fresh_client()
    racing.cookies.set(COOKIE, previous, path="/api/auth")
    response = await racing.post("/api/auth/refresh", headers=CSRF)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "refresh_in_progress"
    assert (await http.post("/api/auth/refresh", headers=CSRF)).status_code == 200


async def test_logout_revokes_session_and_clears_cookie(fresh_client):
    http = fresh_client()
    _, registered = await _register(http)
    old_cookie = http.cookies.get(COOKIE)

    response = await http.post("/api/auth/logout", headers=CSRF)

    assert response.status_code == 204
    assert "max-age=0" in response.headers["set-cookie"].lower()
    assert (await http.get("/api/auth/me", headers=_bearer(registered))).status_code == 401
    replay = fresh_client()
    replay.cookies.set(COOKIE, old_cookie, path="/api/auth")
    assert (await replay.post("/api/auth/refresh", headers=CSRF)).status_code == 401


async def test_logout_is_idempotent_without_a_cookie(fresh_client):
    response = await fresh_client().post("/api/auth/logout", headers=CSRF)

    assert response.status_code == 204


async def test_logout_all_revokes_every_session_of_the_user(fresh_client):
    first = fresh_client()
    email, registered = await _register(first)
    second = fresh_client()
    login = await second.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200

    response = await first.post("/api/auth/logout-all", headers={**_bearer(registered), **CSRF})

    assert response.status_code == 204
    assert (await second.get("/api/auth/me", headers=_bearer(login))).status_code == 401
    assert (await second.post("/api/auth/refresh", headers=CSRF)).status_code == 401


async def test_change_password_revokes_other_sessions_and_keeps_current_one(fresh_client):
    first = fresh_client()
    email, registered = await _register(first)
    second = fresh_client()
    other = await second.post("/api/auth/login", json={"email": email, "password": PASSWORD})

    response = await first.post(
        "/api/auth/change-password",
        headers=_bearer(registered),
        json={"current_password": PASSWORD, "new_password": "NewPassword456"},
    )

    assert response.status_code == 200, response.text
    assert (await first.get("/api/auth/me", headers=_bearer(response))).status_code == 200
    assert (await first.get("/api/auth/me", headers=_bearer(registered))).status_code == 401
    assert (await second.get("/api/auth/me", headers=_bearer(other))).status_code == 401
    assert (await second.post("/api/auth/refresh", headers=CSRF)).status_code == 401
    old = await fresh_client().post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert old.status_code == 401
    new = await fresh_client().post(
        "/api/auth/login", json={"email": email, "password": "NewPassword456"}
    )
    assert new.status_code == 200


async def test_change_password_rejects_wrong_current_password(fresh_client):
    http = fresh_client()
    _, registered = await _register(http)

    response = await http.post(
        "/api/auth/change-password",
        headers=_bearer(registered),
        json={"current_password": "wrong-password-1", "new_password": "NewPassword456"},
    )

    assert response.status_code == 401
    assert (await http.get("/api/auth/me", headers=_bearer(registered))).status_code == 200


async def test_change_password_enforces_password_strength(fresh_client):
    http = fresh_client()
    _, registered = await _register(http)

    response = await http.post(
        "/api/auth/change-password",
        headers=_bearer(registered),
        json={"current_password": PASSWORD, "new_password": "onlyletters"},
    )

    assert response.status_code == 422


async def test_expired_session_cannot_refresh_or_authenticate(fresh_client):
    http = fresh_client()
    email, registered = await _register(http)
    async with session_scope() as session:
        user_id = await session.scalar(select(User.id).where(User.email == email))
        await session.execute(
            update(AuthSession)
            .where(AuthSession.user_id == user_id)
            .values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
        )

    assert (await http.post("/api/auth/refresh", headers=CSRF)).status_code == 401
    assert (await http.get("/api/auth/me", headers=_bearer(registered))).status_code == 401


async def test_deactivated_user_cannot_refresh(fresh_client):
    http = fresh_client()
    email, _ = await _register(http)
    async with session_scope() as session:
        await session.execute(update(User).where(User.email == email).values(is_active=False))

    assert (await http.post("/api/auth/refresh", headers=CSRF)).status_code == 401


async def test_access_token_without_session_claim_is_rejected(client):
    import jwt

    settings = get_settings()
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "role": "user",
            "iat": now,
            "exp": now + timedelta(minutes=5),
            "iss": "nexa-agent",
        },
        settings.jwt_secret.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )

    response = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
