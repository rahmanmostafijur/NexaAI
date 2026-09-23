"""Per-run token accounting via a context variable.

The orchestrator opens a tracker for each agent run; every provider call made
inside that run (router, SQL generation, answer...) adds its usage to it,
without having to thread a counter through every function signature.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from app.llm.base import TokenUsage

_current_usage: ContextVar[TokenUsage | None] = ContextVar("current_usage", default=None)


@contextmanager
def track_usage() -> Iterator[TokenUsage]:
    usage = TokenUsage()
    token = _current_usage.set(usage)
    try:
        yield usage
    finally:
        try:
            _current_usage.reset(token)
        except ValueError:
            # A generator finalised from another task's context: nothing to restore.
            _current_usage.set(None)


def record_usage(prompt_tokens: int, completion_tokens: int) -> None:
    usage = _current_usage.get()
    if usage is not None:
        usage.prompt_tokens += prompt_tokens
        usage.completion_tokens += completion_tokens
