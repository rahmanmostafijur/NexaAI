"""Execution trace: timing of each pipeline stage (no prompts or private reasoning)."""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any


class Trace:
    def __init__(self) -> None:
        self._started = time.perf_counter()
        self.entries: list[dict[str, Any]] = []

    def add(
        self, name: str, duration_ms: int, status: str = "ok", detail: str | None = None
    ) -> None:
        entry: dict[str, Any] = {"name": name, "duration_ms": duration_ms, "status": status}
        if detail:
            entry["detail"] = detail[:300]
        self.entries.append(entry)

    @contextmanager
    def span(self, name: str, detail: str | None = None) -> Iterator[dict[str, Any]]:
        started = time.perf_counter()
        info: dict[str, Any] = {"detail": detail}
        try:
            yield info
        except BaseException:
            self.add(name, _ms(started), "error", info.get("detail"))
            raise
        self.add(name, _ms(started), "ok", info.get("detail"))

    @property
    def total_ms(self) -> int:
        return _ms(self._started)

    def stages(self) -> list[dict[str, Any]]:
        return [{"name": e["name"], "duration_ms": e["duration_ms"]} for e in self.entries]


def _ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
