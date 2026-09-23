"""Health, system info, schema browser, observability and conversation management."""

from tests.conftest import register_user


async def test_health_reports_database_and_llm(client) -> None:
    body = (await client.get("/api/health")).json()
    assert body == {"status": "ok", "database": True, "llm_configured": False}


async def test_system_info_requires_auth(client, user_headers) -> None:
    assert (await client.get("/api/system/info")).status_code == 401
    info = (await client.get("/api/system/info", headers=user_headers)).json()
    assert info["embedding_provider"] == "hashing"
    assert ".pdf" in info["allowed_extensions"]


async def test_schema_browser_lists_business_tables(client, admin_headers) -> None:
    schema = (await client.get("/api/schema", headers=admin_headers)).json()
    assert schema["schema"] == "commerce"
    tables = {t["name"]: t for t in schema["tables"]}
    assert len(tables) == 9
    customer_fk = next(c for c in tables["orders"]["columns"] if c["name"] == "customer_id")
    assert customer_fk["foreign_key"] == {"table": "customers", "column": "id"}
    summary = (await client.get("/api/schema/tables", headers=admin_headers)).json()
    assert {t["name"] for t in summary} == set(tables)


async def test_agent_runs_and_stats_are_scoped_per_user(client, admin_headers) -> None:
    alice = await register_user(client, "Alice")
    bob = await register_user(client, "Bob")
    await client.post("/api/chat", headers=alice, json={"message": "Hello there"})

    alice_runs = (await client.get("/api/agent/runs", headers=alice)).json()
    assert len(alice_runs) == 1 and alice_runs[0]["status"] == "success"
    assert (await client.get("/api/agent/runs", headers=bob)).json() == []
    run_id = alice_runs[0]["id"]
    assert (await client.get(f"/api/agent/runs/{run_id}", headers=bob)).status_code == 404
    assert (await client.get(f"/api/agent/runs/{run_id}", headers=admin_headers)).status_code == 200

    stats = (await client.get("/api/agent/stats", headers=alice)).json()
    assert stats["total_runs"] == 1 and stats["success_rate"] == 1.0
    assert stats["routes"] == {"GENERAL": 1} and stats["languages"] == {"en": 1}


async def test_conversation_rename_and_delete(client, user_headers) -> None:
    created = await client.post("/api/chat", headers=user_headers, json={"message": "Hi!"})
    conversation_id = created.json()["conversation_id"]
    renamed = await client.patch(
        f"/api/conversations/{conversation_id}",
        headers=user_headers,
        json={"title": "  Weekly   sales  "},
    )
    assert renamed.json()["title"] == "Weekly sales"
    assert renamed.json()["message_count"] == 2
    listed = (await client.get("/api/conversations", headers=user_headers)).json()
    assert listed[0]["id"] == conversation_id
    assert (
        await client.delete(f"/api/conversations/{conversation_id}", headers=user_headers)
    ).status_code == 204
    assert (
        await client.get(f"/api/conversations/{conversation_id}", headers=user_headers)
    ).status_code == 404
