"""Prometheus metrics: what is exposed, and who may read it."""

from __future__ import annotations

import re

import pytest
from pydantic import SecretStr

from app.core.config import get_settings
from tests.integration.test_api_chat import SQL_ROUTE, stream


def sample(body: str, name: str, **labels: str) -> float | None:
    """Value of one exposition sample, matching the given labels (any order)."""
    for line in body.splitlines():
        if line.startswith("#") or not line.startswith(name):
            continue
        head, _, value = line.rpartition(" ")
        if not re.match(rf"^{re.escape(name)}(\{{|$)", head):
            continue
        if all(f'{k}="{v}"' in head for k, v in labels.items()):
            return float(value)
    return None


async def test_metrics_are_exposed_in_prometheus_format(client) -> None:
    response = await client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "# HELP nexa_http_request_duration_seconds" in response.text


async def test_http_requests_are_counted_by_route_template_not_raw_path(client, admin_headers):
    await client.get("/api/health")
    await client.get("/api/documents/00000000-0000-0000-0000-000000000000", headers=admin_headers)

    body = (await client.get("/metrics")).text

    assert sample(body, "nexa_http_request_duration_seconds_count", route="/api/health") >= 1
    assert 'route="/api/documents/{document_id}"' in body
    assert "00000000-0000-0000-0000-000000000000" not in body


async def test_agent_runs_tokens_and_tool_timings_are_recorded(
    client, user_headers, fake_llm
) -> None:
    before = sample(
        (await client.get("/metrics")).text, "nexa_agent_runs_total", route="SQL", status="success"
    )
    fake_llm.routes["orders"] = SQL_ROUTE

    await stream(client, user_headers, "How many orders were placed last month?")
    body = (await client.get("/metrics")).text

    after = sample(body, "nexa_agent_runs_total", route="SQL", status="success")
    assert after == (before or 0) + 1
    assert sample(body, "nexa_tool_duration_seconds_count", tool="sql", status="completed") >= 1
    assert sample(body, "nexa_llm_tokens_total", type="prompt") > 0
    assert sample(body, "nexa_agent_run_duration_seconds_count", route="SQL") >= 1


async def test_failed_runs_are_counted(client, user_headers, fake_llm) -> None:
    from app.core.errors import LLMUnavailableError

    fake_llm.fail_with = LLMUnavailableError("model down")

    await client.post("/api/chat/stream", headers=user_headers, json={"message": "How many?"})
    body = (await client.get("/metrics")).text

    failed = [
        float(line.rpartition(" ")[2])
        for line in body.splitlines()
        if line.startswith("nexa_agent_runs_total") and 'status="failed"' in line
    ]
    assert sum(failed) >= 1


async def test_a_token_protects_the_endpoint_when_configured(client, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "metrics_token", SecretStr("scrape-secret-token"))

    assert (await client.get("/metrics")).status_code == 401
    wrong = await client.get("/metrics", headers={"Authorization": "Bearer nope"})
    assert wrong.status_code == 401
    right = await client.get("/metrics", headers={"Authorization": "Bearer scrape-secret-token"})
    assert right.status_code == 200


async def test_without_a_token_proxied_requests_are_refused(client) -> None:
    response = await client.get("/metrics", headers={"X-Forwarded-For": "203.0.113.9"})

    assert response.status_code == 403


async def test_metrics_can_be_disabled(client, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "metrics_enabled", False)

    assert (await client.get("/metrics")).status_code == 404


@pytest.mark.parametrize("secret", ["scrape-secret-token"])
async def test_the_scrape_token_never_appears_in_the_output(client, monkeypatch, secret) -> None:
    monkeypatch.setattr(get_settings(), "metrics_token", SecretStr(secret))

    body = (await client.get("/metrics", headers={"Authorization": f"Bearer {secret}"})).text

    assert secret not in body
