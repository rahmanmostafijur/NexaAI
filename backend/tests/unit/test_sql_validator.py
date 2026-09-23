import pytest

from app.core.errors import SQLSafetyError
from app.sql.catalog import ColumnInfo, ForeignKey, SchemaSnapshot, TableInfo
from app.sql.schema_retriever import expand_join_path
from app.sql.validator import SQLValidator, is_correctable


def _table(name: str, columns: list[str], fks: dict[str, tuple[str, str]] | None = None):
    fks = fks or {}
    return TableInfo(
        name=name,
        description=None,
        row_estimate=0,
        columns=[
            ColumnInfo(
                c,
                "integer",
                True,
                is_primary_key=c == "id",
                foreign_key=ForeignKey(*fks[c]) if c in fks else None,
            )
            for c in columns
        ],
    )


@pytest.fixture
def snapshot() -> SchemaSnapshot:
    tables = [
        _table("customers", ["id", "full_name", "country", "membership_tier"]),
        _table("categories", ["id", "name"]),
        _table(
            "products",
            ["id", "name", "category_id", "price"],
            {"category_id": ("categories", "id")},
        ),
        _table(
            "orders",
            ["id", "customer_id", "order_date", "status", "total_amount"],
            {"customer_id": ("customers", "id")},
        ),
        _table(
            "order_items",
            ["id", "order_id", "product_id", "quantity", "line_total"],
            {"order_id": ("orders", "id"), "product_id": ("products", "id")},
        ),
    ]
    return SchemaSnapshot("commerce", {t.name: t for t in tables})


@pytest.fixture
def validator(snapshot: SchemaSnapshot) -> SQLValidator:
    return SQLValidator(snapshot, max_rows=200)


VALID = [
    "SELECT c.name, SUM(oi.line_total) AS revenue FROM order_items oi "
    "JOIN products p ON p.id = oi.product_id JOIN categories c ON c.id = p.category_id "
    "GROUP BY c.name ORDER BY revenue DESC LIMIT 5",
    "WITH monthly AS (SELECT date_trunc('month', order_date) AS m, SUM(total_amount) AS t "
    "FROM orders WHERE status <> 'cancelled' GROUP BY 1) SELECT * FROM monthly ORDER BY m",
    "SELECT COUNT(*) FROM commerce.orders WHERE order_date >= CURRENT_DATE - INTERVAL '30 days'",
    "SELECT full_name FROM customers WHERE id IN (SELECT customer_id FROM orders "
    "WHERE total_amount > 1000)",
    "SELECT name, RANK() OVER (ORDER BY price DESC) AS r FROM products",
    "SELECT EXTRACT(YEAR FROM order_date) AS y, COUNT(*) FROM orders GROUP BY y",
    "SELECT name FROM products UNION SELECT name FROM categories",
    "SELECT name FROM products WHERE name = 'DROP TABLE orders'",
]


@pytest.mark.parametrize("sql", VALID)
def test_valid_read_queries_pass(validator: SQLValidator, sql: str) -> None:
    result = validator.validate(sql)
    assert result.sql.upper().startswith(("SELECT", "WITH"))
    assert "LIMIT" in result.sql.upper()


REJECTED = [
    ("DELETE FROM orders", "sql_not_select"),
    ("UPDATE orders SET status = 'x'", "sql_not_select"),
    ("INSERT INTO orders (id) VALUES (1)", "sql_not_select"),
    ("DROP TABLE orders", "sql_not_select"),
    ("TRUNCATE orders", "sql_not_select"),
    ("ALTER TABLE orders ADD COLUMN x int", "sql_not_select"),
    ("CREATE TABLE x (id int)", "sql_not_select"),
    ("GRANT ALL ON orders TO public", "sql_not_select"),
    ("COPY orders TO '/tmp/out.csv'", "sql_not_select"),
    ("SET statement_timeout = 0", "sql_not_select"),
    ("SELECT 1; DROP TABLE orders", "sql_multiple_statements"),
    ("SeLeCt * FrOm orders; DeLeTe FROM orders", "sql_multiple_statements"),
    ("WITH x AS (DELETE FROM orders RETURNING *) SELECT * FROM x", "sql_forbidden_statement"),
    ("SELECT * INTO backup FROM orders", "sql_forbidden_statement"),
    ("SELECT * FROM orders FOR UPDATE", "sql_locking"),
    ("SELECT pg_sleep(10)", "sql_blocked_function"),
    ("SELECT (SELECT pg_read_file('/etc/passwd'))", "sql_blocked_function"),
    ("SELECT current_setting('is_superuser')", "sql_blocked_function"),
    ("SELECT set_config('search_path', 'public', false)", "sql_blocked_function"),
    ("SELECT version()", "sql_blocked_function"),
    ("SELECT * FROM dblink('host=x', 'select 1') AS t(a int)", "sql_table_function"),
    ("SELECT * FROM generate_series(1, 100000000)", "sql_table_function"),
    ("SELECT * FROM pg_catalog.pg_user", "sql_forbidden_table"),
    ("SELECT * FROM pg_shadow", "sql_forbidden_table"),
    ("SELECT * FROM information_schema.tables", "sql_forbidden_table"),
    ("SELECT * FROM public.users", "sql_forbidden_table"),
    ("SELECT id FROM orders UNION SELECT usesysid FROM pg_catalog.pg_user", "sql_forbidden_table"),
    ("SELECT * FROM users", "sql_unknown_table"),
    ("SELECT o.bogus FROM orders o", "sql_unknown_column"),
    ("SELECT nonexistent FROM orders", "sql_unknown_column"),
    ("", "sql_empty"),
    ("SELEC * FROM", "sql_syntax_error"),
]


@pytest.mark.parametrize(("sql", "code"), REJECTED)
def test_unsafe_or_invalid_queries_are_rejected(
    validator: SQLValidator, sql: str, code: str
) -> None:
    with pytest.raises(SQLSafetyError) as error:
        validator.validate(sql)
    assert error.value.code == code


def test_schema_errors_are_correctable_but_attacks_are_not(validator: SQLValidator) -> None:
    with pytest.raises(SQLSafetyError) as unknown:
        validator.validate("SELECT o.bogus FROM orders o")
    assert is_correctable(unknown.value)
    assert "Its columns are" in unknown.value.message
    with pytest.raises(SQLSafetyError) as attack:
        validator.validate("DELETE FROM orders")
    assert not is_correctable(attack.value)


@pytest.mark.parametrize(
    ("sql", "expected_limit"),
    [
        ("SELECT id FROM orders", 200),
        ("SELECT id FROM orders LIMIT 5", 5),
        ("SELECT id FROM orders LIMIT 100000", 200),
    ],
)
def test_row_limit_is_enforced(validator: SQLValidator, sql: str, expected_limit: int) -> None:
    result = validator.validate(sql)
    assert result.limit == expected_limit
    assert result.sql.endswith(f"LIMIT {expected_limit}")


def test_comments_are_stripped_from_executed_sql(validator: SQLValidator) -> None:
    result = validator.validate("SELECT id FROM orders /* hidden */ -- ; DROP TABLE orders")
    assert "--" not in result.sql and "/*" not in result.sql


def test_referenced_tables_are_reported(validator: SQLValidator) -> None:
    result = validator.validate(
        "WITH t AS (SELECT customer_id FROM orders) SELECT c.full_name FROM t "
        "JOIN customers c ON c.id = t.customer_id"
    )
    assert sorted(result.tables) == ["customers", "orders"]  # the CTE name "t" is excluded


def test_join_path_expansion_adds_bridge_tables(snapshot: SchemaSnapshot) -> None:
    tables = expand_join_path(["customers", "products"], snapshot)
    assert {"orders", "order_items", "categories"} <= set(tables)
