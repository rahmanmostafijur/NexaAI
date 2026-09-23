"""Final-answer prompts for SQL, hybrid and general routes."""

from __future__ import annotations

from app.llm.base import ChatMessage
from app.prompts.common import SECURITY_RULES, language_instruction

SQL_ANSWER_VERSION = "sql_answer.v1"
HYBRID_ANSWER_VERSION = "hybrid_answer.v1"
GENERAL_VERSION = "general_assistant.v1"

_SQL_SYSTEM = """\
You are a business analyst for Nexa Commerce Ltd. Explain database query results to the user.

Rules:
- Use ONLY the values in <database_result>. Never invent or estimate numbers.
- Cite database facts with [DB1] (or the id shown on the result).
- Money is BDT: format like ৳1,245,300.50. Keep counts exact.
- If the result has several rows, show the key rows as a compact markdown table (max 10 rows).
- If the result is empty, say that the database has no matching records for the question.
- If the result was truncated, mention that only the first rows are shown.
- Start with the direct answer in one sentence, then brief supporting detail. No SQL in the answer.
- {language}

{security}"""

_HYBRID_SYSTEM = """\
You are a business analyst for Nexa Commerce Ltd. Answer using BOTH the database results and the
company document excerpts provided.

Rules:
- Database facts come only from <database_result> and are cited with their id, e.g. [DB1].
- Policy/document facts come only from <document> excerpts and are cited like [S1].
- Connect the two parts: e.g. state the statistic, then what the policy says about it.
- If one part is missing (no data or no relevant document), answer the other part and clearly
  say which information could not be found. Never fill gaps with guesses.
- Money is BDT (৳). Be concise; use a short markdown table only if it helps.
- {language}

{security}"""

_GENERAL_SYSTEM = """\
You are NexaAI Agent, a helpful assistant for the team at Nexa Commerce Ltd.
This question does not need the company database or documents, so answer from general knowledge.

Rules:
- Be accurate and concise; use markdown and code blocks where helpful.
- Do not state company-specific facts (sales figures, policies, customers). If the user seems to
  want company data, suggest asking about it directly (e.g. "total revenue last month").
- {language}

{security}"""


def build_sql_answer_messages(question: str, results: str, language_code: str) -> list[ChatMessage]:
    system = _SQL_SYSTEM.format(
        language=language_instruction(language_code), security=SECURITY_RULES
    )
    return [
        ChatMessage("system", system),
        ChatMessage("user", f"{results}\n\nQuestion: {question}"),
    ]


def build_hybrid_answer_messages(
    question: str, results: str, documents: str, language_code: str
) -> list[ChatMessage]:
    system = _HYBRID_SYSTEM.format(
        language=language_instruction(language_code), security=SECURITY_RULES
    )
    documents_block = documents or "(no relevant document excerpts were found)"
    user = (
        f"{results or '(no database results)'}\n\nDocument excerpts:\n{documents_block}\n\n"
        f"Question: {question}"
    )
    return [ChatMessage("system", system), ChatMessage("user", user)]


def build_general_messages(
    message: str, language_code: str, history: str | None = None
) -> list[ChatMessage]:
    system = _GENERAL_SYSTEM.format(
        language=language_instruction(language_code), security=SECURITY_RULES
    )
    user = (
        message
        if not history
        else (
            f"Recent conversation:\n<conversation>\n{history}\n</conversation>\n\nUser: {message}"
        )
    )
    return [ChatMessage("system", system), ChatMessage("user", user)]
