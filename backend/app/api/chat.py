"""Chat endpoints: SSE streaming and a non-streaming variant."""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.agent.orchestrator import AgentOrchestrator
from app.agent.types import AgentEvent
from app.api.deps import CurrentUser, DbDep, ServicesDep, SettingsDep
from app.core.logging import request_id_var
from app.core.rate_limit import rate_limiter
from app.repositories.conversations import ConversationRepository
from app.schemas.chat import ChatRequest, ChatResponse, MessageOut

router = APIRouter(prefix="/chat", tags=["chat"])

HEARTBEAT_SECONDS = 15.0


def format_sse(event: AgentEvent) -> str:
    return f"event: {event.type}\ndata: {json.dumps(event.data, ensure_ascii=False)}\n\n"


async def with_heartbeat(
    events: AsyncIterator[AgentEvent], interval: float = HEARTBEAT_SECONDS
) -> AsyncIterator[str]:
    """Relay events; send an SSE comment while idle so proxies keep the stream open.

    The agent generator is consumed by ONE pump task (so its context variables,
    e.g. token accounting, stay in a single context) and frames are relayed
    through a queue. If the client disconnects, the pump is cancelled, which
    lets the orchestrator record the run as interrupted.
    """
    queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=256)

    async def pump() -> None:
        try:
            async for event in events:
                await queue.put(format_sse(event))
        finally:
            await queue.put(None)

    task = asyncio.create_task(pump())
    try:
        while True:
            try:
                frame = await asyncio.wait_for(queue.get(), timeout=interval)
            except TimeoutError:
                yield ": keep-alive\n\n"
                continue
            if frame is None:
                break
            yield frame
        await task  # surface unexpected errors from the pump
    finally:
        if not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


async def _check_access(body: ChatRequest, user: CurrentUser, session: DbDep, limit: int) -> None:
    await rate_limiter.hit(f"chat:{user.id}", limit)
    if body.conversation_id is not None:
        # Fail with a proper 404 before the stream starts.
        await ConversationRepository(session).get_for_user(body.conversation_id, user.id)


@router.post("/stream")
async def chat_stream(
    body: ChatRequest,
    user: CurrentUser,
    session: DbDep,
    services: ServicesDep,
    settings: SettingsDep,
) -> StreamingResponse:
    await _check_access(body, user, session, settings.rate_limit_chat_per_minute)
    events = AgentOrchestrator(services).run(
        user_id=user.id,
        message=body.message,
        conversation_id=body.conversation_id,
        request_id=request_id_var.get(),
    )
    return StreamingResponse(
        with_heartbeat(events),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    user: CurrentUser,
    session: DbDep,
    services: ServicesDep,
    settings: SettingsDep,
) -> ChatResponse:
    await _check_access(body, user, session, settings.rate_limit_chat_per_minute)
    conversation_id, message = await AgentOrchestrator(services).answer(
        user_id=user.id,
        message=body.message,
        conversation_id=body.conversation_id,
        request_id=request_id_var.get(),
    )
    return ChatResponse(conversation_id=conversation_id, message=MessageOut(**message))
