"""Prometheus metrics: request latency, agent runs, tool timings, token usage, indexing jobs.

Metric names are fixed and low-cardinality: HTTP routes use the route *template*
(`/api/documents/{document_id}`), never the raw path, and nothing user-supplied becomes a label.
"""

from __future__ import annotations

import time

from prometheus_client import Counter, Histogram
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_LATENCY_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0)

HTTP_DURATION = Histogram(
    "nexa_http_request_duration_seconds",
    "HTTP request latency until the response starts (streams keep running afterwards).",
    ["method", "route", "status"],
    buckets=_LATENCY_BUCKETS,
)
AGENT_RUNS = Counter(
    "nexa_agent_runs",
    "Agent runs by chosen route and outcome.",
    ["route", "status"],
)
AGENT_RUN_DURATION = Histogram(
    "nexa_agent_run_duration_seconds",
    "End-to-end agent run time by route.",
    ["route"],
    buckets=_LATENCY_BUCKETS,
)
TOOL_DURATION = Histogram(
    "nexa_tool_duration_seconds",
    "Time spent in each agent tool (sql = Text-to-SQL, rag = retrieval, general).",
    ["tool", "status"],
    buckets=_LATENCY_BUCKETS,
)
LLM_TOKENS = Counter(
    "nexa_llm_tokens",
    "Language-model tokens consumed.",
    ["type"],
)
INGESTION_JOBS = Counter(
    "nexa_ingestion_jobs",
    "Document indexing attempts by outcome.",
    ["outcome"],
)


class MetricsMiddleware:
    """Times every HTTP request, labelled by method, route template and status code."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = time.perf_counter()
        observed = False

        async def send_and_observe(message: Message) -> None:
            nonlocal observed
            if message["type"] == "http.response.start" and not observed:
                observed = True
                HTTP_DURATION.labels(
                    method=scope["method"],
                    route=route_template(scope),
                    status=str(message["status"]),
                ).observe(time.perf_counter() - started)
            await send(message)

        await self.app(scope, receive, send_and_observe)


def route_template(scope: Scope) -> str:
    """The full path template (`/api/documents/{document_id}`) of the route that served `scope`.

    `scope["route"]` holds the template relative to the included router (`/documents/{id}`),
    which drops the `/api` prefix. The full template is rebuilt from the real path by swapping
    each path-parameter value back to its `{name}`. If that does not line up with the matched
    route, the relative template is used, so a label can never contain user-supplied values.
    Requests that matched no route share the single label `unmatched`.
    """
    route = scope.get("route")
    relative = getattr(route, "path", None)
    if not relative:
        return "unmatched"
    path = str(scope.get("path", ""))
    for name, value in (scope.get("path_params") or {}).items():
        text = str(value)
        index = path.rfind(text)
        if text and index != -1:
            path = f"{path[:index]}{{{name}}}{path[index + len(text) :]}"
    return path if path.endswith(relative) else str(relative)
