"""Conversation memory: a bounded, compact view of recent turns.

Only the last N messages are considered, each is truncated, and the total is
capped by characters. Assistant turns carry their route and the SQL they ran,
which is what makes follow-ups such as "How many of them were returned?"
resolvable ("them" = the previous query's filter).
"""

from __future__ import annotations

from app.models import Message

_MAX_MESSAGE_CHARS = 500
_MAX_SQL_CHARS = 400


def format_history(messages: list[Message], max_chars: int) -> str | None:
    lines: list[str] = []
    used = 0
    for message in reversed(messages):
        line = _format(message)
        if used + len(line) > max_chars:
            break
        lines.append(line)
        used += len(line)
    return "\n".join(reversed(lines)) or None


def _format(message: Message) -> str:
    content = " ".join(message.content.split())
    if len(content) > _MAX_MESSAGE_CHARS:
        content = content[: _MAX_MESSAGE_CHARS - 1] + "…"
    if message.role == "user":
        return f"User: {content}"
    details = message.details or {}
    extras = []
    if details.get("route"):
        extras.append(f"route={details['route']}")
    for sql in details.get("sql") or []:
        text = " ".join(str(sql.get("sql", "")).split())[:_MAX_SQL_CHARS]
        if text:
            extras.append(f"SQL: {text}")
    suffix = f" [{'; '.join(extras)}]" if extras else ""
    return f"Assistant: {content}{suffix}"
