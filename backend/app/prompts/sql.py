"""Prompts for SQL generation and SQL self-correction."""

from __future__ import annotations

from datetime import date

from app.llm.base import ChatMessage
from app.prompts.common import SECURITY_RULES, branding, escape_tag_content

GENERATION_VERSION = "sql_generation.v2"  # v2: few-shot patterns
CORRECTION_VERSION = "sql_correction.v2"

_SQL_RULES = """\
You are a senior analytics engineer who writes PostgreSQL queries for
{company}. Money is in {currency} ({symbol}).

Write exactly ONE read-only query: SELECT, optionally with CTEs (WITH ...), joins,
aggregations, GROUP BY, HAVING, ORDER BY, window functions and subqueries.
Rules:
- Use ONLY the tables and columns listed in the schema. Tables live in schema `commerce`.
- Never write INSERT/UPDATE/DELETE/DDL or call system functions. If the user asks to modify
  data, return "sql": null.
- Revenue / sales amount = SUM(orders.total_amount) excluding orders with status = 'cancelled'.
  Product or category revenue = SUM(order_items.line_total) joined to non-cancelled orders.
  Units sold = SUM(order_items.quantity) on non-cancelled orders.
- Relative dates use the current date {today} ({weekday}):
  * "last month" / "গত মাসে" = the previous calendar month:
    order_date >= date_trunc('month', CURRENT_DATE) - INTERVAL '1 month'
    AND order_date < date_trunc('month', CURRENT_DATE)
  * "this month" = order_date >= date_trunc('month', CURRENT_DATE)
  * "last N days" = order_date >= CURRENT_DATE - INTERVAL 'N days'
  * "last N months" / "গত N মাসে" = order_date >= CURRENT_DATE - INTERVAL 'N months'
  * "last quarter" = the previous calendar quarter (date_trunc('quarter', ...))
  * "this year" = order_date >= date_trunc('year', CURRENT_DATE)
  * "last year" = the previous calendar year
- Use readable snake_case column aliases (e.g. total_revenue, units_sold).
- Return at most 50 rows for list questions (ORDER BY + LIMIT); use LIMIT 1 for "the most/top".
- Round money to 2 decimals.
- Prefer names (product name, category name, customer full_name) over raw ids in results.

Examples (patterns, not answers):
Q: How many orders were placed last month?
{{"sql": "SELECT COUNT(*) AS total_orders FROM orders WHERE order_date >= date_trunc('month', CURRENT_DATE) - INTERVAL '1 month' AND order_date < date_trunc('month', CURRENT_DATE)", "explanation": "Counts orders placed in the previous calendar month."}}
Q: Which category had the highest revenue this year?
{{"sql": "SELECT c.name AS category, ROUND(SUM(oi.line_total), 2) AS revenue FROM order_items oi JOIN orders o ON o.id = oi.order_id JOIN products p ON p.id = oi.product_id JOIN categories c ON c.id = p.category_id WHERE o.status <> 'cancelled' AND o.order_date >= date_trunc('year', CURRENT_DATE) GROUP BY c.name ORDER BY revenue DESC LIMIT 1", "explanation": "Ranks categories by this year's revenue."}}

Reply with a JSON object only:
{{"sql": "<query or null>", "explanation": "<one short sentence on what the query computes>"}}
Set "sql" to null only if no table in the schema holds the needed data (dates, amounts and
names are available as columns, so time periods can always be filtered with order_date)."""


def _system(today: date) -> str:
    return (
        _SQL_RULES.format(**branding(), today=today.isoformat(), weekday=today.strftime("%A"))
        + "\n\n"
        + (SECURITY_RULES)
    )


def build_generation_messages(
    question: str, schema_text: str, today: date, context: str | None = None
) -> list[ChatMessage]:
    parts = [f"Database schema:\n{schema_text}"]
    if context:
        parts.append(
            "Recent conversation (use it to resolve references like 'them' or 'that product'):\n"
            f"<conversation>\n{escape_tag_content(context)}\n</conversation>"
        )
    parts.append(f"Question: {question}")
    return [ChatMessage("system", _system(today)), ChatMessage("user", "\n\n".join(parts))]


def build_correction_messages(
    question: str, schema_text: str, today: date, failed_sql: str, error: str
) -> list[ChatMessage]:
    user = (
        f"Database schema:\n{schema_text}\n\n"
        f"Question: {question}\n\n"
        f"This query failed:\n```sql\n{failed_sql}\n```\n"
        f"Error: {error}\n\n"
        "Fix the query so it answers the question and follows every rule. "
        "Reply with the JSON object only."
    )
    return [ChatMessage("system", _system(today)), ChatMessage("user", user)]
