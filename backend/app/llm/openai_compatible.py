"""LLM provider for any OpenAI-compatible Chat Completions API.

Works with OpenAI, Groq, Gemini's OpenAI endpoint, OpenRouter, Together,
vLLM, LM Studio and Ollama (`/v1`). Uses httpx directly so the app does not
depend on a vendor SDK.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.core.errors import LLMUnavailableError
from app.llm.base import ChatMessage, LLMProvider, LLMResponse, TokenUsage
from app.llm.usage import record_usage

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS = {408, 409, 429, 500, 502, 503, 504}
_MAX_ATTEMPTS = 3
_MAX_RETRY_AFTER_SECONDS = 20.0


class OpenAICompatibleProvider(LLMProvider):
    name = "openai_compatible"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        temperature: float = 0.1,
        max_tokens: int = 1200,
        timeout_seconds: float = 60.0,
        json_mode: bool = True,
        reasoning_effort: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._json_mode = json_mode
        self._reasoning_effort = reasoning_effort
        self._stream_usage_supported = True
        # Circuit breaker: when the provider says the quota is gone for minutes, fail
        # every call immediately instead of making the user wait through retries.
        self._blocked_until = 0.0
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers=headers,
            timeout=httpx.Timeout(timeout_seconds, connect=10.0),
            transport=transport,
        )

    def _payload(
        self,
        messages: list[ChatMessage],
        temperature: float | None,
        max_tokens: int | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": self._temperature if temperature is None else temperature,
            "max_tokens": max_tokens or self._max_tokens,
        }
        if self._reasoning_effort:
            # Reasoning models (e.g. gpt-oss) otherwise spend many hidden tokens per call.
            payload["reasoning_effort"] = self._reasoning_effort
        return payload

    def _ensure_not_blocked(self) -> None:
        remaining = self._blocked_until - time.monotonic()
        if remaining > 0:
            raise _quota_error(remaining)

    def _is_quota_exhausted(self, response: httpx.Response) -> bool:
        """A 429 asking to wait longer than we are willing to retry = quota exhausted."""
        wait = _retry_after_seconds(response)
        if response.status_code == 429 and wait is not None and wait > _MAX_RETRY_AFTER_SECONDS:
            self._blocked_until = time.monotonic() + wait
            return True
        return False

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> LLMResponse:
        self._ensure_not_blocked()
        payload = self._payload(messages, temperature, max_tokens)
        if json_mode and self._json_mode:
            payload["response_format"] = {"type": "json_object"}
        data = await self._post_with_retry(payload)
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMUnavailableError(
                "The language model returned an unexpected response."
            ) from exc
        usage = _parse_usage(data.get("usage"))
        record_usage(usage.prompt_tokens, usage.completion_tokens)
        return LLMResponse(text=text, usage=usage, model=str(data.get("model", self.model)))

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        self._ensure_not_blocked()
        payload = self._payload(messages, temperature, max_tokens)
        payload["stream"] = True
        if self._stream_usage_supported:
            payload["stream_options"] = {"include_usage": True}
        try:
            for attempt in range(1, _MAX_ATTEMPTS + 1):
                async with self._client.stream(
                    "POST", "/chat/completions", json=payload
                ) as response:
                    if response.status_code == 400 and "stream_options" in payload:
                        # Some compatible servers reject stream_options; retry without it.
                        await response.aread()
                        self._stream_usage_supported = False
                        async for delta in self.stream(
                            messages, temperature=temperature, max_tokens=max_tokens
                        ):
                            yield delta
                        return
                    if response.status_code >= 400:
                        await response.aread()
                        # Nothing has been yielded yet, so rate limits can be retried safely.
                        retryable = (
                            response.status_code in _RETRYABLE_STATUS
                            and not self._is_quota_exhausted(response)
                        )
                        if retryable and attempt < _MAX_ATTEMPTS:
                            await asyncio.sleep(_retry_delay(response, attempt))
                            continue
                        raise _status_error(response)
                    async for line in response.aiter_lines():
                        delta = _parse_stream_line(line)
                        if delta:
                            yield delta
                    return
        except httpx.TimeoutException as exc:
            raise LLMUnavailableError("The language model timed out. Please try again.") from exc
        except httpx.TransportError as exc:
            raise LLMUnavailableError("Could not reach the language model service.") from exc

    async def _post_with_retry(self, payload: dict[str, Any]) -> dict[str, Any]:
        last_error: Exception | None = None
        response: httpx.Response | None = None
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            response = None
            try:
                response = await self._client.post("/chat/completions", json=payload)
            except httpx.TimeoutException as exc:
                last_error = LLMUnavailableError("The language model timed out. Please try again.")
                last_error.__cause__ = exc
            except httpx.TransportError as exc:
                last_error = LLMUnavailableError("Could not reach the language model service.")
                last_error.__cause__ = exc
            else:
                if response.status_code < 400:
                    return response.json()
                last_error = _status_error(response)
                if response.status_code not in _RETRYABLE_STATUS or self._is_quota_exhausted(
                    response
                ):
                    raise last_error
            if attempt < _MAX_ATTEMPTS:
                await asyncio.sleep(_retry_delay(response, attempt))
        assert last_error is not None
        raise last_error

    async def aclose(self) -> None:
        await self._client.aclose()


def _quota_error(wait_seconds: float) -> LLMUnavailableError:
    minutes = max(1, round(wait_seconds / 60))
    return LLMUnavailableError(
        "The language model's usage quota is used up for now. "
        f"Please try again in about {minutes} minute{'s' if minutes > 1 else ''}."
    )


def _retry_delay(response: httpx.Response | None, attempt: int) -> float:
    """Honour the provider's Retry-After (common on free tiers), else exponential backoff."""
    wait = _retry_after_seconds(response)
    if wait is not None:
        return min(max(wait, 0.5), _MAX_RETRY_AFTER_SECONDS)
    return 0.5 * 2 ** (attempt - 1)


def _retry_after_seconds(response: httpx.Response | None) -> float | None:
    header = response.headers.get("retry-after") if response is not None else None
    try:
        return float(header) if header is not None else None
    except ValueError:
        return None


def _parse_usage(raw: Any) -> TokenUsage:
    if not isinstance(raw, dict):
        return TokenUsage()
    return TokenUsage(
        prompt_tokens=int(raw.get("prompt_tokens") or 0),
        completion_tokens=int(raw.get("completion_tokens") or 0),
    )


def _parse_stream_line(line: str) -> str | None:
    if not line.startswith("data:"):
        return None
    data = line[5:].strip()
    if not data or data == "[DONE]":
        return None
    try:
        chunk = json.loads(data)
    except json.JSONDecodeError:
        return None
    usage = chunk.get("usage")
    if usage:
        parsed = _parse_usage(usage)
        record_usage(parsed.prompt_tokens, parsed.completion_tokens)
    choices = chunk.get("choices") or []
    if not choices:
        return None
    return (choices[0].get("delta") or {}).get("content") or None


def _status_error(response: httpx.Response) -> LLMUnavailableError:
    status = response.status_code
    logger.warning("LLM provider returned HTTP %s", status)
    if status in (401, 403):
        return LLMUnavailableError("The language model rejected the configured credentials.")
    if status == 404:
        return LLMUnavailableError("The configured language model was not found.")
    if status == 429:
        wait = _retry_after_seconds(response)
        if wait is not None and wait > _MAX_RETRY_AFTER_SECONDS:
            return _quota_error(wait)
        return LLMUnavailableError("The language model is rate limited. Please retry shortly.")
    return LLMUnavailableError(f"The language model service failed (HTTP {status}).")
