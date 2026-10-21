"""Liveness (`/api/health`) vs readiness (`/api/ready`: database, migrations, optional Redis)."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import session_scope


async def test_ready_reports_every_dependency_when_all_is_well(client) -> None:
    response = await client.get("/api/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"]["database"] is True
    assert body["checks"]["migrations"] is True
    assert body["checks"]["redis"] is None  # not configured, so not checked


async def test_ready_needs_no_authentication(client) -> None:
    assert (await client.get("/api/ready")).status_code == 200


async def test_not_ready_while_migrations_are_behind(client) -> None:
    async with session_scope() as session:
        original = await session.scalar(text("SELECT version_num FROM alembic_version"))
        await session.execute(text("UPDATE alembic_version SET version_num = '0001'"))
    try:
        response = await client.get("/api/ready")
    finally:
        async with session_scope() as session:
            await session.execute(
                text("UPDATE alembic_version SET version_num = :v"), {"v": original}
            )

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["migrations"] is False
    assert body["checks"]["database"] is True


async def test_not_ready_when_a_configured_redis_is_unreachable(client, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "redis_url", "redis://127.0.0.1:1/0")

    response = await client.get("/api/ready")

    assert response.status_code == 503
    assert response.json()["checks"]["redis"] is False


async def test_ready_checks_a_configured_redis(client, redis_url, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "redis_url", redis_url)

    response = await client.get("/api/ready")

    assert response.status_code == 200
    assert response.json()["checks"]["redis"] is True


async def test_liveness_stays_up_even_when_a_dependency_is_down(client, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "redis_url", "redis://127.0.0.1:1/0")

    assert (await client.get("/api/health")).status_code == 200


@pytest.mark.parametrize("path", ["/api/health", "/api/ready"])
async def test_probes_do_not_leak_connection_details(client, path) -> None:
    body = (await client.get(path)).text.lower()

    assert "postgresql" not in body and "password" not in body and "redis://" not in body
