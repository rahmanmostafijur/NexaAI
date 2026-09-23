"""Text-to-SQL against the real seeded database and the real read-only role."""

import pytest

from app.core.config import get_settings
from app.core.errors import SQLExecutionError, SQLSafetyError
from app.db.session import get_readonly_pool, get_session_factory
from app.sql.catalog import SchemaCatalog
from app.sql.executor import SQLExecutor
from app.sql.schema_retriever import SchemaRetriever
from app.sql.service import SQLNotAnswerableError, SQLService
from tests.fakes import HashingEmbeddings, ScriptedLLM

pytestmark = pytest.mark.usefixtures("database")


def executor(timeout_ms: int = 5000, max_rows: int = 200) -> SQLExecutor:
    return SQLExecutor(get_readonly_pool, timeout_ms=timeout_ms, max_rows=max_rows)


def service(llm: ScriptedLLM) -> SQLService:
    return SQLService(
        llm=llm,
        catalog=SchemaCatalog(get_session_factory(), "commerce"),
        retriever=SchemaRetriever(HashingEmbeddings()),
        executor=executor(),
        max_rows=200,
        max_corrections=2,
    )


async def test_catalog_describes_tables_keys_and_comments() -> None:
    snapshot = await SchemaCatalog(get_session_factory(), "commerce").snapshot()
    assert set(snapshot.tables) == {
        "categories",
        "customers",
        "inventory",
        "order_items",
        "orders",
        "payments",
        "products",
        "returns",
        "reviews",
    }
    orders = snapshot.tables["orders"]
    assert "Revenue" in (orders.description or "")
    assert orders.column("id").is_primary_key
    assert orders.column("customer_id").foreign_key.table == "customers"
    assert any(index.name == "ix_orders_order_date" for index in orders.indexes)
    assert "FK -> customers.id" in snapshot.render(["orders"])


async def test_executor_returns_json_safe_rows_and_truncates() -> None:
    result = await executor(max_rows=5).execute(
        "SELECT id, total_amount, order_date FROM orders ORDER BY id LIMIT 50"
    )
    assert result.columns == ["id", "total_amount", "order_date"]
    assert result.row_count == 5 and result.truncated
    assert isinstance(result.rows[0][1], int | float)
    assert isinstance(result.rows[0][2], str)


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO categories (id, name) VALUES (999, 'hack')",
        "UPDATE customers SET full_name = 'x'",
        "DELETE FROM orders",
        "SELECT * FROM public.users",
        "SELECT * FROM public.agent_runs",
    ],
)
async def test_database_role_blocks_writes_and_app_tables(sql: str) -> None:
    """Defence in depth: even SQL that bypasses the validator cannot write or read app data."""
    with pytest.raises(SQLExecutionError) as error:
        await executor().execute(sql)
    assert error.value.code == "sql_permission_denied"
    assert not error.value.correctable


async def test_statement_timeout_is_enforced() -> None:
    with pytest.raises(SQLExecutionError) as error:
        await executor(timeout_ms=200).execute("SELECT pg_sleep(3)")
    assert error.value.code == "sql_timeout"


async def test_self_correction_fixes_an_invalid_column() -> None:
    llm = ScriptedLLM()
    llm.sql["customers"] = "SELECT COUNT(*) AS n FROM customers WHERE nation = 'Bangladesh'"
    llm.corrections = ["SELECT COUNT(*) AS n FROM customers WHERE country = 'Bangladesh'"]
    run = await service(llm).run("How many customers are in Bangladesh?")
    assert len(run.attempts) == 2
    assert run.attempts[0].error and "nation" in run.attempts[0].error
    assert run.result.rows[0][0] > 0
    assert run.sql.endswith("LIMIT 200")


async def test_retries_are_bounded() -> None:
    llm = ScriptedLLM()
    llm.sql["customers"] = "SELECT missing_column FROM customers"
    llm.corrections = ["SELECT still_missing FROM customers", "SELECT nope FROM customers"]
    with pytest.raises(SQLSafetyError):
        await service(llm).run("How many customers?")
    assert sum(1 for kind, _ in llm.calls if kind == "sql_correction") == 2


async def test_unsafe_generated_sql_is_never_retried() -> None:
    llm = ScriptedLLM()
    llm.sql["delete"] = "DELETE FROM orders"
    with pytest.raises(SQLSafetyError):
        await service(llm).run("delete all orders")
    assert not any(kind == "sql_correction" for kind, _ in llm.calls)


async def test_model_can_decline_unanswerable_questions() -> None:
    class DecliningLLM(ScriptedLLM):
        async def complete(self, messages, **kwargs):
            from app.llm.base import LLMResponse

            return LLMResponse('{"sql": null, "explanation": "No salary data exists."}')

    with pytest.raises(SQLNotAnswerableError, match="salary"):
        await service(DecliningLLM()).run("What is the CEO's salary?")


async def test_schema_retrieval_selects_relevant_tables_only() -> None:
    snapshot = await SchemaCatalog(get_session_factory(), "commerce").snapshot()
    retriever = SchemaRetriever(HashingEmbeddings())
    tables = await retriever.select_tables("Which category had the most revenue?", snapshot)
    assert {"categories", "orders"} <= set(tables)
    assert "reviews" not in tables and "payments" not in tables
    stock = await retriever.select_tables("এই product-এর stock কত?", snapshot)
    assert "inventory" in stock and "products" in stock


async def test_readonly_role_is_configured_in_the_database() -> None:
    pool = await get_readonly_pool()
    async with pool.acquire() as connection:
        assert await connection.fetchval("SHOW default_transaction_read_only") == "on"
        assert await connection.fetchval("SELECT current_user") == get_settings().sql_readonly_user
