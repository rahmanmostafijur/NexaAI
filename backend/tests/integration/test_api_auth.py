"""Authentication, authorization, rate limiting and security headers."""

from app.core.config import get_settings
from tests.conftest import register_user


async def test_login_success_and_me(client, admin_headers) -> None:
    response = await client.get("/api/auth/me", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["role"] == "admin"


async def test_login_failures_share_one_generic_message(client) -> None:
    wrong_password = await client.post(
        "/api/auth/login", json={"email": "admin@test.local", "password": "nope"}
    )
    unknown_user = await client.post(
        "/api/auth/login", json={"email": "ghost@test.local", "password": "nope"}
    )
    assert wrong_password.status_code == unknown_user.status_code == 401
    assert wrong_password.json()["error"]["message"] == unknown_user.json()["error"]["message"]


async def test_protected_endpoints_require_a_valid_token(client) -> None:
    assert (await client.get("/api/conversations")).status_code == 401
    bad = await client.get("/api/conversations", headers={"Authorization": "Bearer abc"})
    assert bad.status_code == 401
    assert bad.json()["error"]["code"] == "unauthorized"


async def test_register_rules(client) -> None:
    body = {"email": "dup@test.local", "password": "Password123", "full_name": "Dup User"}
    assert (await client.post("/api/auth/register", json=body)).status_code in (201, 409)
    assert (await client.post("/api/auth/register", json=body)).status_code == 409
    weak = {**body, "email": "weak@test.local", "password": "short"}
    response = await client.post("/api/auth/register", json=weak)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_registration_can_be_disabled(client) -> None:
    settings = get_settings()
    settings.allow_registration = False
    try:
        response = await client.post(
            "/api/auth/register",
            json={"email": "x@test.local", "password": "Password123", "full_name": "X Y"},
        )
        assert response.status_code == 403
    finally:
        settings.allow_registration = True


async def test_regular_users_cannot_use_admin_endpoints(client, user_headers) -> None:
    assert (await client.get("/api/schema", headers=user_headers)).status_code == 403
    upload = await client.post(
        "/api/documents", headers=user_headers, files={"file": ("a.md", b"# hi", "text/markdown")}
    )
    assert upload.status_code == 403
    assert (await client.get("/api/documents", headers=user_headers)).status_code == 200


async def test_login_is_rate_limited(client) -> None:
    settings = get_settings()
    original = settings.rate_limit_auth_per_minute
    settings.rate_limit_auth_per_minute = 2
    try:
        body = {"email": "admin@test.local", "password": "wrong"}
        statuses = [(await client.post("/api/auth/login", json=body)).status_code for _ in range(3)]
        assert statuses[:2] == [401, 401] and statuses[2] == 429
        limited = await client.post("/api/auth/login", json=body)
        assert int(limited.headers["retry-after"]) >= 1
    finally:
        settings.rate_limit_auth_per_minute = original


async def test_security_headers_and_request_id(client) -> None:
    response = await client.get("/api/health", headers={"X-Request-ID": "trace-12345678"})
    assert response.headers["x-request-id"] == "trace-12345678"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    spoofed = await client.get("/api/health", headers={"X-Request-ID": "bad id\nwith newline"})
    assert spoofed.headers["x-request-id"] != "bad id\nwith newline"


async def test_other_users_data_is_invisible(client) -> None:
    alice = await register_user(client, "Alice")
    bob = await register_user(client, "Bob")
    created = await client.post("/api/chat", headers=alice, json={"message": "Hello there"})
    conversation_id = created.json()["conversation_id"]
    assert (
        await client.get(f"/api/conversations/{conversation_id}", headers=bob)
    ).status_code == 404
    delete = await client.delete(f"/api/conversations/{conversation_id}", headers=bob)
    assert delete.status_code == 404
    stream = await client.post(
        "/api/chat/stream", headers=bob, json={"message": "hi", "conversation_id": conversation_id}
    )
    assert stream.status_code == 404
