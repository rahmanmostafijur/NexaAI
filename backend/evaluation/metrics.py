"""Scoring functions. Every metric is computed from the dataset; nothing is estimated."""

from __future__ import annotations

import math
import statistics
from collections.abc import Iterable, Sequence
from decimal import Decimal

_BENGALI_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")


def normalise_text(text: str) -> str:
    return " ".join(text.translate(_BENGALI_DIGITS).lower().split())


def contains_all_groups(answer: str, groups: Sequence[Sequence[str]]) -> bool:
    """Each group is a list of acceptable alternatives; every group must match."""
    text = normalise_text(answer)
    return all(any(normalise_text(option) in text for option in group) for group in groups)


def _cell(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, int | float | Decimal):
        number = float(value)
        if math.isfinite(number):
            return f"{round(number, 2):.2f}"
    return str(value).strip().lower()


def result_matches(gold_rows: list[list[object]], agent_rows: list[list[object]]) -> bool:
    """Execution accuracy: the agent's result must contain the gold result.

    Column order, aliases and extra columns are ignored (the agent may add a
    helpful count column). Every gold row must match a distinct agent row whose
    values include all of the gold row's values, and multi-row answers must
    have the same number of rows.
    """
    if not gold_rows:
        return not agent_rows
    if len(gold_rows) > 1 and len(agent_rows) != len(gold_rows):
        return False
    remaining = [{_cell(v) for v in row} for row in agent_rows]
    for gold in gold_rows:
        wanted = {_cell(v) for v in gold}
        match = next((i for i, cells in enumerate(remaining) if wanted <= cells), None)
        if match is None:
            return False
        remaining.pop(match)
    return True


def rate(values: Iterable[bool]) -> tuple[float | None, int]:
    items = list(values)
    return (sum(items) / len(items) if items else None), len(items)


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(pct / 100 * len(ordered)) - 1))
    return ordered[index]


def median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None
