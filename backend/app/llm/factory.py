"""Builds the configured LLM provider."""

from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache

from app.core.config import Settings, get_settings
from app.core.errors import LLMUnavailableError
from app.llm.base import ChatMessage, LLMProvider, LLMResponse
from app.llm.openai_compatible import OpenAICompatibleProvider

_NOT_CONFIGURED = (
    "No language model is configured. Set LLM_BASE_URL, LLM_MODEL and LLM_API_KEY "
    "(or point LLM_BASE_URL at a local Ollama server)."
)


class UnconfiguredLLM(LLMProvider):
    """Null object used when no provider is configured: every call fails clearly."""

    name = "none"
    model = ""

    @property
    def configured(self) -> bool:
        return False

    async def complete(self, messages: list[ChatMessage], **_: object) -> LLMResponse:
        raise LLMUnavailableError(_NOT_CONFIGURED)

    async def stream(self, messages: list[ChatMessage], **_: object) -> AsyncIterator[str]:
        raise LLMUnavailableError(_NOT_CONFIGURED)
        yield ""  # pragma: no cover - makes this an async generator


def build_llm_provider(settings: Settings) -> LLMProvider:
    if not settings.llm_configured:
        return UnconfiguredLLM()
    return OpenAICompatibleProvider(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key.get_secret_value(),
        model=settings.llm_model,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        timeout_seconds=settings.llm_timeout_seconds,
        json_mode=settings.llm_json_mode,
        reasoning_effort=settings.llm_reasoning_effort or None,
    )


@lru_cache
def get_llm_provider() -> LLMProvider:
    return build_llm_provider(get_settings())
