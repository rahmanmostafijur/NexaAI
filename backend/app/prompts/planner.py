"""Hybrid planner prompt: decompose a question into ordered tool steps."""

from __future__ import annotations

from app.llm.base import ChatMessage
from app.prompts.common import SECURITY_RULES

VERSION = "hybrid_planner.v1"

_SYSTEM = """\
You plan how to answer a business question that needs both the database and company documents.

Tools:
- "sql": answers a data question from the business database (sales, products, customers,
  returns, stock...). Its input is an English data question, not SQL.
- "rag": searches company documents (policies, handbook, FAQ). Its input is a search question.

Rules:
- Use 2 to 4 steps with ids "s1", "s2", ...
- Put data steps first. If a document search depends on a data result (e.g. the policy for
  "the top category"), list the data step in `depends_on` and write the placeholder {{s1}}
  where the data result should be inserted, e.g. "warranty policy for {{s1}} products".
- Each step has a short `purpose` (max 12 words) that can be shown to the user.

Reply with JSON only:
{{"steps": [{{"id": "s1", "tool": "sql", "query": "...", "depends_on": [], "purpose": "..."}}]}}

{security}"""


def build_messages(question: str) -> list[ChatMessage]:
    return [
        ChatMessage("system", _SYSTEM.format(security=SECURITY_RULES)),
        ChatMessage("user", f"Question: {question}"),
    ]
