"""Agent orchestrator: the request lifecycle, emitted as a stream of events.

    persist user message -> detect language -> route -> plan -> execute tools
    -> prepare answer -> stream tokens -> validate citations -> persist answer + run

Each phase is a separate component (router, planner, executor, responder), so
this class only sequences them, handles failures and records observability.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from app.agent.citations import validate_citations
from app.agent.executor import sql_event
from app.agent.language import detect_language
from app.agent.memory import format_history
from app.agent.services import AgentServices
from app.agent.tools.base import ToolContext, ToolResult
from app.agent.trace import Trace
from app.agent.types import AgentEvent, LanguageInfo, Plan, Route, RouteDecision
from app.core.errors import AppError
from app.core.logging import log_extra
from app.db.session import session_scope
from app.llm.usage import track_usage
from app.repositories.agent_runs import AgentRunRepository
from app.repositories.conversations import ConversationRepository, MessageRepository
from app.repositories.documents import DocumentRepository

logger = logging.getLogger(__name__)

STAGE_LABELS = {
    "analyzing": "Analyzing request...",
    "routing": "Selecting data source...",
    "planning": "Planning steps...",
    "generating": "Generating answer...",
    "validating": "Checking sources...",
}


def _status(stage: str) -> AgentEvent:
    return AgentEvent("status", {"stage": stage, "label": STAGE_LABELS[stage]})


def _title_from(message: str) -> str:
    words = " ".join(message.split())
    return words if len(words) <= 60 else words[:57].rstrip() + "..."


class AgentOrchestrator:
    def __init__(self, services: AgentServices) -> None:
        self._services = services
        self._settings = services.settings

    async def run(
        self,
        *,
        user_id: uuid.UUID,
        message: str,
        conversation_id: uuid.UUID | None,
        request_id: str | None,
    ) -> AsyncIterator[AgentEvent]:
        trace = Trace()
        with track_usage() as usage:
            conversation_id, user_message_id, run_id, history, documents = await self._start(
                user_id, message, conversation_id, request_id
            )
            yield AgentEvent(
                "meta",
                {
                    "conversation_id": str(conversation_id),
                    "run_id": str(run_id),
                    "user_message_id": str(user_message_id),
                },
            )
            state: dict[str, Any] = {"decision": None, "language": None, "tools": []}
            try:
                async for event in self._pipeline(message, history, documents, trace, state):
                    if event.type == "done":
                        final = await self._finish(
                            conversation_id, run_id, event.data, trace, usage.as_dict(), state
                        )
                        state["finished"] = True
                        yield AgentEvent("done", {"message": final})
                    else:
                        yield event
            except AppError as exc:
                await self._fail(user_message_id, run_id, trace, usage.as_dict(), state, exc)
                yield AgentEvent(
                    "error", {"code": exc.code, "message": exc.message, "retryable": exc.retryable}
                )
            except (asyncio.CancelledError, GeneratorExit):
                if state.get("finished"):
                    raise  # the answer was already saved; nothing to clean up
                error = AppError("The client disconnected before the answer finished.")
                error.code = "client_disconnected"
                await asyncio.shield(
                    self._fail(user_message_id, run_id, trace, usage.as_dict(), state, error)
                )
                raise
            except Exception:
                logger.exception("Agent run %s failed", run_id)
                error = AppError("Something went wrong while answering. Please try again.")
                error.code, error.retryable = "internal_error", True
                await self._fail(user_message_id, run_id, trace, usage.as_dict(), state, error)
                yield AgentEvent(
                    "error", {"code": error.code, "message": error.message, "retryable": True}
                )

    async def answer(self, **kwargs: Any) -> tuple[str, dict[str, Any]]:
        """Non-streaming variant: returns (conversation_id, final message)."""
        conversation_id = ""
        final: dict[str, Any] | None = None
        failure: dict[str, Any] | None = None
        # Drain the generator completely so its cleanup runs in this context.
        async for event in self.run(**kwargs):
            if event.type == "meta":
                conversation_id = event.data["conversation_id"]
            elif event.type == "done":
                final = event.data["message"]
            elif event.type == "error":
                failure = event.data
        if failure is not None:
            error = AppError(failure["message"])
            error.code = failure["code"]
            error.status_code = 503 if failure.get("retryable") else 422
            raise error
        if final is None:
            raise AppError("The agent did not produce an answer.")
        return conversation_id, final

    # --- pipeline ------------------------------------------------------------

    async def _pipeline(
        self,
        message: str,
        history: str | None,
        documents: list[str],
        trace: Trace,
        state: dict[str, Any],
    ) -> AsyncIterator[AgentEvent]:
        services = self._services
        yield _status("analyzing")
        with trace.span("language_detection") as span:
            language = detect_language(message)
            span["detail"] = language.code
        state["language"] = language

        yield _status("routing")
        snapshot = await services.catalog.snapshot()
        with trace.span("routing") as span:
            decision = await services.router.route(
                message,
                language=language,
                history=history,
                tables=sorted(snapshot.tables),
                documents=documents,
            )
            span["detail"] = (
                f"{decision.route.value} ({decision.confidence:.2f}, {decision.source})"
            )
        state["decision"] = decision
        yield AgentEvent("analysis", decision.as_event(language))

        if decision.needs_clarification and decision.clarification_question:
            yield AgentEvent("token", {"delta": decision.clarification_question})
            yield AgentEvent(
                "done",
                self._draft(decision, language, Plan([]), decision.clarification_question, [], []),
            )
            return

        yield _status("planning")
        with trace.span("planning") as span:
            plan = await services.planner.plan(decision)
            span["detail"] = f"{len(plan.steps)} step(s), {plan.source}"
        yield AgentEvent("plan", plan.as_event())
        state["tools"] = list(dict.fromkeys(s.tool for s in plan.steps if s.tool != "general"))

        context = ToolContext(language=language, original_message=message, history=history)
        results: dict[str, ToolResult] = {}
        async for event in self._execute(plan, context, trace, results):
            yield event

        prepared = services.responder.prepare(
            decision=decision,
            language=language,
            message=message,
            plan=plan,
            results=results,
            history=history,
        )
        if prepared.sources:
            yield AgentEvent("sources", {"sources": prepared.sources})

        yield _status("generating")
        parts: list[str] = []
        with trace.span("answer_generation") as span:
            async for delta in services.responder.stream(prepared):
                parts.append(delta)
                yield AgentEvent("token", {"delta": delta})
            span["detail"] = prepared.prompt_version or "fixed response"

        yield _status("validating")
        check = validate_citations("".join(parts), prepared.valid_ids)
        warnings = list(prepared.warnings)
        if check.removed:
            warnings.append(f"Removed citations to unknown sources: {', '.join(check.removed)}")
        sources = prepared.sources
        doc_sources = [s for s in sources if s["type"] == "document"]
        if doc_sources and check.used:
            sources = [s for s in sources if s["type"] == "database" or s["id"] in check.used]
        elif doc_sources and prepared.canned is None:
            warnings.append(
                "The answer did not cite specific passages; all retrieved sources are listed."
            )
        # Grounded = the answer is backed by evidence the user can inspect.
        if prepared.canned is not None or decision.route == Route.GENERAL:
            grounded = False
        elif decision.route == Route.SQL:
            grounded = any(s["type"] == "database" for s in sources)
        else:
            grounded = bool(check.used)
        sql_details = [sql_event(step_id, r) for step_id, r in results.items() if r.sql]
        yield AgentEvent(
            "done",
            self._draft(
                decision,
                language,
                plan,
                check.text,
                sources,
                warnings,
                grounded=grounded,
                sql=sql_details,
            ),
        )

    async def _execute(
        self, plan: Plan, context: ToolContext, trace: Trace, results: dict[str, ToolResult]
    ) -> AsyncIterator[AgentEvent]:
        """Run the executor in a task and relay its events as they happen."""
        queue: asyncio.Queue[AgentEvent] = asyncio.Queue()

        async def emit(event: AgentEvent) -> None:
            await queue.put(event)

        task = asyncio.create_task(self._services.executor.execute(plan, context, emit, trace))
        getter: asyncio.Task[AgentEvent] | None = None
        try:
            while True:
                getter = asyncio.create_task(queue.get())
                done, _ = await asyncio.wait({task, getter}, return_when=asyncio.FIRST_COMPLETED)
                if getter in done:
                    yield getter.result()
                    continue
                getter.cancel()
                break
            while not queue.empty():
                yield queue.get_nowait()
            results.update(task.result())
        finally:
            if getter is not None and not getter.done():
                getter.cancel()  # a stream closed mid-step must not leak a pending get()
            if not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task

    def _draft(
        self,
        decision: RouteDecision,
        language: LanguageInfo,
        plan: Plan,
        content: str,
        sources: list[dict[str, Any]],
        warnings: list[str],
        *,
        grounded: bool = False,
        sql: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return {
            "content": content,
            "details": {
                "route": decision.route.value,
                "confidence": round(decision.confidence, 3),
                "reason": decision.reason,
                "language": language.code,
                "plan": [step.as_dict() for step in plan.steps],
                "sql": sql or [],
                "sources": sources,
                "grounded": grounded,
                "warnings": warnings,
            },
        }

    # --- persistence -----------------------------------------------------------

    async def _start(
        self,
        user_id: uuid.UUID,
        message: str,
        conversation_id: uuid.UUID | None,
        request_id: str | None,
    ) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, str | None, list[str]]:
        async with session_scope() as session:
            conversations = ConversationRepository(session)
            messages = MessageRepository(session)
            if conversation_id is not None:
                conversation = await conversations.get_for_user(conversation_id, user_id)
                recent = await messages.recent(conversation.id, self._settings.context_max_messages)
            else:
                conversation = await conversations.create(user_id, _title_from(message))
                recent = []
            history = format_history(recent, self._settings.context_max_chars)
            user_message = await messages.add(conversation.id, "user", message)
            await conversations.touch(conversation.id)
            run = await AgentRunRepository(session).create(
                request_id=request_id,
                conversation_id=conversation.id,
                user_id=user_id,
                status="running",
            )
            documents = await DocumentRepository(session).indexed_titles()
            return conversation.id, user_message.id, run.id, history, documents

    async def _finish(
        self,
        conversation_id: uuid.UUID,
        run_id: uuid.UUID,
        draft: dict[str, Any],
        trace: Trace,
        token_usage: dict[str, int],
        state: dict[str, Any],
    ) -> dict[str, Any]:
        details = {
            **draft["details"],
            "run_id": str(run_id),
            "timings": {"total_ms": trace.total_ms, "stages": trace.stages()},
        }
        decision: RouteDecision = state["decision"]
        language: LanguageInfo = state["language"]
        async with session_scope() as session:
            message = await MessageRepository(session).add(
                conversation_id, "assistant", draft["content"], details
            )
            await ConversationRepository(session).touch(conversation_id)
            await AgentRunRepository(session).update(
                run_id,
                status="success",
                language=language.code,
                route=decision.route.value,
                confidence=decision.confidence,
                tools_used=state["tools"],
                total_ms=trace.total_ms,
                trace=trace.entries,
                token_usage=token_usage if token_usage["total_tokens"] else None,
                completed_at=datetime.now(UTC),
            )
        logger.info(
            "Agent run completed",
            extra=log_extra(
                run_id=run_id,
                route=decision.route.value,
                total_ms=trace.total_ms,
                tokens=token_usage["total_tokens"],
            ),
        )
        return {
            "id": str(message.id),
            "conversation_id": str(conversation_id),
            "role": "assistant",
            "content": message.content,
            "created_at": message.created_at.isoformat(),
            "details": details,
        }

    async def _fail(
        self,
        user_message_id: uuid.UUID,
        run_id: uuid.UUID,
        trace: Trace,
        token_usage: dict[str, int],
        state: dict[str, Any],
        error: AppError,
    ) -> None:
        """Record the failure; remove the unanswered user message so a retry is clean."""
        decision: RouteDecision | None = state.get("decision")
        language: LanguageInfo | None = state.get("language")
        try:
            async with session_scope() as session:
                await MessageRepository(session).delete(user_message_id)
                await AgentRunRepository(session).update(
                    run_id,
                    status="failed",
                    language=language.code if language else None,
                    route=decision.route.value if decision else None,
                    confidence=decision.confidence if decision else None,
                    tools_used=state.get("tools", []),
                    total_ms=trace.total_ms,
                    trace=trace.entries,
                    token_usage=token_usage if token_usage["total_tokens"] else None,
                    error_code=error.code,
                    error_message=error.message[:500],
                    completed_at=datetime.now(UTC),
                )
        except Exception:
            logger.exception("Could not record failure for run %s", run_id)
        logger.warning("Agent run failed", extra=log_extra(run_id=run_id, error_code=error.code))
