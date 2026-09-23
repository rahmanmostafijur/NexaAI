"""Evaluation runner.

    python evaluate_agent.py --mode offline   # no LLM: heuristic routing, retrieval, gold SQL
    python evaluate_agent.py --mode full      # full agent with the configured LLM

Results are printed as a table and written to evaluation/results/*.json.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.agent import heuristics
from app.agent.orchestrator import AgentOrchestrator
from app.agent.services import AgentServices
from app.core.config import BACKEND_DIR, get_settings
from app.core.errors import AppError
from app.core.logging import configure_logging
from app.core.security import hash_password
from app.db.session import dispose_engines, get_readonly_pool, session_scope
from app.embeddings.factory import get_embedding_provider
from app.llm.factory import get_llm_provider
from app.models import User
from app.sql.executor import SQLExecutor
from app.sql.validator import SQLValidator
from evaluation.metrics import contains_all_groups, median, percentile, rate, result_matches

DATASETS = {
    "main": BACKEND_DIR / "evaluation" / "dataset.jsonl",
    # Written after the heuristic vocabulary was tuned; never used for tuning.
    "holdout": BACKEND_DIR / "evaluation" / "holdout.jsonl",
}
RESULTS_DIR = BACKEND_DIR / "evaluation" / "results"
TOP_K = 5
EVAL_USER = "evaluation@nexa.local"

logger = logging.getLogger("evaluation")


@dataclass
class ItemResult:
    id: str
    category: str
    expected_route: str
    predicted_route: str | None = None
    route_correct: bool | None = None
    sql_correct: bool | None = None
    retrieval_hit: bool | None = None
    retrieval_precision: float | None = None
    citation_correct: bool | None = None
    answer_correct: bool | None = None
    hybrid_success: bool | None = None
    latency_ms: float | None = None
    error: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


def load_dataset(path: Path = DATASETS["main"]) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


async def _gold_rows(executor: SQLExecutor, sql: str) -> list[list[object]]:
    return (await executor.execute(sql)).rows


def _retrieval_scores(titles: list[str], expected: list[str]) -> tuple[bool, float]:
    relevant = [t for t in titles if t in expected]
    return bool(relevant), (len(relevant) / len(titles) if titles else 0.0)


# --- offline mode -------------------------------------------------------------


async def evaluate_offline(
    items: list[dict[str, Any]], services: AgentServices
) -> list[ItemResult]:
    """Everything that can be measured without a language model."""
    settings = get_settings()
    executor = SQLExecutor(
        get_readonly_pool,
        timeout_ms=settings.sql_statement_timeout_ms,
        max_rows=settings.sql_max_rows,
    )
    snapshot = await services.catalog.snapshot()
    validator = SQLValidator(snapshot, settings.sql_max_rows)
    results = []
    for item in items:
        result = ItemResult(item["id"], item["category"], item["expected_route"])
        started = time.perf_counter()
        decision = heuristics.classify(item["question"])
        result.predicted_route = decision.route.value
        result.route_correct = decision.route.value == item["expected_route"]
        if item.get("gold_sql"):
            try:
                rows = await _gold_rows(executor, validator.validate(item["gold_sql"]).sql)
                result.sql_correct = bool(rows)  # gold query is valid, safe and returns data
                result.details["gold_rows"] = rows[:3]
            except AppError as exc:
                result.sql_correct = False
                result.error = f"gold SQL failed: {exc.message}"
        if item.get("expected_sources"):
            chunks = await services.retriever.search(item["question"], top_k=TOP_K)
            filenames = [c.filename for c in chunks]
            result.retrieval_hit, result.retrieval_precision = _retrieval_scores(
                filenames, item["expected_sources"]
            )
            result.details["retrieved"] = filenames
        result.latency_ms = (time.perf_counter() - started) * 1000
        results.append(result)
    return results


# --- full mode -------------------------------------------------------------------


async def _evaluation_user() -> uuid.UUID:
    async with session_scope() as session:
        user = await session.scalar(select(User).where(User.email == EVAL_USER))
        if user is None:
            user = User(
                email=EVAL_USER,
                full_name="Evaluation Runner",
                password_hash=hash_password(uuid.uuid4().hex),
                role="user",
            )
            session.add(user)
            await session.flush()
        return user.id


async def evaluate_full(
    items: list[dict[str, Any]], services: AgentServices, pause: float = 0.0
) -> list[ItemResult]:
    settings = get_settings()
    executor = SQLExecutor(
        get_readonly_pool,
        timeout_ms=settings.sql_statement_timeout_ms,
        max_rows=settings.sql_max_rows,
    )
    orchestrator = AgentOrchestrator(services)
    user_id = await _evaluation_user()
    results = []
    for number, item in enumerate(items, start=1):
        if pause and number > 1:
            await asyncio.sleep(pause)  # stay under provider rate limits (free tiers)
        result = ItemResult(item["id"], item["category"], item["expected_route"])
        started = time.perf_counter()
        try:
            _, message = await orchestrator.answer(
                user_id=user_id, message=item["question"], conversation_id=None, request_id=None
            )
        except AppError as exc:
            result.error = f"{exc.code}: {exc.message}"
            result.route_correct = False
            results.append(result)
            logger.warning("[%d/%d] %s failed: %s", number, len(items), item["id"], result.error)
            continue
        result.latency_ms = (time.perf_counter() - started) * 1000
        details = message["details"]
        result.predicted_route = details["route"]
        result.route_correct = details["route"] == item["expected_route"]
        answer = message["content"]

        if item.get("gold_sql"):
            gold = await _gold_rows(executor, item["gold_sql"])
            agent_rows = details["sql"][0]["rows"] if details["sql"] else []
            result.sql_correct = bool(details["sql"]) and result_matches(gold, agent_rows)
            result.details["agent_sql"] = details["sql"][0]["sql"] if details["sql"] else None
        documents = [s for s in details["sources"] if s["type"] == "document"]
        if item.get("expected_sources"):
            filenames = [s["filename"] for s in documents]
            result.retrieval_hit, result.retrieval_precision = _retrieval_scores(
                filenames, item["expected_sources"]
            )
            cited = {s["id"] for s in documents}
            result.citation_correct = (
                bool(cited)
                and any(s["filename"] in item["expected_sources"] for s in documents)
                and all(f"[{sid}]" in answer for sid in cited)
            )
        if item.get("must_include"):
            result.answer_correct = contains_all_groups(answer, item["must_include"])
        if item["expected_route"] == "HYBRID":
            result.hybrid_success = bool(
                result.route_correct and result.sql_correct and result.retrieval_hit
            )
        result.details["answer"] = answer[:500]
        results.append(result)
        logger.info("[%d/%d] %s route=%s", number, len(items), item["id"], result.predicted_route)
    return results


# --- reporting ---------------------------------------------------------------------


def summarise(results: list[ItemResult], mode: str) -> dict[str, Any]:
    def metric(values) -> dict[str, Any]:
        value, n = rate(values)
        return {"value": value, "n": n}

    latencies = [r.latency_ms for r in results if r.latency_ms is not None]
    precisions = [r.retrieval_precision for r in results if r.retrieval_precision is not None]
    by_category: dict[str, dict[str, Any]] = {}
    for category in sorted({r.category for r in results}):
        subset = [r for r in results if r.category == category]
        by_category[category] = {
            "routing_accuracy": metric(
                r.route_correct for r in subset if r.route_correct is not None
            )
        }
    summary = {
        "mode": mode,
        "items": len(results),
        "routing_accuracy": metric(r.route_correct for r in results if r.route_correct is not None),
        "sql_accuracy": metric(r.sql_correct for r in results if r.sql_correct is not None),
        "retrieval_hit_rate": metric(
            r.retrieval_hit for r in results if r.retrieval_hit is not None
        ),
        "retrieval_precision": {
            "value": sum(precisions) / len(precisions) if precisions else None,
            "n": len(precisions),
        },
        "citation_correctness": metric(
            r.citation_correct for r in results if r.citation_correct is not None
        ),
        "answer_correctness": metric(
            r.answer_correct for r in results if r.answer_correct is not None
        ),
        "hybrid_success_rate": metric(
            r.hybrid_success for r in results if r.hybrid_success is not None
        ),
        "latency_ms": {"p50": median(latencies), "p95": percentile(latencies, 95)},
        "errors": sum(1 for r in results if r.error),
        "by_category": by_category,
    }
    return summary


def _format(metric: dict[str, Any]) -> str:
    if metric["value"] is None:
        return "n/a"
    return f"{metric['value'] * 100:.1f}%  (n={metric['n']})"


def print_report(summary: dict[str, Any]) -> None:
    labels = {
        "offline": {
            "routing_accuracy": "Routing Accuracy (heuristic router, no LLM)",
            "sql_accuracy": "Gold SQL valid & executable",
            "retrieval_hit_rate": f"Retrieval Hit Rate @{TOP_K}",
            "retrieval_precision": f"Retrieval Precision @{TOP_K}",
        },
        "full": {
            "routing_accuracy": "Routing Accuracy",
            "sql_accuracy": "SQL Execution Accuracy",
            "retrieval_hit_rate": "Retrieval Hit Rate (cited sources)",
            "retrieval_precision": "Retrieval Precision (cited sources)",
            "citation_correctness": "Citation Correctness",
            "answer_correctness": "Answer Correctness (required facts)",
            "hybrid_success_rate": "Hybrid Success Rate",
        },
    }[summary["mode"]]
    print(f"\nNexaAI Agent evaluation — mode: {summary['mode']}, items: {summary['items']}")
    print("-" * 72)
    for key, label in labels.items():
        print(f"{label:<44} {_format(summary[key])}")
    latency = summary["latency_ms"]
    if latency["p50"] is not None:
        print(f"{'Latency p50 / p95':<44} {latency['p50']:.0f} ms / {latency['p95']:.0f} ms")
    print(f"{'Errors':<44} {summary['errors']}")
    print("\nRouting accuracy by category:")
    for category, values in summary["by_category"].items():
        print(f"  {category:<12} {_format(values['routing_accuracy'])}")


async def main(
    mode: str,
    limit: int | None,
    dataset: str = "main",
    category: str | None = None,
    pause: float = 0.0,
) -> None:
    configure_logging("WARNING")
    logging.getLogger("evaluation").setLevel(logging.INFO)
    settings = get_settings()
    llm = get_llm_provider()
    if mode == "full" and not llm.configured:
        raise SystemExit(
            "Full evaluation needs a configured LLM (LLM_BASE_URL / LLM_MODEL / LLM_API_KEY)."
        )
    services = AgentServices.build(settings, llm, get_embedding_provider())
    items = load_dataset(DATASETS[dataset])
    if category:
        items = [item for item in items if item["category"] == category]
    items = items[:limit] if limit else items
    try:
        if mode == "full":
            results = await evaluate_full(items, services, pause)
        else:
            results = await evaluate_offline(items, services)
    finally:
        await llm.aclose()
        await dispose_engines()
    summary = summarise(results, mode)
    summary["dataset"] = dataset + (f" ({category})" if category else "")
    print_report(summary)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    suffix = f"-{category}" if category else ""
    output = RESULTS_DIR / f"{stamp}-{dataset}{suffix}-{mode}.json"
    payload = {
        "summary": summary,
        "model": {"llm": llm.model, "embedding": services.embeddings.model},
        "items": [asdict(r) for r in results],
    }
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    print(f"\nDetailed results: {output}")


def cli() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the NexaAI agent.")
    parser.add_argument("--mode", choices=["offline", "full"], default="offline")
    parser.add_argument("--dataset", choices=sorted(DATASETS), default="main")
    parser.add_argument(
        "--pause", type=float, default=0.0, help="seconds between items (rate limits)"
    )
    parser.add_argument("--category", default=None, help="only items of this category")
    parser.add_argument("--limit", type=int, default=None, help="evaluate only the first N items")
    args = parser.parse_args()
    asyncio.run(main(args.mode, args.limit, args.dataset, args.category, args.pause))
